"""In-memory manual annotation and bounded sample aggregation (TASK-04 §5.4).

The pixel map is authoritative. SQLite holds one aggregate per present label,
never editing history; snapshots own their immutable label-index mapping.
"""
from spectrumagent.storage import guard as storage
from collections import deque
from dataclasses import dataclass, field, replace
from copy import deepcopy
import json
import os
import logging
import sqlite3
from pathlib import PurePosixPath
from threading import RLock
from time import perf_counter
from uuid import uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from .engines.superpixels import ReadableRows, row_blocks
from .labels import AssignSamples, LabelStore, invalid, now
from .draft import DraftStore, remap_document, conflict
from .raster import encode_rle, rasterize, rasterize_with_conflicts_v1
from .segmentation_resources import managed


UNDO_DEPTH = 30


class AnnotationConflict(DataError):
    """Transport adapters can preserve the mandated HTTP 409 in §5.4."""
    status_code = 409

    def __init__(self, detail, *, code="ANNOTATION_CONFLICT"):
        super().__init__(code, detail)


@dataclass
class Moments:
    count: int
    mean: np.ndarray
    m2: np.ndarray

    @property
    def std(self):
        return np.sqrt(np.maximum(self.m2 / self.count, 0))


@dataclass
class Aggregates:
    labels: dict = field(default_factory=dict)
    parts: dict = field(default_factory=dict)


def _accumulate(target, keys, spectra):
    """Combine block moments; avoids cancellation for constant spectra."""
    unique, inverse = np.unique(keys, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    cuts = np.cumsum(np.bincount(inverse))[:-1]
    for key, indices in zip(unique, np.split(order, cuts)):
        pixels = spectra[indices]
        mean = pixels.mean(axis=0, dtype=np.float64)
        delta = pixels - mean
        m2 = np.einsum("ij,ij->j", delta, delta)
        count = len(indices)
        key = int(key)
        previous = target.get(key)
        if previous is None:
            target[key] = Moments(count, mean, m2)
        else:
            total = previous.count + count
            shift = mean - previous.mean
            previous.m2 += m2 + shift * shift * (previous.count * count / total)
            previous.mean += shift * (count / total)
            previous.count = total


def aggregate_spectra(registry, cube_id, label_map, *, block_size=32, segments=None):
    """Save AND quality use these current-state original-reflectance moments.

    Only one bounded row block is read at a time, always via Registry.readable.
    Optional parts are (superpixel ∩ label), including mixed superpixels (R17).
    """
    cube_id = str(cube_id)
    dataset, _ = registry.readable(cube_id, raw=False)
    shape = dataset.shape
    del dataset
    if label_map.dtype != np.int32 or label_map.shape != shape[:2] or np.any(label_map < -2):
        raise DataError("INVALID_LABEL_MAP", "需要 int32 (lines,samples) 三态 label map")
    if block_size <= 0:
        raise DataError("INVALID_BLOCK_SIZE", "行块大小必须为正")
    if segments is not None and (segments.shape != label_map.shape or np.any(segments < 0)):
        raise DataError("INVALID_SEGMENTS", "超像素图必须与 label map 同形且 id 非负")
    result = Aggregates()
    label_count = int(label_map.max()) + 1 if np.any(label_map >= 0) else 0
    for l0, l1, block in row_blocks(ReadableRows(registry, cube_id, shape), block_size):
        labels = label_map[l0:l1].ravel()
        confirmed = labels >= 0
        if np.any(confirmed):
            values = block.reshape(-1, shape[2])[confirmed]
            selected = labels[confirmed]
            _accumulate(result.labels, selected, values)
            if segments is not None:
                ids = segments[l0:l1].ravel()[confirmed].astype(np.int64)
                _accumulate(result.parts, ids * label_count + selected, values)
            del values, selected
        del block
    if segments is not None and label_count:
        result.parts = {divmod(key, label_count): value for key, value in result.parts.items()}
    return result


def map_statistics(label_map, label_ids, candidates=(), segments=None):
    counts = {str(i): int(np.count_nonzero(label_map == i)) for i in range(len(label_ids))}
    labeled = int(np.count_nonzero(label_map >= 0))
    uncertain = int(np.count_nonzero(label_map == -2))
    blank = int(np.count_nonzero(label_map == -1))
    pending = np.zeros(label_map.shape, dtype=bool)
    if segments is not None:
        for candidate in candidates:
            pending |= np.isin(segments, candidate["superpixels"])
    largest = max(range(len(label_ids)), key=lambda i: counts[str(i)], default=None)
    return {"n_pixels": int(label_map.size), "labeled_pixels": labeled,
            "uncertain_pixels": uncertain, "blank_pixels": blank,
            "labeled_percent": 100 * labeled / label_map.size,
            "uncertain_percent": 100 * uncertain / label_map.size,
            "blank_percent": 100 * blank / label_map.size,
            "label_counts": counts, "pending_pixels": int(pending.sum()),
            "dominant_label_id": label_ids[largest] if labeled else None}


@dataclass
class WorkingState:
    label_map: np.ndarray
    label_ids: tuple
    segments: np.ndarray | None = None
    params: dict | None = None
    candidates: list = field(default_factory=list)
    gestures: dict = field(default_factory=dict)
    # §5.4 requires >=5; TASK-12 raises to 30. No operation history is persisted.
    undo_stack: deque = field(default_factory=lambda: deque(maxlen=UNDO_DEPTH))
    document_json: str | None = None
    revision: int = 0
    segmentation_content_hash: str | None = None
    segmentation_algorithm_version: str | None = None
    segmentation_ref: str | None = None
    segmentation_notice: str | None = None


class SessionStore:
    def __init__(self, registry, paths):
        self.registry, self.paths = registry, paths
        self.database = registry.database
        self._states = {}
        self._lock = RLock()
        self.drafts = DraftStore(self.database, registry)
        self.resources = None

    def _label_ids(self, cube_id):
        cube_id = str(cube_id)
        self.registry.get(cube_id)
        with connect_database(self.database) as db:
            rows = db.execute("SELECT l.id FROM label l JOIN dataset_registry d "
                              "ON d.project_id=l.project_id WHERE d.id=? AND l.deleted_at IS NULL "
                              "ORDER BY l.sort_order ASC,l.code ASC", (cube_id,)).fetchall()
        return tuple(row[0] for row in rows)

    def forget(self, cube_id):
        """Drop cached working state so it rebuilds from the persisted draft."""
        with self._lock:
            self._states.pop(str(cube_id), None)

    def _state(self, cube_id):
        cube_id = str(cube_id)
        if self.resources is not None:
            dataset, _ = self.registry.get(cube_id)
            self.resources.ensure(int(np.prod(dataset.shape[:2]))*12+32768,cube=cube_id)
        ids = self._label_ids(cube_id)
        state = self._states.get(cube_id)
        needs_raster = state is None or state.label_map is None
        if state is None:
            dataset, _ = self.registry.readable(cube_id, raw=False)
            state = WorkingState(np.full(dataset.shape[:2], -1, dtype=np.int32), ids)
        elif state.label_map is None:
            dataset, _ = self.registry.get(cube_id)
            # Reconstructed below from the authoritative, unchanged draft.
            state.label_map = np.empty(dataset.shape[:2], dtype=np.int32)
        if state.label_ids != ids:
            if self.resources is not None:
                from .segmentation_resources import unique_bytes
                self.resources.ensure(unique_bytes(state.undo_stack)*2+state.label_map.nbytes*3+32768,cube=cube_id)
            # New labels can change indices. Preserve pixel identity by label ID,
            # including undo maps; saved versions are never touched.
            positions = {label_id: i for i, label_id in enumerate(ids)}
            def remap(old):
                result = old.copy()
                for i, label_id in enumerate(state.label_ids):
                    if label_id not in positions:
                        if np.any(old == i):
                            raise DataError("LABEL_REMOVED", "工作态引用的标签已被删除", label_id=label_id)
                        continue
                    result[old == i] = positions[label_id]
                return result
            # Prepare both halves before writing; CAS failures change neither.
            labels = self.drafts.labels(cube_id)
            undo = deque(maxlen=UNDO_DEPTH)
            for doc, old in state.undo_stack:
                try:
                    undo.append((json.dumps(remap_document(json.loads(doc), labels, state.label_ids)),
                                 remap(old) if old is not None else None))
                except DataError as error:
                    if error.code != 'LABEL_REMOVED':
                        raise
                    # A permanent deletion cannot be reversed by annotation undo.
        else:
            undo = state.undo_stack
        row = self.drafts.get(cube_id)
        document = row["document"] if row else self.drafts.empty(cube_id)
        labels = self.drafts.labels(cube_id)
        old_ids = state.label_ids if row and state.revision == row["revision"] and state.document_json else None
        normalized = remap_document(document, labels, old_ids)
        if normalized != document or state.label_ids != ids:
            row = self.drafts.replace(cube_id, normalized, row["revision"] if row else 0)
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        # The draft is still read and checked on every access. Reuse only the
        # exact projection of that document, never an independently edited map.
        if needs_raster or state.document_json != encoded or state.label_ids != ids or os.environ.get('SPECTRUMAGENT_RASTER_CACHE')=='0':
            state.label_map = rasterize(normalized, state.label_map.shape)
        state.document_json = encoded
        state.revision = row["revision"] if row else 0
        state.undo_stack = undo
        state.label_ids = ids
        self._states[cube_id] = state
        return state

    @managed(restore=False)
    def working(self, cube_id):
        return self._working_snapshot(cube_id)

    def _working_snapshot(self, cube_id):
        """Attached-state projection; caller already owns the ordered lease."""
        with self._lock:
            state = self._state(cube_id)
            return {"label_map": state.label_map.copy(),
                    "label_index": {str(i): label_id for i, label_id in enumerate(state.label_ids)},
                    "params": dict(state.params) if state.params is not None else None,
                    "statistics": map_statistics(state.label_map, state.label_ids, state.candidates, state.segments)}

    def set_segmentation(self, cube_id, segmentation):
        with self._lock:
            state = self._state(cube_id)
            if segmentation.segments.shape != state.label_map.shape:
                raise DataError("INVALID_SEGMENTS", "超像素图与工作态不同形")
            actual = dict(segmentation.report["params"])
            if state.params is not None and any(state.params[key] != actual[key]
                                                for key in ("n_segments", "compactness", "pca_components")):
                state.candidates.clear()
            state.segments = segmentation.segments.copy()
            state.params = actual
            state.segmentation_content_hash = getattr(segmentation, "content_hash", None)
            state.segmentation_algorithm_version = getattr(segmentation, "algorithm_version", None)

    @managed()
    def store_gesture(self, cube_id, seed):
        with self._lock:
            state = self._state(cube_id)
            if self.resources is not None:
                from .segmentation_resources import unique_bytes
                self.resources.ensure(unique_bytes(seed)*2+4096,cube=str(cube_id))
            reference = "g-" + uuid4().hex
            state.gestures[reference] = {"seed": deepcopy(seed), "created_at": now()}
            return reference

    @managed(required=True)
    def resolve_gesture(self, cube_id, gesture_ref):
        with self._lock:
            entry = self._state(cube_id).gestures.get(gesture_ref)
            if entry is None:
                error = DataError("GESTURE_NOT_FOUND", "手势引用不存在或已失效")
                error.status_code = 404
                raise error
            return deepcopy(entry["seed"])

    @managed()
    def edit(self, cube_id, mask, *, action, label_id=None, geometry=None, source=None, confidence=None):
        """Apply an explicit human selection; no automatic label assignment."""
        with self._lock:
            state = self._state(cube_id)
            if mask.shape != state.label_map.shape or mask.dtype != np.bool_:
                raise DataError("INVALID_REGION", "区域必须为同形布尔像素掩码")
            if action == "confirm":
                if label_id not in state.label_ids:
                    raise DataError("INVALID_LABEL", "标签须属于当前项目", label_id=label_id)
                value = state.label_ids.index(label_id)
            elif action in ("erase", "uncertain"):
                value = -1 if action == "erase" else -2
            else:
                raise DataError("INVALID_REGION_ACTION", "操作须为 confirm/erase/uncertain")
            if geometry is None or "superpixels" in geometry:
                actual = {"type": "pixel_set", "rows": encode_rle(mask), "segments_fingerprint": state.params}
            else:
                actual = {"type": "polygon", "points": geometry["polygon"]}
            if self.resources is not None:
                self.resources.ensure(state.label_map.nbytes*3+len(json.dumps(actual))*4+len(state.document_json)*2+8192,cube=str(cube_id))
            self.drafts.add(cube_id, state.revision, geometry=actual,
                            op="add" if action == "confirm" else action,
                            class_code=json.loads(state.document_json)["classes"][value]["code"] if action == "confirm" else None,
                            source=source or "manual", confidence=confidence)
            state.undo_stack.append((state.document_json, state.label_map.copy()))
            if action != "erase" and state.segments is not None:
                # Consume explicitly selected candidates; generation belongs to 10.3.5.
                state.candidates[:] = [candidate for candidate in state.candidates
                                      if not np.all(mask[np.isin(state.segments, candidate["superpixels"])])]
            return self.working(cube_id)

    @managed()
    def undo(self, cube_id):
        with self._lock:
            state = self._state(cube_id)
            if not state.undo_stack:
                raise AnnotationConflict("撤销栈为空")
            document, label_map = state.undo_stack[-1]
            self.drafts.replace(cube_id, json.loads(document), state.revision)
            state.undo_stack.pop()
            if label_map is not None:state.label_map = label_map.copy()
            return self.working(cube_id)

    @managed(required=True)
    def validate(self, cube_id, *, threshold=None):
        from .quality import validate
        with self._lock:
            state = self._state(cube_id)
            self._require_segments(state)
            return validate(self.registry, cube_id, state.label_map, state.segments,
                            state.label_ids, state.params, threshold=threshold)

    @staticmethod
    def _require_segments(state):
        if state.segments is None:
            raise DataError("SUPERPIXELS_REQUIRED", "请先生成超像素分割")

    @managed(required=False)
    def save(self, cube_id, *, overwrite=False, confirm=False, note: str | None = None, frozen=None, external=False):
        if note is not None and (not isinstance(note, str) or len(note) > 2000):
            raise DataError("INVALID_VERSION_NOTE", "保存备注须为不超过 2000 字符的文本")
        cube_id = str(cube_id)
        with self._lock:
            state = self._state(cube_id) if frozen is None else replace(
                self._states[cube_id], document_json=frozen[0], label_map=frozen[1], revision=frozen[2],
                label_ids=self._label_ids(cube_id))
            if not external:
                self._require_segments(state)
            elif not state.document_json or not json.loads(state.document_json)['regions']:
                raise DataError('EXTERNAL_ANNOTATION_INVALID', '外部标注没有有效区域')
            with connect_database(self.database) as db:
                latest = db.execute("SELECT id,version_no,created_at FROM annotation_version "
                                    "WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,)).fetchone()
                latest_ref = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=?", (latest[0],)).fetchone()[0] if latest else None
            # Saving replaces the current result; callers cannot create history.
            overwrite = latest is not None
            started = perf_counter()
            dataset, _ = self.registry.get(cube_id)
            aggregates = aggregate_spectra(self.registry, cube_id, state.label_map,
                                           block_size=state.params["block_size"], segments=state.segments)
            from .quality import validate
            quality = (dict(completeness=map_statistics(state.label_map, state.label_ids),
                            source='external_roi', not_applicable={'超像素检查': '外部标注直接接入，未生成超像素'})
                       if external else validate(self.registry, cube_id, state.label_map, state.segments,
                                                 state.label_ids, state.params, aggregates=aggregates))
            timestamp = now()
            version_id = latest[0] if overwrite else str(uuid4())
            version_no = latest[1] if overwrite else (latest[1] + 1 if latest else 1)
            created = latest[2] if overwrite else timestamp
            note = (json.dumps({"event": "overwrite" if overwrite else "save", "at": timestamp,
                                **({"text": note} if note is not None else {})})
                    if overwrite or note is not None else None)
            annotation_rows, spectrum_rows = self._aggregate_rows(
                cube_id, version_id, state, aggregates, dataset.name, timestamp)
            relative = latest_ref if overwrite else PurePosixPath(cube_id, "current").as_posix()
            directory = self.paths.snapshots.joinpath(*PurePosixPath(relative).parts)
            storage.mkdir(directory.parent, parents=True, exist_ok=True)
            temporary = directory.with_name(directory.name + f".{uuid4().hex}.tmp")
            backup = directory.with_name(directory.name + f".{uuid4().hex}.backup.tmp")
            storage.mkdir(temporary)
            published = False
            try:
                self._write_snapshot(temporary, state, aggregates)
                transaction_started = perf_counter()
                with connect_database(self.database) as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute("SELECT id,version_no,created_at FROM annotation_version "
                                         "WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,)).fetchone()
                    if current != latest:
                        raise AnnotationConflict("保存期间标注已改变，请重试")
                    if frozen is not None:
                        current_draft = db.execute("SELECT revision FROM annotation_draft WHERE cube_id=?", (cube_id,)).fetchone()
                        if (current_draft[0] if current_draft else 0) != frozen[2]:
                            raise conflict()
                    if directory.exists():
                        storage.replace(directory, backup)
                    storage.replace(temporary, directory)
                    published = True
                    values = (relative, int(state.label_map.size), int(np.count_nonzero(state.label_map >= 0)),
                              0, json.dumps(state.params), note)
                    if overwrite:
                        db.execute("DELETE FROM annotation WHERE version_id=?", (version_id,))
                        db.execute("DELETE FROM sample_spectrum WHERE version_id=?", (version_id,))
                        db.execute("DELETE FROM training_mat WHERE annotation_version_id=?", (version_id,))
                        db.execute("UPDATE annotation_version SET snapshot_ref=?,n_pixels=?,labeled_pixels=?,"
                                   "auto_ratio=?,params=?,note=? WHERE id=?", (*values, version_id))
                    else:
                        db.execute("INSERT INTO annotation_version "
                                   "(id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,auto_ratio,params,note,created_at) "
                                   "VALUES (?,?,?,?,?,?,?,?,?,?)", (version_id, cube_id, version_no, *values, created))
                    db.executemany("INSERT INTO annotation "
                                   "(id,cube_id,version_id,granularity,label_id,geometry,pixel_count,source,created_at) "
                                   "VALUES (?,?,?,?,?,?,?,?,?)", annotation_rows)
                    db.executemany("INSERT INTO sample_spectrum "
                                   "(id,cube_id,version_id,label_id,sample_code,n_pixels,mean_ref,std_ref,created_at) "
                                   "VALUES (?,?,?,?,?,?,?,?,?)", spectrum_rows)
                    from hashlib import sha256
                    document=json.dumps(json.loads(state.document_json),ensure_ascii=False,sort_keys=True,separators=(',',':'))
                    db.execute('INSERT INTO annotation_confirmation_state VALUES (?,?,?,?) ON CONFLICT(cube_id) DO UPDATE SET '
                               'annotation_version_id=excluded.annotation_version_id,draft_revision=excluded.draft_revision,document_sha256=excluded.document_sha256',
                               (cube_id,version_id,state.revision,sha256(document.encode()).hexdigest()))
                transaction_seconds = perf_counter() - transaction_started
            except BaseException:
                if published:
                    storage.rmtree(directory)
                if backup.exists():
                    storage.replace(backup, directory)
                raise
            finally:
                if temporary.exists():
                    storage.rmtree(temporary)
            if backup.exists():
                storage.rmtree(backup)
            if overwrite:
                from spectrumagent.agent.mat import MatStore
                MatStore(self.registry, self.paths).discard_invalidated(cube_id, version_id)
            export = self._project_saved(cube_id, version_no, state, dataset.header_path)
            return {"id": version_id, "cube_id": cube_id, "version_no": version_no,
                    "snapshot_ref": relative, "created_at": created, "note": note,
                    "quality": quality, "elapsed_seconds": perf_counter() - started,
                    "transaction_seconds": transaction_seconds, "export": export}

    @managed(restore=False)
    def import_external(self, cube_id, document):
        """Persist an already validated ROI through the normal draft/snapshot path.

        No segmentation is fabricated. An existing, different annotation is never
        overwritten by import; retries of the exact document remain idempotent.
        """
        with self._lock:
            old = self.drafts.get(cube_id)
            if old:
                def semantic(doc):
                    doc = deepcopy(doc)
                    for region in doc['regions']:
                        region.pop('created_at', None)
                    return doc
                if semantic(old['document']) == semantic(document):
                    document = old['document']
            if old and old['document']['regions'] and old['document'] != document:
                raise DataError('ANNOTATION_EXISTS', '样品已有不同标注，请先在工作台核对，未覆盖')
            if not old or old['document'] != document:
                self.drafts.replace(cube_id, document, old['revision'] if old else 0)
            state = self._state(cube_id)
            state.params = {'block_size': 32, 'source': 'external_roi'}
            return self.save(cube_id, external=True, note='导入已确认的外部 ROI 标注')

    def _project_saved(self, cube_id, version_no, state, source_hdr):
        # The version transaction and four-file snapshot have already succeeded.
        try:
            from .projection_io import write_projection
            with connect_database(self.database) as db:
                project_id = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (cube_id,)).fetchone()[0]
            document = json.loads(state.document_json)
            label_index = {str(i): item["code"] for i, item in enumerate(document["classes"])}
            path, _ = write_projection(self.paths, cube_id, project_id, source_hdr, version_no,
                                       state.label_map, label_index, document=document)
            return {"ok": True, "path": path, "error": None}
        except Exception as error:
            logging.getLogger(__name__).exception("JSON 投影失败 cube_id=%s", cube_id)
            return {"ok": False, "path": None, "error": str(error)}

    @staticmethod
    def _write_snapshot(directory, state, aggregates):
        # A sibling .tmp directory is published with os.replace before DB commit.
        np.savez_compressed(storage.resolve_write(directory / "label_map.npz", kind="ARTIFACT_WRITE"), label_map=state.label_map)
        (storage.resolve_write(directory / "label_index.json", kind="WRITE_TEXT")).write_text(json.dumps(
            {str(i): label_id for i, label_id in enumerate(state.label_ids)}), encoding="utf-8")
        spectra = {}
        for i, moments in aggregates.labels.items():
            spectra[f"mean_{i}"] = moments.mean.astype(np.float64)
            spectra[f"std_{i}"] = moments.std.astype(np.float64)
        np.savez_compressed(storage.resolve_write(directory / "spectra.npz", kind="ARTIFACT_WRITE"), **spectra)
        (storage.resolve_write(directory / "annotation.json", kind="WRITE_TEXT")).write_text(state.document_json, encoding="utf-8")

    @staticmethod
    def _aggregate_rows(cube_id, version_id, state, aggregates, sample_code, timestamp):
        # Region pointers are audit summaries. Pixel counts remain map-derived.
        geometries = {i: [] for i in aggregates.labels}
        for region in json.loads(state.document_json)["regions"]:
            if region["op"] == "add" and region["class_index"] in geometries:
                geometries[region["class_index"]].append(region["region_id"])
        annotation_rows, spectrum_rows = [], []
        for i, moments in aggregates.labels.items():
            count = int(np.count_nonzero(state.label_map == i))
            annotation_rows.append((str(uuid4()), cube_id, version_id, "sample", state.label_ids[i],
                                    json.dumps({"region_ids": geometries[i]}), count, "manual", timestamp))
            spectrum_rows.append((str(uuid4()), cube_id, version_id, state.label_ids[i], sample_code,
                                  moments.count, f"mean_{i}", f"std_{i}", timestamp))
        return annotation_rows, spectrum_rows

    def read_version(self, version_id):
        with self._lock, connect_database(self.database) as db:
            row = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=?", (str(version_id),)).fetchone()
            if row is None:
                error = DataError("VERSION_NOT_FOUND", "标注版本不存在", version_id=version_id)
                error.status_code = 404
                raise error
            relative = PurePosixPath(row[0])
            if relative.is_absolute() or ".." in relative.parts or "\\" in row[0] or ":" in row[0]:
                raise DataError("INVALID_SNAPSHOT_REF", "快照须为 POSIX 相对路径")
            directory = self.paths.snapshots.joinpath(*relative.parts)
            with np.load(directory / "label_map.npz", allow_pickle=False) as archive:
                label_map = archive["label_map"].copy()
            with np.load(directory / "spectra.npz", allow_pickle=False) as archive:
                spectra = {key: archive[key].copy() for key in archive.files}
            return {"label_map": label_map,
                    "label_index": json.loads((directory / "label_index.json").read_text("utf-8")),
                    "spectra": spectra,
                    "document": json.loads((directory / "annotation.json").read_text("utf-8"))
                    if (directory / "annotation.json").exists() else None}

    def assign_samples(self, project_id, cube_ids, label_id, source):
        request = AssignSamples(project_id=project_id, cube_ids=cube_ids, label_id=str(label_id), source=source)
        with self._lock, connect_database(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            LabelStore.require_project(db, project_id)
            label = LabelStore.require_label(db, label_id)
            if label["project_id"] != project_id:
                raise invalid("label_id", "标签不属于本项目")
            counts = {"assigned": 0, "skipped": 0}
            for cube_id in request.cube_ids:
                row = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (cube_id,)).fetchone()
                if row is None or row[0] != project_id:
                    raise invalid("cube_ids", "样品不存在或不属于本项目")
                inserted = db.execute("INSERT OR IGNORE INTO sample_label (project_id,cube_id,label_id,source,created_at) VALUES (?,?,?,?,?)",
                                      (project_id, cube_id, str(label_id), source, now())).rowcount
                counts["assigned" if inserted else "skipped"] += 1
            return counts

    def sample_labels(self, project_id=None, cube_ids=None):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            if project_id is not None:
                LabelStore.require_project(db, project_id)
            # Join active cubes and project ownership: deleted or mismatched rows
            # never reappear in the read-only material column.
            rows = db.execute("SELECT sl.cube_id,l.* FROM sample_label sl JOIN label l ON l.id=sl.label_id "
                              "AND l.project_id=sl.project_id JOIN dataset_registry d ON d.id=sl.cube_id "
                              "AND d.project_id=sl.project_id WHERE l.deleted_at IS NULL AND (? IS NULL OR sl.project_id=?) "
                              "ORDER BY sl.cube_id,l.sort_order,l.code", (project_id, project_id))
            wanted = None if cube_ids is None else {str(value) for value in cube_ids}
            result = {}
            for row in rows:
                label = dict(row)
                cube_id = label.pop("cube_id")
                if wanted is None or cube_id in wanted:
                    result.setdefault(cube_id, []).append(label)
            return result
