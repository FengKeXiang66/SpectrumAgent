"""Raw DN export, never a computation input. R20 accepts savemat's write copy.

Only one source row is resident during accumulation. Serialization is scipy's
public savemat API, including its unavoidable O(n*B) byte copy.
The requested float32 export can lose precision for float64 DN; source_dtype
retains the original dtype and byte order for downstream provenance.
"""
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
from threading import RLock
from uuid import UUID, uuid4

import numpy as np
from scipy.io import savemat

from backend.database import connect_database
from spectrumagent.annotation.engines.superpixels import row_blocks
from spectrumagent.annotation.labels import now
from spectrumagent.data import DataError
from spectrumagent.preprocess.recipes import input_fingerprint
from spectrumagent.preprocess.run import file_sha256


_WRITE_LOCK = RLock()  # Shared by service instances; fixed per-version temp names.


def missing(code, detail):
    error = DataError(code, detail)
    error.status_code = 404
    return error


class MatStore:
    def __init__(self, registry, paths):
        self.registry, self.paths = registry, paths
        self.database = registry.database

    def discard_invalidated(self, cube_id, version_id):
        """R22: post-commit cleanup is best effort; missing DB row is authority."""
        try:
            with _WRITE_LOCK:
                with connect_database(self.database) as db:
                    # A concurrent rebuild may already have published a new MAT.
                    # Share its lock and never delete that newly valid export.
                    if db.execute("SELECT 1 FROM training_mat WHERE annotation_version_id=?", (str(version_id),)).fetchone():
                        return
                path = self.paths.exports / str(UUID(str(cube_id))) / str(UUID(str(version_id))) / "training_mat.mat"
                if not path.resolve().is_relative_to(self.paths.exports.resolve()):
                    raise ValueError("导出物清理越界")
                path.unlink(missing_ok=True)
        except Exception as error:
            # No local paths, credentials or exception text in cleanup logs.
            logging.getLogger(__name__).warning("MAT_CLEANUP_FAILED version_id=%s reason=%s", version_id, type(error).__name__)

    def _snapshot(self, cube_id, version_id):
        # IDs are path components only after DB ownership and UUID validation.
        cube_id, version_id = str(UUID(str(cube_id))), str(UUID(str(version_id)))
        self.registry.get(cube_id)
        with connect_database(self.database) as db:
            row = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=? AND cube_id=?",
                             (version_id, cube_id)).fetchone()
        if row is None:
            raise missing("VERSION_NOT_FOUND", "标注版本不存在")
        relative = PurePosixPath(row[0])
        if relative.is_absolute() or ".." in relative.parts or "\\" in row[0] or ":" in row[0]:
            raise DataError("INVALID_SNAPSHOT_REF", "快照须为 POSIX 相对路径")
        return self.paths.snapshots.joinpath(*relative.parts)

    def get(self, cube_id, version_id):
        self._snapshot(cube_id, version_id)
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM training_mat WHERE cube_id=? AND annotation_version_id=?",
                             (str(cube_id), str(version_id))).fetchone()
        if row is None:
            raise missing("MAT_NOT_FOUND", "训练 MAT 不存在")
        result = dict(row)
        self.file(result)
        return result

    def file(self, row):
        relative = PurePosixPath(row["relative_path"])
        path = self.paths.root.joinpath(*relative.parts)
        if relative.is_absolute() or ".." in relative.parts or "\\" in row["relative_path"] or ":" in row["relative_path"] or not path.resolve().is_relative_to(self.paths.exports.resolve()):
            raise DataError("INVALID_EXPORT_REF", "导出物须位于 exports 内")
        if not path.is_file():
            raise missing("MAT_NOT_FOUND", "训练 MAT 不存在")
        return path

    def rebuild(self, cube_id, version_id):
        with _WRITE_LOCK:
            snapshot = self._snapshot(cube_id, version_id)
            with np.load(snapshot / "label_map.npz", allow_pickle=False) as archive:
                label_map = archive["label_map"].copy()
            return self.generate(cube_id, version_id, label_map)

    def generate(self, cube_id, version_id, label_map):
        with _WRITE_LOCK:
            try:
                return self._generate(str(cube_id), str(version_id), label_map)
            except Exception as error:
                raise DataError("MAT_GENERATION_FAILED", f"训练 MAT 生成失败：{error}") from error

    def _generate(self, cube_id, version_id, label_map):
        snapshot = self._snapshot(cube_id, version_id)
        label_index = json.loads((snapshot / "label_index.json").read_text("utf-8"))
        dataset, _ = self.registry.readable(cube_id, raw=True)
        if label_map.dtype != np.int32 or label_map.shape != dataset.shape[:2] or np.any(label_map < -2):
            raise DataError("INVALID_LABEL_MAP", "原始立方体与标注位图不同形或编码非法")
        if any(str(i) not in label_index for i in np.unique(label_map[label_map >= 0])):
            raise DataError("LABEL_INDEX_MISMATCH", "标注位图引用未知类别")
        files = {Path(dataset.header_path), Path(dataset.data_path)}
        root = Path(os.path.commonpath([str(path.parent) for path in files]))
        hashes = {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(files)}
        count, bands = int(np.count_nonzero(label_map >= 0)), dataset.shape[2]
        timestamp = now()
        fingerprint = input_fingerprint(cube_id, hashes, version_id, count)
        directory = self.paths.exports / cube_id / version_id
        temporary = directory / ".tmp"
        directory.mkdir(parents=True, exist_ok=True)
        temporary.mkdir()
        maps = {}
        target = directory / "training_mat.mat"
        backup = temporary / "previous.mat"
        published = False
        try:
            # Empty exports still have precisely typed zero-row arrays.
            for key, dtype, shape in [("spectra", np.float32, (count, bands)),
                                      ("labels", np.int32, (count,)), ("rows", np.int32, (count,)),
                                      ("cols", np.int32, (count,))]:
                maps[key] = np.lib.format.open_memmap(temporary / f"{key}.npy", mode="w+", dtype=dtype, shape=shape) if count else np.empty(shape, dtype=dtype)
            position, source_dtype = 0, None
            # A single row is an algorithmic bound, including tiny test cubes.
            for l0, l1, block in row_blocks(dataset, 1):
                source_dtype = block.dtype.str
                rr, cc = np.nonzero(label_map[l0:l1] >= 0)
                end = position + len(rr)
                maps["spectra"][position:end] = block[rr, cc]
                maps["labels"][position:end] = label_map[l0 + rr, cc]
                maps["rows"][position:end], maps["cols"][position:end] = l0 + rr, cc
                position = end
                del block
            metadata = {"cube_id": cube_id, "annotation_version_id": version_id,
                        "input_fingerprint": fingerprint, "n_spectra": count, "n_bands": bands,
                        "n_classes": len(label_index), "dtype_note": "raw_dn_pre_b01",
                        "schema_version": 1, "created_at": timestamp}
            savemat(temporary / "training_mat.mat", {**maps, "source_dtype": source_dtype,
                    # Numeric JSON object keys cannot be MATLAB struct fields.
                    "label_index": json.dumps(label_index, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    "wavelengths": np.asarray(dataset.wavelengths, dtype=np.float64),
                    "has_wavelengths": bool(dataset.wavelengths), "metadata": metadata}, do_compression=False)
            digest = file_sha256(temporary / "training_mat.mat")
            relative = target.relative_to(self.paths.root).as_posix()
            with connect_database(self.database) as db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute("SELECT id FROM training_mat WHERE annotation_version_id=?", (version_id,)).fetchone()
                identifier = previous[0] if previous else str(uuid4())
                row = {"id": identifier, "cube_id": cube_id, "annotation_version_id": version_id,
                       "relative_path": relative, "sha256": digest, "n_spectra": count,
                       "n_bands": bands, "n_classes": len(label_index), "input_fingerprint": fingerprint,
                       "created_at": timestamp}
                if target.exists():
                    os.replace(target, backup)
                os.replace(temporary / "training_mat.mat", target)
                published = True
                if previous:
                    db.execute("UPDATE training_mat SET cube_id=:cube_id,relative_path=:relative_path,sha256=:sha256,"
                               "n_spectra=:n_spectra,n_bands=:n_bands,n_classes=:n_classes,input_fingerprint=:input_fingerprint,"
                               "created_at=:created_at WHERE id=:id", row)
                else:
                    db.execute("INSERT INTO training_mat (id,cube_id,annotation_version_id,relative_path,sha256,n_spectra,n_bands,n_classes,input_fingerprint,created_at) "
                               "VALUES (:id,:cube_id,:annotation_version_id,:relative_path,:sha256,:n_spectra,:n_bands,:n_classes,:input_fingerprint,:created_at)", row)
            return row
        except BaseException:
            if published:
                target.unlink()
            if backup.exists():
                os.replace(backup, target)
            raise
        finally:
            for array in maps.values():
                if isinstance(array, np.memmap):
                    array._mmap.close()
            maps.clear()
            # Validated UUID children of exports, never caller-composed cleanup.
            if not temporary.resolve().is_relative_to(self.paths.exports.resolve()):
                raise ValueError("临时目录越界")
            shutil.rmtree(temporary)
