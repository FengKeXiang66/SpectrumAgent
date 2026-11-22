"""TASK-04 §5.6 HTTP adapters; engines and working state remain single-source."""
import base64
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import asdict
from io import BytesIO
import json
import logging
import math
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
import numpy as np
from PIL import Image, ImageColor
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from backend.database import connect_database
from spectrumagent.annotation.labels import (LabelRequest, LabelStore, LabelPatch, ImportTreeScope,
    ImportTreeCandidate, ImportTreeApply, AssignSamples, plastic_catalog)
from spectrumagent.annotation.engines.superpixels import Parameters, SuperpixelEngine, segments_png
from spectrumagent.annotation.engines.diffusion import DEFAULT_THRESHOLD, DEFAULT_QUEUE_MIN_SIMILARITY, DiffusionEngine
from spectrumagent.annotation.session import AnnotationConflict, SessionStore
from spectrumagent.annotation.projection_io import read_projection_status
from spectrumagent.annotation.raster import polygon_mask
from spectrumagent.annotation.draft import Polygon
from spectrumagent.annotation.gestures import region_from_gesture, select_candidates
from spectrumagent.agent.tools import SLICParameters, SAMParameters
from spectrumagent.data import DataError


class LabelPaths(set):
    """The app checks concrete request paths for identity headers and 422s."""
    def __contains__(self, path):
        if super().__contains__(path):
            return True
        prefix = "/api/v1/labels/"
        if isinstance(path, str) and path.startswith(prefix):
            identifier = path[len(prefix):]
            try:
                return str(UUID(identifier)) == identifier.lower()
            except ValueError:
                pass
        return False


LABEL_PATHS = LabelPaths({"/api/v1/projects", "/api/v1/labels", "/api/v1/catalog/plastic",
    "/api/v1/labels/{label_id}", "/api/v1/labels/merge", "/api/v1/labels/import-tree/preview",
    "/api/v1/labels/import-tree/apply", "/api/v1/labels/assign-samples", "/api/v1/sample-labels"})


def block_summary(segments, label_map, resources=None):
    """One joint bincount; blanks never compete and confirmed ties win."""
    n_blocks = int(segments.max()) + 1
    n_labels = max(2, int(label_map.max()) + 3)  # -2, -1, then registered indices.
    if resources is not None:
        with resources.temporary(segments.size*24+n_blocks*n_labels*16):
            return block_summary(segments,label_map)
    histogram = np.bincount(segments.ravel().astype(np.int64) * n_labels + label_map.ravel() + 2,
                            minlength=n_blocks * n_labels).reshape(n_blocks, n_labels)
    sizes = histogram.sum(axis=1)
    # argmax chooses the first tie: confirmed ascending, then uncertain.
    order = np.r_[np.arange(2, n_labels), 0]
    marked = histogram[:, order]
    label_count = np.count_nonzero(marked, axis=1)
    winner = marked.argmax(axis=1)
    count = marked[np.arange(n_blocks), winner]
    blank = label_count == 0
    label = np.where(blank, -1, order[winner] - 2)
    purity = np.where(blank, 100, (100 * count) // np.maximum(sizes, 1))
    return {"label": label.tolist(), "purity": purity.tolist(), "label_count": label_count.tolist()}


class SuperpixelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_segments: Annotated[int, Field(strict=True, gt=0)] = Parameters().n_segments
    compactness: Annotated[float, Field(gt=0, allow_inf_nan=False)] = Parameters().compactness
    pca_components: Annotated[int, Field(strict=True, gt=0)] = Parameters().pca_components
    force: StrictBool = False


class SuperpixelReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cube_id: str
    shape: list[int]
    params: dict[str, str | int | float]
    superpixel_count: int
    n_before: int
    n_after: int
    area_cv: float
    R: float | None
    boundary_sum: float
    internal_sum: float
    boundary_pairs: int
    internal_pairs: int
    sum_ratio_diagnostic: float | None
    d_s: list[float]
    tau: float
    subdivided_ids: list[int]
    parent_children: dict[int, list[int]]
    feature_bytes: int
    resident_feature_bytes: int
    feature_mean: list[float]
    feature_std: list[float]
    normalized_mean: list[float]
    normalized_std: list[float]
    normalized_min: float
    normalized_max: float
    baseline_rss_bytes: int
    baseline_peak_rss_bytes: int
    peak_rss_bytes: int
    peak_rss_delta_bytes: int
    pca_seconds: float
    slic_seconds: float
    total_seconds: float
    overlay: dict[str, int | str]
    segments_png: str
    segments_shape: list[int]
    block_counts: list[int]


class ReadSuperpixelsReady(BaseModel):
    status: Literal['ready']
    segmentation_ref: str
    origin: Literal['memory', 'disk']
    durable: Literal[True]
    load_elapsed_ms: int
    report: SuperpixelReport


class ReadSuperpixelsMissing(BaseModel):
    status: Literal['missing']
    segmentation_ref: None = None
    origin: None = None
    durable: Literal[False] = False
    load_elapsed_ms: int
    report: None = None


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabelRecord(Input):
    id: str
    project_id: str
    schema_id: str
    code: str
    name: str
    tree_path: str
    color_hex: str
    shortcut_key: int | None
    sort_order: int
    is_background: int
    created_at: str


class MergeLabelsRequest(Input):
    source_id: UUID
    target_id: UUID


class DeletedLabel(Input):
    deleted: str


class DeleteLabelRequest(Input):
    confirm: StrictBool = False


class MergedLabels(Input):
    target: LabelRecord
    references: dict[str, int]


class AppliedTree(Input):
    created_labels: int
    created_samples: int
    skipped: int


class AssignedSamples(Input):
    assigned: int
    skipped: int


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



class DraftGesture(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    gesture_ref: Annotated[str, Field(min_length=1)]




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

    # TASK-16：UI 入口已移除，保留供审计与未来复用；TASK-15 不走此路径（它读 exports/ 下的 JSON）。
    def change_draft(identifier, operation):
        lease = engine.resources.lease(identifier, required=False) if engine.resources else nullcontext()
        with lease, sessions._lock:
            state = sessions._state(identifier)
            if engine.resources:
                engine.resources.ensure(state.label_map.nbytes*3+len(state.document_json)*4+16384,cube=str(identifier))
            before = (state.document_json, state.label_map.copy())
            result = operation()
            state.undo_stack.append(before)
            sessions._state(identifier)
            return result

    @router.get("/annotations/{cube_id}/draft")
    def get_draft(cube_id: UUID):
        lease = engine.resources.lease(cube_id, required=False, restore=False) if engine.resources else nullcontext()
        with lease, sessions._lock:
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
        lease = engine.resources.lease(identifier) if engine.resources else nullcontext()
        with lease, engine.lock, sessions._lock:
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

    def working_view(identifier, *, with_overlay=True, snapshot=None):
        lease = engine.resources.lease(identifier, required=False, restore=False) if engine.resources else nullcontext()
        with lease, sessions._lock:
            engine.registry.get(identifier)  # Existing not-found boundary, no independent source opening.
            with connect_database(store.database) as db:
                project_id = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (str(identifier),)).fetchone()[0]
            state = sessions._state(identifier)
            context = {"project_id": project_id, "queue": deepcopy(state.candidates)}
            if state.segments is None:
                return {"superpixel_count": 0, "params": None, "statistics": {}, "overlay": None,
                        "blocks": {"label": [], "purity": [], "label_count": []}, **context}
            working = snapshot if snapshot is not None else sessions._working_snapshot(identifier)
            return {"superpixel_count": len(np.unique(state.segments)), "params": working["params"],
                    "statistics": working["statistics"],
                    "blocks": block_summary(state.segments, working["label_map"], engine.resources),
                    **({"overlay": label_overlay(working["label_map"], working["label_index"], colors())}
                       if with_overlay else {}), **context}

    async def no_body(request: Request):
        if await request.body():
            raise DataError("INVALID_REQUEST", "此端点不接受 body")

    async def read_only_input(request: Request):
        if request.query_params or await request.body():
            raise DataError('INVALID_REQUEST', '分割读取不接受 body 或 query 参数')

    def encoded_report(segmentation):
        reservation = engine.resources.temporary(segmentation.segments.nbytes*8+1024**2) if engine.resources else nullcontext()
        with reservation:
            encoded = segments_png(segmentation.segments)
            return {**segmentation.report, 'segments_png': encoded['png_base64'],
                    'segments_shape': encoded['shape'], 'block_counts': encoded['counts']}

    @router.get('/datasets/{identifier}/superpixels', response_model=ReadSuperpixelsReady | ReadSuperpixelsMissing,
                dependencies=[Depends(read_only_input)])
    def get_superpixels(identifier: UUID):
        resources = engine.resources
        if resources is None:
            engine.registry.get(identifier)
            return {'status':'missing', 'load_elapsed_ms':0}
        try:
            with resources.lease(identifier, required=False, restore=False):
                result, origin, elapsed = resources.read(identifier)
                if result is None:return {'status':'missing','load_elapsed_ms':elapsed}
                return {'status':'ready','segmentation_ref':result.segmentation_ref,'origin':origin,
                        'durable':True,'load_elapsed_ms':elapsed,'report':encoded_report(result)}
        except DataError as error:
            if error.code!='SOURCE_CHANGED':raise
            raise DataError('SOURCE_CHANGED','源文件暂不可读或已变化，未恢复分割') from None
        except OSError:
            raise DataError('SOURCE_CHANGED','源文件暂不可读或已变化，未恢复分割') from None

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

    @router.patch("/labels/{label_id}", response_model=LabelRecord)
    def patch_label(label_id: UUID, request: LabelPatch):
        return store.update(str(label_id), **request.model_dump(exclude_unset=True))

    @router.delete("/labels/{label_id}", response_model=DeletedLabel)
    def delete_label(label_id: UUID, request: DeleteLabelRequest = DeleteLabelRequest()):
        return store.delete(str(label_id), confirm=request.confirm)

    @router.post("/labels/merge", response_model=MergedLabels)
    def merge_labels(request: MergeLabelsRequest):
        return store.merge(str(request.source_id), str(request.target_id))

    @router.post("/labels/import-tree/preview", response_model=list[ImportTreeCandidate])
    def preview_tree(request: ImportTreeScope):
        return store.import_tree(request.root, request.depth, project_id=request.project_id)

    @router.post("/labels/import-tree/apply", response_model=AppliedTree)
    def apply_tree(request: ImportTreeApply):
        return store.apply_tree(request.candidates, project_id=request.project_id,
                                root=request.root, depth=request.depth)

    @router.post("/labels/assign-samples", response_model=AssignedSamples)
    def assign_samples(request: AssignSamples):
        return sessions.assign_samples(**request.model_dump())

    @router.get("/sample-labels", response_model=dict[str, list[LabelRecord]])
    def sample_labels(project_id: UUID | None = None):
        return sessions.sample_labels(str(project_id) if project_id is not None else None)

    @router.post("/datasets/{identifier}/superpixels")
    def superpixels(identifier: UUID, request: SuperpixelRequest):
        params = Parameters(n_segments=request.n_segments, compactness=request.compactness,
                            pca_components=request.pca_components)
        def prepare_one():
            lease = engine.resources.lease(identifier, required=False, restore=False) if engine.resources else nullcontext()
            with lease:
                segmentation, action = engine.prepare_with_action(identifier, sessions, params, force=request.force)
                return {**encoded_report(segmentation), 'action': action}
        tasks = getattr(engine, 'preparation_tasks', None)
        return tasks.run_sync(prepare_one) if tasks else prepare_one()

    @router.post("/datasets/{identifier}/diffuse")
    def diffuse(identifier: UUID, request: DiffuseRequest):
        with current_segmentation(identifier):
            result = diffusion.generate(identifier, request.seed.model_dump(), threshold=request.threshold,
                                        queue_min_similarity=request.queue_min_similarity)
            return {**result, "candidates": [result["candidate"]], "queue": result["candidates"]}

    @router.post("/datasets/{identifier}/annotations/regions")
    def regions(identifier: UUID, request: AnnotationRegionRequest):
        with current_segmentation(identifier) as state:
            snapshot = sessions.edit(identifier, geometry_mask(state, request.geometry),
                                     action=request.action, label_id=request.label_id, geometry=request.geometry.model_dump())
            return working_view(identifier, with_overlay=False, snapshot=snapshot)

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
            saved = sessions.save(identifier, note=request.note)
            return {key: value for key, value in saved.items() if key != "version_no"}

    @router.get("/datasets/{identifier}/annotations")
    def current_annotation(identifier: UUID):
        working = working_view(identifier)
        with connect_database(store.database) as db:
            db.row_factory = sqlite3.Row
            records = [dict(row) for row in db.execute(
                "SELECT * FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (str(identifier),))]
        for record in records:
            record.pop("version_no", None)
            record["params"] = json.loads(record["params"])
            record["note"] = json.loads(record["note"]) if record["note"] is not None else None
        # Disk truth, not a UI-side guess: the workbench shows whether this
        # cube already has a published JSON annotation file.
        return {"current": records[0] if records else None, "working": working,
                "json_projection": read_projection_status(sessions.paths, identifier)}

    return router
