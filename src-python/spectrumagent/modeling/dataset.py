"""Recompute recipes from bounded pixel reads; MAT and mean spectra are not inputs."""
import json
from pathlib import Path, PurePosixPath
import sqlite3
from time import perf_counter

import numpy as np

from backend.database import connect_database
from spectrumagent.annotation.engines.superpixels import ReadableRows, row_blocks
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.run import file_sha256
from . import ModelingError


def _inputs(registry, *, cube_ids, annotation_version_ids, preprocess_run_ids, target, task="classification"):
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
    if task != "classification" or target != "label":
        raise ModelingError("TARGET_UNSUPPORTED", "13.1 仅支持分类 label；连续量来源须在13.2前另行裁定")
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
