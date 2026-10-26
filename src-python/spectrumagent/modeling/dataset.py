"""Recompute recipes from bounded pixel reads; MAT and mean spectra are not inputs."""
import json
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import io
import math
from pathlib import Path, PurePosixPath
import sqlite3
from threading import RLock
from time import perf_counter
from uuid import uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.annotation.engines.superpixels import ReadableRows, row_blocks
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.run import file_sha256
from . import ModelingError


def _inputs(registry, *, cube_ids, annotation_version_ids, preprocess_run_ids, target, task="classification", target_schema_id=None):
    if not cube_ids or len(cube_ids) != len(annotation_version_ids) or len(cube_ids) != len(preprocess_run_ids):
        raise ModelingError("ARGUMENT_LENGTH_MISMATCH", "三个引用数组须等长且非空")
    rows = []
    with connect_database(registry.database) as db:
        db.row_factory = sqlite3.Row
        # Check every version before checking any preprocess run (R7 ordering).
        for cube, version in zip(cube_ids, annotation_version_ids):
            annotation = db.execute("SELECT * FROM annotation_version WHERE id=?", (str(version),)).fetchone()
            if annotation is None or annotation["cube_id"] != str(cube):
                raise ModelingError("VERSION_CUBE_MISMATCH", "标注版本不属于对应数据集")
            rows.append({"cube_id": str(cube), "annotation": dict(annotation)})
        for row, identifier in zip(rows, preprocess_run_ids):
            run = db.execute("SELECT * FROM preprocess_run WHERE id=?", (str(identifier),)).fetchone()
            if run is None or run["cube_id"] != row["cube_id"] or run["status"] != "succeeded":
                raise ModelingError("PREPROCESS_RUN_NOT_READY", "对应预处理 run 必须属于该数据集且已成功")
            recipe = db.execute("SELECT pipeline FROM preprocess_recipe_version WHERE id=?", (run["recipe_version_id"],)).fetchone()
            if recipe is None:
                raise ModelingError("PREPROCESS_RUN_NOT_READY", "预处理配方版本不存在")
            row.update(run=dict(run), pipeline=json.loads(recipe[0]))
    if task == "regression":
        if not target_schema_id:
            raise ModelingError("TARGET_SCHEMA_REQUIRED", "回归须提供连续字段 target_schema_id")
        with connect_database(registry.database) as db:
            schema = db.execute("SELECT project_id,tree_path FROM label_schema WHERE id=? AND field_type='continuous'",
                                (target_schema_id,)).fetchone()
            if schema is None:
                raise ModelingError("INVALID_TARGET_SCHEMA", "目标必须是连续字段")
            targets = dict(db.execute("SELECT cube_id,value FROM sample_target WHERE schema_id=? AND project_id=?",
                                      (target_schema_id, schema[0])))
        rows = [dict(row, y=targets[row["cube_id"]], target=schema[1]) for row in rows if row["cube_id"] in targets]
        if not rows:
            raise ModelingError("NO_TARGETS", "引用数据集尚无该连续字段的取值")
    elif task != "classification" or target != "label":
        raise ModelingError("TARGET_UNSUPPORTED", "分类仅支持 label")
    return rows


def _build(registry, paths, rows):
    started = perf_counter()
    operators = builtin_registry()
    xs, ys, gs, metadata = [], [], [], []
    cube_groups = {cube: i for i, cube in enumerate(dict.fromkeys(row["cube_id"] for row in rows))}
    for row in rows:
        cube = row["cube_id"]
        dataset, _ = registry.readable(cube, raw=False)
        shape, wavelengths = dataset.shape, dataset.wavelengths
        hashes = {"header": file_sha256(Path(dataset.header_path)), "data": file_sha256(Path(dataset.data_path))}
        del dataset
        ref = row["annotation"]["snapshot_ref"]
        relative = PurePosixPath(ref)
        base = paths.snapshots.resolve()
        folder = base.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in ref or ":" in ref or not folder.is_relative_to(base):
            raise ModelingError("INVALID_SNAPSHOT_REF", "标注快照须位于应用快照目录")
        try:
            with np.load(folder / "label_map.npz", allow_pickle=False) as archive:
                label_map = archive["label_map"].copy()
        except (OSError, ValueError, KeyError) as error:
            raise ModelingError("INVALID_SNAPSHOT_REF", "无法读取确认版 label_map") from error
        if label_map.shape != shape[:2]:
            raise ModelingError("LABEL_MAP_SHAPE_MISMATCH", "label_map 形状与数据集不一致")
        if label_map.dtype.kind not in "iu" or np.any(label_map < -2):
            raise ModelingError("INVALID_LABEL_MAP", "标签须为整数三态编码")
        selected_count = int(np.count_nonzero(label_map >= 0))
        if not selected_count:
            raise ModelingError("NO_LABELED_PIXELS", "确认版没有可训练的已标像素")
        x = np.empty((selected_count, shape[2]), dtype=np.float64)
        y = np.empty(selected_count, dtype=np.int64)
        offset = 0
        # raw=False 等价于 B01 的 scale/passthrough（header.scale 默认 1.0）。
        # preprocess 不传参考谱，reference 不可达；将来 preprocess 支持参考谱时，
        # 此处须同步改为 raw=True + 显式 reflectance。
        for first, last, block in row_blocks(ReadableRows(registry, cube, shape), 32):
            labels = label_map[first:last].ravel()
            mask = labels >= 0
            count = int(mask.sum())
            x[offset:offset+count] = block.reshape(-1, shape[2])[mask]
            y[offset:offset+count] = labels[mask]
            offset += count
            del block
        # Each cube is fitted as a whole, explicitly acknowledged by leak.py.
        processed = operators.run(x, row["pipeline"], wavelengths=wavelengths or None).spectra
        if not np.isfinite(processed).all():
            raise ModelingError("NON_FINITE_SPECTRA", "预处理结果含非有限值")
        xs.append(np.asarray(processed, dtype=np.float64))
        ys.append(y)
        gs.append(np.full(selected_count, cube_groups[cube], dtype=np.int32))
        metadata.append({"cube_id": cube, "group": cube_groups[cube], "n_samples": selected_count,
                         "input_fingerprint": row["run"]["input_fingerprint"], "source_hashes": hashes,
                         "pipeline": row["pipeline"]})
        del x, processed, label_map
    if len({x.shape[1] for x in xs}) != 1:
        raise ModelingError("FEATURE_COUNT_MISMATCH", "各数据集预处理后的特征数须相同")
    return {"X": np.concatenate(xs), "y": np.concatenate(ys), "groups": np.concatenate(gs),
            "meta": {"cubes": metadata, "n_samples": sum(len(y) for y in ys), "n_features": xs[0].shape[1],
                     "build_seconds": perf_counter() - started}}


def build_training_set(registry, paths, *, cube_ids, annotation_version_ids, preprocess_run_ids, target):
    return _build(registry, paths, _inputs(registry, cube_ids=cube_ids,
                  annotation_version_ids=annotation_version_ids, preprocess_run_ids=preprocess_run_ids, target=target))


def build_sample_training_set(registry, paths, *, preprocess_run_ids, target_schema_id):
    """One bounded sum/count per cube; snapshot indices, never live label ordering."""
    with connect_database(registry.database) as db:
        references = [db.execute("SELECT cube_id,annotation_version_id FROM preprocess_run WHERE id=?", (identifier,)).fetchone()
                      for identifier in preprocess_run_ids]
    if not references or any(row is None for row in references):
        raise ModelingError("PREPROCESS_RUN_NOT_READY", "须提供已成功的预处理 run")
    if len({row[0] for row in references}) != len(references):
        raise ModelingError("DUPLICATE_CUBE", "每个数据集只能提供一个预处理 run")
    rows = _inputs(registry, cube_ids=[r[0] for r in references], annotation_version_ids=[r[1] for r in references],
                   preprocess_run_ids=preprocess_run_ids, target="", task="regression", target_schema_id=target_schema_id)
    means, cubes, axes = [], [], []
    for row in rows:
        cube = row["cube_id"]
        dataset, _ = registry.readable(cube, raw=False)
        shape = dataset.shape
        axes.append(np.asarray(dataset.wavelengths, dtype=np.float64))
        ref = row["annotation"]["snapshot_ref"]
        relative, base = PurePosixPath(ref), paths.snapshots.resolve()
        folder = base.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in ref or ":" in ref or not folder.is_relative_to(base):
            raise ModelingError("INVALID_SNAPSHOT_REF", "标注快照须位于应用快照目录")
        try:
            with np.load(folder / "label_map.npz", allow_pickle=False) as archive:
                labels = archive["label_map"].copy()
            index = json.loads((folder / "label_index.json").read_text("utf-8"))
        except (OSError, ValueError, KeyError) as error:
            raise ModelingError("INVALID_SNAPSHOT_REF", "无法读取版本 label_map/label_index") from error
        if labels.shape != shape[:2] or labels.dtype.kind not in "iu" or np.any(labels < -2):
            raise ModelingError("LABEL_MAP_SHAPE_MISMATCH", "label_map 与数据集不匹配")
        if not isinstance(index, dict) or any(str(i) not in index for i in np.unique(labels[labels >= 0])):
            raise ModelingError("INVALID_SNAPSHOT_REF", "label_index 缺少已标像素映射")
        with connect_database(registry.database) as db:
            backgrounds = {identifier for identifier, in db.execute("SELECT id FROM label WHERE is_background=1")}
        bg_indices = [int(i) for i, identifier in index.items() if identifier in backgrounds]
        total, count = np.zeros(shape[2], dtype=np.float64), 0
        for first, last, block in row_blocks(ReadableRows(registry, cube, shape), 32):
            mask = labels[first:last] >= 0
            if bg_indices:
                mask &= ~np.isin(labels[first:last], bg_indices)
            total += block[mask].sum(axis=0, dtype=np.float64)
            count += int(mask.sum())
        if count == 0:
            raise ModelingError("NO_FOREGROUND_PIXELS", "版本中没有可用的已标前景像素", cube_id=cube)
        means.append(total/count)
        cubes.append({"cube_id": cube, "n_pixels_used": count, "annotation_version_id": row["annotation"]["id"],
                      "input_fingerprint": row["run"]["input_fingerprint"], "pipeline": row["pipeline"],
                      "source_hashes": {"header": file_sha256(Path(dataset.header_path)), "data": file_sha256(Path(dataset.data_path))}})
    if len({json.dumps(row["pipeline"], sort_keys=True) for row in rows}) != 1:
        raise ModelingError("RECIPE_MISMATCH", "整样谱建模须采用相同配方步骤和参数")
    raw = np.stack(means)
    # np.stack enforces equal band counts, not equal wavelength scales: equal
    # band counts with different axes would silently run SG/derivatives on the
    # wrong scale. All cubes must share one axis; all-unknown stays uniform.
    if len({axis.tobytes() for axis in axes}) != 1:
        raise ModelingError("WAVELENGTH_AXIS_MISMATCH", "各数据集波长轴刻度须一致")
    # Fit-on-apply across sample means is explicitly retained in leak_report.
    processed = builtin_registry().run(raw, rows[0]["pipeline"], wavelengths=axes[0] if axes[0].size else None).spectra
    if not np.isfinite(processed).all():
        raise ModelingError("NON_FINITE_SPECTRA", "整样谱预处理含非有限值")
    return {"X": processed, "X_raw": raw, "y": np.asarray([row["y"] for row in rows], dtype=float),
            "groups": np.asarray([row["cube_id"] for row in rows]), "target": rows[0]["target"],
            "preprocess_run_ids": [row["run"]["id"] for row in rows],
            "meta": {"cubes": cubes, "n_samples": len(rows), "n_pixels_used": sum(c["n_pixels_used"] for c in cubes),
                     "n_features": processed.shape[1], "excluded_without_target": len(references)-len(rows)}}


class SampleTargets:
    """Continuous values keyed by project + schema tree_path; IDs remain FKs."""
    def __init__(self, database):
        self.database, self.lock = database, RLock()

    @staticmethod
    def _validate(db, cube_id, schema_id, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ModelingError("INVALID_TARGET_VALUE", "连续量须为有限数值")
        row = db.execute("SELECT d.project_id,s.field_type,s.config FROM dataset_registry d JOIN label_schema s ON s.project_id=d.project_id "
                         "WHERE d.id=? AND s.id=?", (cube_id, schema_id)).fetchone()
        if row is None:
            raise ModelingError("INVALID_TARGET_SCHEMA", "数据集与连续字段须属于同一项目")
        if row[1] != "continuous":
            raise ModelingError("NON_CONTINUOUS_SCHEMA", "目标字段必须为 continuous")
        config = json.loads(row[2]) if row[2] else {}
        if not isinstance(config, dict) or any(key in config and (isinstance(config[key], bool) or not isinstance(config[key], (int,float)) or not math.isfinite(config[key])) for key in ("min","max")):
            raise ModelingError("INVALID_TARGET_SCHEMA_CONFIG", "连续字段 min/max 配置须为有限数值")
        if "min" in config and "max" in config and config["min"] > config["max"]:
            raise ModelingError("INVALID_TARGET_SCHEMA_CONFIG", "连续字段 min 大于 max")
        if value < config.get("min", -math.inf) or value > config.get("max", math.inf):
            raise ModelingError("TARGET_OUT_OF_RANGE", "连续量超出字段配置值域", minimum=config.get("min"), maximum=config.get("max"))
        return row[0]

    @staticmethod
    def _write(db, project_id, cube_id, schema_id, value, source):
        db.execute("INSERT INTO sample_target VALUES (?,?,?,?,?,?,?) ON CONFLICT(cube_id,schema_id) DO UPDATE SET "
                   "value=excluded.value,source=excluded.source,created_at=excluded.created_at",
                   (str(uuid4()), project_id, cube_id, schema_id, float(value), source, datetime.now(timezone.utc).isoformat()))

    def put(self, cube_id, schema_id, value):
        with self.lock, connect_database(self.database, timeout=10) as db:
            project = self._validate(db, cube_id, schema_id, value)
            self._write(db, project, cube_id, schema_id, value, "annotation")
        return next(row for row in self.list(project) if row["cube_id"] == cube_id and row["schema_id"] == schema_id)

    def list(self, project_id=None):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT t.*,s.tree_path FROM sample_target t JOIN label_schema s ON s.id=t.schema_id "
                    + ("WHERE t.project_id=? " if project_id else "") + "ORDER BY t.cube_id,t.schema_id", (project_id,) if project_id else ())]

    def import_csv(self, project_id, text, *, overwrite=False):
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        try:
            if reader.fieldnames != ["cube_name", "schema", "value"]:
                raise ModelingError("INVALID_TARGET_CSV", "CSV 表头须为 cube_name,schema,value")
            items = list(reader)
        except csv.Error:
            raise ModelingError("INVALID_TARGET_CSV", "CSV 格式错误") from None
        unmatched, pending, invalid, accepted = [], [], [], []
        unknown, out_of_range = [], []
        with self.lock, connect_database(self.database, timeout=10) as db:
            names = defaultdict(list)
            for identifier, payload in db.execute("SELECT id,payload FROM dataset_registry WHERE project_id=?", (project_id,)):
                names[json.loads(payload)["name"]].append(identifier)
            schemas = {path: (identifier, name) for identifier,path,name in db.execute("SELECT id,tree_path,name FROM label_schema WHERE project_id=?", (project_id,))}
            keyed = []
            for number, item in enumerate(items, 2):
                match = names.get(item.get("cube_name"), [])
                if len(match) != 1:
                    unmatched.append({"line": number, "cube_name": item.get("cube_name"), "reason": "cube_name 未唯一关联"})
                    continue
                field = item.get("schema")
                resolved = schemas.get(field)
                if resolved is None:
                    candidates = [path for path,(_,name) in schemas.items() if name == field]
                    if len(candidates) > 1:
                        invalid.append({"line": number, "error": "AMBIGUOUS_SCHEMA", "candidates": sorted(candidates)})
                        continue
                    if not candidates:
                        unknown.append({"line": number, "schema": field, "error": "UNKNOWN_SCHEMA"})
                        continue
                    resolved = schemas[candidates[0]]
                schema = resolved[0]
                if None in item or any(item.get(key) is None for key in ("cube_name","schema","value")):
                    invalid.append({"line": number, "error": "INVALID_TARGET_CSV"})
                    continue
                try:
                    value = float(item["value"])
                    self._validate(db, match[0], schema, value)
                except ModelingError as error:
                    destination = out_of_range if error.code == "TARGET_OUT_OF_RANGE" else invalid
                    destination.append({"line": number, "error": error.code, "reason": error.payload.detail})
                    continue
                except (ValueError, TypeError):
                    invalid.append({"line": number, "error": "INVALID_TARGET_VALUE", "reason": "value 须为有限数值"})
                    continue
                keyed.append((number, match[0], schema, value))
            counts = Counter((cube, schema) for _, cube, schema, _ in keyed)
            for number, cube, schema, value in keyed:
                existing = db.execute("SELECT 1 FROM sample_target WHERE cube_id=? AND schema_id=?", (cube, schema)).fetchone()
                if not overwrite and (counts[cube, schema] > 1 or existing):
                    pending.append({"line": number, "cube_id": cube, "schema_id": schema, "value": value})
                    continue
                self._write(db, project_id, cube, schema, value, "import")
                accepted.append({"line": number, "cube_id": cube, "schema_id": schema})
        return {"imported": len(accepted), "unmatched": unmatched, "pending_confirmation": pending, "invalid": invalid,
                "unknown_fields": unknown, "out_of_range": out_of_range}
