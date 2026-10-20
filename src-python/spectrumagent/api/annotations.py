"""TASK-04 §5.6 HTTP adapters; engines and working state remain single-source."""
import base64
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import json
import math
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
import numpy as np
from PIL import Image, ImageColor
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from backend.database import connect_database
from spectrumagent.annotation.labels import LabelRequest, LabelStore, plastic_catalog
from spectrumagent.annotation.engines.superpixels import DEFAULT_COMPACTNESS, Parameters, SuperpixelEngine
from spectrumagent.annotation.engines.diffusion import DEFAULT_THRESHOLD, DEFAULT_QUEUE_MIN_SIMILARITY, DiffusionEngine
from spectrumagent.annotation.session import AnnotationConflict, SessionStore
from spectrumagent.data import DataError


LABEL_PATHS = {"/api/v1/projects", "/api/v1/labels", "/api/v1/catalog/plastic"}


class SuperpixelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_segments: Annotated[int, Field(strict=True, gt=0)] = 800
    compactness: Annotated[float, Field(gt=0, allow_inf_nan=False)] = DEFAULT_COMPACTNESS
    pca_components: Annotated[int, Field(strict=True, gt=0)] = 5
    force: StrictBool = False


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


Pixel = Annotated[list[StrictInt], Field(min_length=2, max_length=2)]
Vertex = Annotated[list[Annotated[float, Field(strict=True, allow_inf_nan=False)]], Field(min_length=2, max_length=2)]


class PointSeed(Input):
    point: Pixel


class BoxSeed(Input):
    box: Annotated[list[StrictInt], Field(min_length=4, max_length=4)]


class DoodleSeed(Input):
    doodle: Annotated[list[Pixel], Field(min_length=1)]


class DiffuseRequest(Input):
    seed: PointSeed | BoxSeed | DoodleSeed
    threshold: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] = DEFAULT_THRESHOLD
    queue_min_similarity: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] = DEFAULT_QUEUE_MIN_SIMILARITY


class SuperpixelGeometry(Input):
    superpixels: Annotated[list[Annotated[int, Field(strict=True, ge=0)]], Field(min_length=1)]


class PolygonGeometry(Input):
    polygon: Annotated[list[Vertex], Field(min_length=3)]


class AnnotationRegionRequest(Input):
    label_id: str | None = None
    geometry: SuperpixelGeometry | PolygonGeometry
    action: Literal["confirm", "erase", "uncertain"]


class SaveRequest(Input):
    note: Annotated[str, Field(strict=True, max_length=2000)] | None = None
    overwrite: StrictBool = False
    confirm: StrictBool = False


def polygon_mask(shape, vertices):
    """R19: pixel CENTRES, even-odd, exact on-edge inclusion; no dilation."""
    rows = np.arange(shape[0], dtype=np.float64)[:, None] + .5
    cols = np.arange(shape[1], dtype=np.float64)[None, :] + .5
    inside = np.zeros(shape, dtype=bool)
    on_edge = np.zeros(shape, dtype=bool)
    for (r0, c0), (r1, c1) in zip(vertices, vertices[1:] + vertices[:1]):
        cross = (rows-r0)*(c1-c0) - (cols-c0)*(r1-r0)
        on_edge |= ((cross == 0) & (rows >= min(r0, r1)) & (rows <= max(r0, r1))
                    & (cols >= min(c0, c1)) & (cols <= max(c0, c1)))
        if r0 != r1:
            crossing = ((r0 > rows) != (r1 > rows)) & (cols < c0+(rows-r0)*(c1-c0)/(r1-r0))
            inside ^= crossing
    return inside | on_edge


def geometry_mask(state, geometry):
    if isinstance(geometry, SuperpixelGeometry):
        if not np.isin(geometry.superpixels, state.segments).all():
            raise DataError("INVALID_GEOMETRY", "区域包含不存在的超像素 id")
        return np.isin(state.segments, geometry.superpixels)
    return polygon_mask(state.label_map.shape, geometry.polygon)


def label_overlay(label_map, label_index, colors):
    """Presentation only: registered colors, light blank/dark uncertain hatches."""
    stride = max(1, math.ceil(max(label_map.shape) / 512))
    reduced = label_map[::stride, ::stride]
    rows, cols = np.indices(reduced.shape)
    maximum = np.iinfo(np.uint8).max
    diagonal = (rows+cols) % 2 == 0
    gray = np.where(diagonal, maximum//2, maximum).astype(np.uint8)
    gray[reduced == -2] = np.where(diagonal, 0, maximum//2)[reduced == -2]
    pixels = np.repeat(gray[:, :, None], 3, axis=2)
    for index, label_id in label_index.items():
        pixels[reduced == int(index)] = ImageColor.getrgb(colors[label_id])
    image = Image.fromarray(pixels)
    output = BytesIO()
    image.save(output, format="PNG")
    return {"width": image.width, "height": image.height, "mime": "image/png",
            "png_base64": base64.b64encode(output.getvalue()).decode("ascii")}


def make_router(store: LabelStore, engine: SuperpixelEngine, sessions: SessionStore, diffusion: DiffusionEngine):
    router = APIRouter(prefix="/api/v1", tags=["annotation labels"])

    @contextmanager
    def current_segmentation(identifier):
        # Same lock order as DiffusionEngine; keep check + operation atomic.
        with engine.lock, sessions._lock:
            state = sessions._state(identifier)
            cached = engine.cache.get(str(identifier))
            params = cached[1].report["params"] if cached is not None else None
            if (state.params != params or (cached is not None
                    and any(params.get(key) != value for key, value in asdict(cached[0]).items()))):
                raise AnnotationConflict("分割参数与工作态不一致，请重新生成超像素", code="SEGMENTATION_STALE")
            sessions._require_segments(state)
            yield state

    def colors():
        with connect_database(store.database) as db:
            return dict(db.execute("SELECT id,color_hex FROM label"))

    def working_view(identifier):
        with sessions._lock:
            engine.registry.get(identifier)  # Existing not-found boundary, no independent source opening.
            with connect_database(store.database) as db:
                project_id = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (str(identifier),)).fetchone()[0]
            state = sessions._state(identifier)
            context = {"project_id": project_id, "queue": deepcopy(state.candidates)}
            if state.segments is None:
                return {"superpixel_count": 0, "params": None, "statistics": {}, "overlay": None, **context}
            working = sessions.working(identifier)
            return {"superpixel_count": len(np.unique(state.segments)), "params": working["params"],
                    "statistics": working["statistics"],
                    "overlay": label_overlay(working["label_map"], working["label_index"], colors()), **context}

    async def no_body(request: Request):
        if await request.body():
            raise DataError("INVALID_REQUEST", "此端点不接受 body")

    @router.get("/projects")
    def projects():
        return store.projects()

    @router.get("/labels")
    def labels(project_id: str):
        return store.tree(project_id)

    @router.post("/labels", status_code=201)
    def add_label(request: LabelRequest):
        return store.add(request)

    @router.get("/catalog/plastic")
    def catalog():
        return plastic_catalog()

    @router.post("/datasets/{identifier}/superpixels")
    def superpixels(identifier: UUID, request: SuperpixelRequest):
        params = Parameters(n_segments=request.n_segments, compactness=request.compactness,
                            pca_components=request.pca_components)
        segmentation = engine.generate(identifier, params, force=request.force)
        sessions.set_segmentation(identifier, segmentation)
        return segmentation.report

    @router.post("/datasets/{identifier}/diffuse")
    def diffuse(identifier: UUID, request: DiffuseRequest):
        with current_segmentation(identifier):
            result = diffusion.generate(identifier, request.seed.model_dump(), threshold=request.threshold,
                                        queue_min_similarity=request.queue_min_similarity)
            return {**result, "candidates": [result["candidate"]], "queue": result["candidates"]}

    @router.post("/datasets/{identifier}/annotations/regions")
    def regions(identifier: UUID, request: AnnotationRegionRequest):
        with current_segmentation(identifier) as state:
            sessions.edit(identifier, geometry_mask(state, request.geometry),
                          action=request.action, label_id=request.label_id)
            return working_view(identifier)

    @router.post("/datasets/{identifier}/annotations/undo")
    def undo(identifier: UUID):
        sessions.undo(identifier)
        return working_view(identifier)

    @router.get("/datasets/{identifier}/annotations/working")
    def working(identifier: UUID):
        return working_view(identifier)

    @router.post("/datasets/{identifier}/annotations/validate", dependencies=[Depends(no_body)])
    def validate(identifier: UUID):
        with current_segmentation(identifier):
            return sessions.validate(identifier)

    @router.post("/datasets/{identifier}/annotations/save")
    def save(identifier: UUID, request: SaveRequest):
        with current_segmentation(identifier):
            saved = sessions.save(identifier, overwrite=request.overwrite, confirm=request.confirm, note=request.note)
            return {key: value for key, value in saved.items() if key != "version_no"}

    @router.get("/datasets/{identifier}/annotations")
    def versions(identifier: UUID):
        working = working_view(identifier)
        with connect_database(store.database) as db:
            db.row_factory = sqlite3.Row
            records = [dict(row) for row in db.execute(
                "SELECT * FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC", (str(identifier),))]
        for record in records:
            record["params"] = json.loads(record["params"])
            record["note"] = json.loads(record["note"]) if record["note"] is not None else None
        return {"versions": records, "working": working}

    @router.get("/datasets/{identifier}/annotations/{version}/overlay")
    def version_overlay(identifier: UUID, version: UUID):
        engine.registry.get(identifier)
        # Verify the nested cube/version relation; do not expose another cube's
        # snapshot through a valid but unrelated version UUID.
        with connect_database(store.database) as db:
            owner = db.execute("SELECT cube_id FROM annotation_version WHERE id=?", (str(version),)).fetchone()
            if owner is not None and owner[0] != str(identifier):
                error = DataError("VERSION_NOT_FOUND", "标注版本不存在", version_id=str(version))
                error.status_code = 404  # R20: a valid UUID belonging to another cube.
                raise error
        snapshot = sessions.read_version(str(version))
        return label_overlay(snapshot["label_map"], snapshot["label_index"], colors())

    return router
