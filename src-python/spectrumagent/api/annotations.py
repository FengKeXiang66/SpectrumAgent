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
from fastapi.responses import FileResponse
import numpy as np
from PIL import Image, ImageColor
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from backend.database import connect_database
from spectrumagent.annotation.labels import LabelRequest, LabelStore, plastic_catalog
from spectrumagent.annotation.engines.superpixels import DEFAULT_COMPACTNESS, Parameters, SuperpixelEngine
from spectrumagent.annotation.engines.diffusion import DEFAULT_THRESHOLD, DEFAULT_QUEUE_MIN_SIMILARITY, DiffusionEngine
from spectrumagent.annotation.session import AnnotationConflict, SessionStore
from spectrumagent.annotation.raster import polygon_mask
from spectrumagent.annotation.draft import Polygon
from spectrumagent.annotation.gestures import region_from_gesture, select_candidates
from spectrumagent.agent.tools import SLICParameters, SAMParameters
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


class StoreGestureRequest(Input):
    seed: PointSeed | BoxSeed | DoodleSeed


class StoredGesture(BaseModel):
    gesture_ref: str
    kind: Literal["point", "box", "doodle"]


class DraftCandidatesRequest(Input):
    revision: Annotated[int, Field(ge=0)]
    class_code: Annotated[str, Field(min_length=1)]
    method: Literal["SLIC", "SAM"]
    params: SLICParameters | SAMParameters

    @model_validator(mode="after")
    def matching_params(self):
        key = "gesture_ref" if self.method == "SAM" else "n_segments"
        if key not in self.params.model_dump():
            raise ValueError("method 与 params 类型不一致")
        return self


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


class DraftGesture(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    gesture_ref: Annotated[str, Field(min_length=1)]


class DraftConfirmRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    revision: Annotated[int, Field(ge=0)]
    overwrite: bool = False
    note: Annotated[str, Field(max_length=2000)] | None = None


class DraftRegionInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    revision: Annotated[int, Field(ge=0)]
    geometry: Polygon | DraftGesture


class DraftAddRequest(DraftRegionInput):
    op: Literal["add"] = "add"
    class_code: Annotated[str, Field(min_length=1)]
    confidence: Literal["high", "medium", "low"] | None = None


class DraftUncertainRequest(DraftRegionInput):
    op: Literal["uncertain"]


class DraftEraseRequest(DraftRegionInput):
    op: Literal["erase"]


class DraftPatchRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    revision: Annotated[int, Field(ge=0)]
    class_code: Annotated[str, Field(min_length=1)] | None = None
    geometry: Polygon | DraftGesture | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    deleted: bool | None = None

    @model_validator(mode="after")
    def nonnull_patch(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("patch 不接受 null 字段")
        return self


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

    @router.post("/annotations/{cube_id}/draft/confirm")
    def confirm_draft(cube_id: UUID, request: DraftConfirmRequest):
        return sessions.confirm(cube_id, **request.model_dump())

    @router.get("/annotations/{cube_id}/versions/{version_id}/training-mat", response_class=FileResponse,
                responses={200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
    def training_mat(cube_id: UUID, version_id: UUID):
        from spectrumagent.agent.mat import MatStore
        mats = MatStore(sessions.registry, sessions.paths)
        return FileResponse(mats.file(mats.get(cube_id, version_id)), media_type="application/octet-stream", filename="training_mat.mat")

    def change_draft(identifier, operation):
        with sessions._lock:
            state = sessions._state(identifier)
            before = (state.document_json, state.label_map.copy())
            result = operation()
            state.undo_stack.append(before)
            sessions._state(identifier)
            return result

    @router.get("/annotations/{cube_id}/draft")
    def get_draft(cube_id: UUID):
        with sessions._lock:
            sessions._state(cube_id)
            return sessions.drafts.view(cube_id)

    @router.post("/annotations/{cube_id}/draft/regions")
    def add_draft_region(cube_id: UUID, request: DraftAddRequest | DraftUncertainRequest | DraftEraseRequest):
        if isinstance(request.geometry, DraftGesture):
            result = region_from_gesture(sessions, cube_id, request.geometry.gesture_ref, op=request.op,
                class_code=getattr(request, "class_code", None), confidence=getattr(request, "confidence", None), expected_revision=request.revision)
            return {"revision": result["revision"], "region_id": result["region_id"],
                    "statistics": sessions.drafts.statistics(cube_id, result["document"])}
        arguments = request.model_dump(exclude={"revision"}, exclude_unset=True)
        arguments["geometry"] = request.geometry.model_dump()
        result = change_draft(cube_id, lambda: sessions.drafts.add(cube_id, request.revision, **arguments))
        return {"revision": result["revision"], "region_id": result["region_id"],
                "statistics": sessions.drafts.statistics(cube_id, result["document"])}

    @router.post("/annotations/{cube_id}/draft/regions/{region_id}")
    def patch_draft_region(cube_id: UUID, region_id: str, request: DraftPatchRequest):
        result = change_draft(cube_id, lambda: sessions.drafts.patch(
            cube_id, region_id, request.revision, request.model_dump(exclude={"revision"}, exclude_unset=True)))
        return {"revision": result["revision"], "region_id": result["region_id"]}

    @router.post("/annotations/{cube_id}/gestures", response_model=StoredGesture)
    def store_gesture(cube_id: UUID, request: StoreGestureRequest):
        seed = request.seed.model_dump()
        return {"gesture_ref": sessions.store_gesture(cube_id, seed), "kind": next(iter(seed))}

    @router.post("/annotations/{cube_id}/draft/candidates")
    def draft_candidates(cube_id: UUID, request: DraftCandidatesRequest):
        result = select_candidates(sessions, diffusion, cube_id, method=request.method, class_code=request.class_code,
                                   params=request.params, expected_revision=request.revision)
        return {"revision": result["revision"], "region_id": result["region_id"], "geometry_type": "pixel_set",
                "preview_statistics": {key: result[key] for key in ("n_superpixels", "pixel_count", "min_similarity", "avg_similarity")}}

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
                          action=request.action, label_id=request.label_id, geometry=request.geometry.model_dump())
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
