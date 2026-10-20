"""In-memory manual annotation and bounded sample aggregation (TASK-04 §5.4).

The pixel map is authoritative. SQLite holds one aggregate per present label,
never editing history; snapshots own their immutable label-index mapping.
"""
from collections import deque
from dataclasses import dataclass, field
import json
import os
from pathlib import PurePosixPath
import shutil
from threading import RLock
from time import perf_counter
from uuid import uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from .engines.superpixels import ReadableRows, row_blocks
from .labels import now


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
    # §5.4 requires >=5; no operation history is persisted.
    undo_stack: deque = field(default_factory=lambda: deque(maxlen=5))


class SessionStore:
    def __init__(self, registry, paths):
        self.registry, self.paths = registry, paths
        self.database = registry.database
        self._states = {}
        self._lock = RLock()

    def _label_ids(self, cube_id):
        cube_id = str(cube_id)
        self.registry.get(cube_id)
        with connect_database(self.database) as db:
            rows = db.execute("SELECT l.id FROM label l JOIN dataset_registry d "
                              "ON d.project_id=l.project_id WHERE d.id=? "
                              "ORDER BY l.sort_order ASC,l.code ASC", (cube_id,)).fetchall()
        return tuple(row[0] for row in rows)

    def _state(self, cube_id):
        cube_id = str(cube_id)
        ids = self._label_ids(cube_id)
        state = self._states.get(cube_id)
        if state is None:
            dataset, _ = self.registry.readable(cube_id, raw=False)
            state = WorkingState(np.full(dataset.shape[:2], -1, dtype=np.int32), ids)
            self._states[cube_id] = state
        elif state.label_ids != ids:
            # New labels can change indices. Preserve pixel identity by label ID,
            # including undo maps; saved versions are never touched.
            positions = {label_id: i for i, label_id in enumerate(ids)}
            def remap(old):
                result = old.copy()
                for i, label_id in enumerate(state.label_ids):
                    if label_id not in positions:
                        raise DataError("LABEL_REMOVED", "工作态引用的标签已被删除", label_id=label_id)
                    result[old == i] = positions[label_id]
                return result
            state.label_map = remap(state.label_map)
            state.undo_stack = deque((remap(old) for old in state.undo_stack), maxlen=5)
            state.label_ids = ids
        return state

    def working(self, cube_id):
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

    def edit(self, cube_id, mask, *, action, label_id=None):
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
            state.undo_stack.append(state.label_map.copy())
            state.label_map[mask] = value
            if action != "erase" and state.segments is not None:
                # Consume explicitly selected candidates; generation belongs to 10.3.5.
                state.candidates[:] = [candidate for candidate in state.candidates
                                      if not np.all(mask[np.isin(state.segments, candidate["superpixels"])])]
            return self.working(cube_id)

    def undo(self, cube_id):
        with self._lock:
            state = self._state(cube_id)
            if not state.undo_stack:
                raise AnnotationConflict("撤销栈为空")
            state.label_map = state.undo_stack.pop().copy()
            return self.working(cube_id)

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

    def save(self, cube_id, *, overwrite=False, confirm=False, note: str | None = None):
        if note is not None and (not isinstance(note, str) or len(note) > 2000):
            raise DataError("INVALID_VERSION_NOTE", "版本备注须为不超过 2000 字符的文本")
        cube_id = str(cube_id)
        with self._lock:
            state = self._state(cube_id)
            self._require_segments(state)
            with connect_database(self.database) as db:
                latest = db.execute("SELECT id,version_no,created_at FROM annotation_version "
                                    "WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,)).fetchone()
            if overwrite and (not confirm or latest is None):
                raise AnnotationConflict("覆写须已有版本且显式 confirm；仅覆盖最新版本")
            started = perf_counter()
            dataset, _ = self.registry.get(cube_id)
            aggregates = aggregate_spectra(self.registry, cube_id, state.label_map,
                                           block_size=state.params["block_size"], segments=state.segments)
            from .quality import validate
            quality = validate(self.registry, cube_id, state.label_map, state.segments,
                               state.label_ids, state.params, aggregates=aggregates)
            timestamp = now()
            version_id = latest[0] if overwrite else str(uuid4())
            version_no = latest[1] if overwrite else (latest[1] + 1 if latest else 1)
            created = latest[2] if overwrite else timestamp
            note = (json.dumps({"event": "overwrite" if overwrite else "save", "at": timestamp,
                                **({"text": note} if note is not None else {})})
                    if overwrite or note is not None else None)
            annotation_rows, spectrum_rows = self._aggregate_rows(
                cube_id, version_id, state, aggregates, dataset.name, timestamp)
            relative = PurePosixPath(cube_id, f"v{version_no}").as_posix()
            directory = self.paths.snapshots / cube_id / f"v{version_no}"
            directory.parent.mkdir(parents=True, exist_ok=True)
            temporary = directory.with_name(directory.name + f".{uuid4().hex}.tmp")
            backup = directory.with_name(directory.name + f".{uuid4().hex}.backup.tmp")
            temporary.mkdir()
            published = False
            try:
                self._write_snapshot(temporary, state, aggregates)
                transaction_started = perf_counter()
                with connect_database(self.database) as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute("SELECT id,version_no,created_at FROM annotation_version "
                                         "WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,)).fetchone()
                    if current != latest:
                        raise AnnotationConflict("保存期间最新版本已改变，请重试")
                    if directory.exists():
                        os.replace(directory, backup)
                    os.replace(temporary, directory)
                    published = True
                    values = (relative, int(state.label_map.size), int(np.count_nonzero(state.label_map >= 0)),
                              0, json.dumps(state.params), note)
                    if overwrite:
                        db.execute("DELETE FROM annotation WHERE version_id=?", (version_id,))
                        db.execute("DELETE FROM sample_spectrum WHERE version_id=?", (version_id,))
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
                transaction_seconds = perf_counter() - transaction_started
            except BaseException:
                if published:
                    shutil.rmtree(directory)
                if backup.exists():
                    os.replace(backup, directory)
                raise
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
            if backup.exists():
                shutil.rmtree(backup)
            return {"id": version_id, "cube_id": cube_id, "version_no": version_no,
                    "snapshot_ref": relative, "created_at": created, "note": note,
                    "quality": quality, "elapsed_seconds": perf_counter() - started,
                    "transaction_seconds": transaction_seconds}

    @staticmethod
    def _write_snapshot(directory, state, aggregates):
        # A sibling .tmp directory is published with os.replace before DB commit.
        np.savez_compressed(directory / "label_map.npz", label_map=state.label_map)
        (directory / "label_index.json").write_text(json.dumps(
            {str(i): label_id for i, label_id in enumerate(state.label_ids)}), encoding="utf-8")
        spectra = {}
        for i, moments in aggregates.labels.items():
            spectra[f"mean_{i}"] = moments.mean.astype(np.float64)
            spectra[f"std_{i}"] = moments.std.astype(np.float64)
        np.savez_compressed(directory / "spectra.npz", **spectra)

    @staticmethod
    def _aggregate_rows(cube_id, version_id, state, aggregates, sample_code, timestamp):
        # Full-coverage geometry only. Pixel counts ALWAYS come from label_map.
        geometries = {i: [] for i in aggregates.labels}
        for segment in np.unique(state.segments):
            labels = np.unique(state.label_map[state.segments == segment])
            if len(labels) == 1 and labels[0] >= 0:
                geometries[int(labels[0])].append(int(segment))
        annotation_rows, spectrum_rows = [], []
        for i, moments in aggregates.labels.items():
            count = int(np.count_nonzero(state.label_map == i))
            annotation_rows.append((str(uuid4()), cube_id, version_id, "sample", state.label_ids[i],
                                    json.dumps({"superpixels": geometries[i]}), count, "manual", timestamp))
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
                    "spectra": spectra}
