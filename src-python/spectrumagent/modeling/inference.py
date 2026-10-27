"""Bounded pixel inference with frozen, registration-reconstructed calibration."""
import base64
from copy import deepcopy
import json
from pathlib import PurePosixPath
import sqlite3
import struct
from uuid import uuid4
import zlib

import numpy as np

from backend.database import connect_database
from spectrumagent.annotation.engines.superpixels import ReadableRows, row_blocks
from spectrumagent.data import DataError
from spectrumagent.display.falsecolor import concentration_colors, CONCENTRATION_PALETTE
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.operators.pca import transform
from spectrumagent.preprocess.registry import validate
from spectrumagent.preprocess.run import file_sha256
from . import ModelingError
from .registry import ModelRegistry, axis_sha256, encode, missing, normalized_pipeline, now

WARNING = "模型训练粒度＝样品均值谱；像素级预测为域外外推，仅表示含量空间分布趋势"


def mismatch():
    return ModelingError("CALIBRATION_MISMATCH", "标定缺失、维度或算子版本与配方不一致")


def finite(value):
    if not np.isfinite(value).all():
        raise ModelingError("NON_FINITE_SPECTRA", "输入谱或变换、预测结果含非有限值")
    return value


def apply_with_calibration(calibration, pipeline, block):
    """Never call a fit entry for any of the five cross-sample fitted operators.

    Fixed one-row matrix transforms also avoid BLAS batch-size rounding changes.
    """
    result = finite(np.asarray(block, dtype=np.float64))
    if result.ndim != 2 or 0 in result.shape:
        raise ModelingError("FEATURE_COUNT_MISMATCH", "需要非空二维像素谱")
    operators = builtin_registry()
    try:
        expected = normalized_pipeline(pipeline)
        if (calibration["protocol"] != 1 or calibration["pipeline"] != expected
                or result.shape[1] != calibration["input_n_features"]
                or len(calibration["steps"]) != len(expected["steps"])):
            raise mismatch()
        for step, saved in zip(operators.parse_pipeline(pipeline).steps, calibration["steps"]):
            entry = operators.resolve(step.op, step.version)
            params = json.loads(encode(validate(entry.model, step.params, "params").model_dump()))
            if any(saved.get(key) != value for key, value in
                   (("op", step.op), ("version", step.version), ("params", params))):
                raise mismatch()
            meta = saved["meta"]
            if step.op == "standardize" and params["method"] in ("standard", "minmax"):
                fitted = meta["fitted"]
                if len(fitted) != result.shape[1]:
                    raise mismatch()
                if params["method"] == "standard":
                    offset = np.asarray([row["mean"] for row in fitted])
                    scale = np.asarray([row["std"] for row in fitted])
                else:
                    offset = np.asarray([row["min"] for row in fitted])
                    scale = np.asarray([row["max"] for row in fitted]) - offset
                if not np.isfinite(offset).all() or not np.isfinite(scale).all() or np.any(scale < 0):
                    raise mismatch()
                zero = scale == 0
                if zero.any() and params["zero_std"] == "error":
                    raise mismatch()
                with np.errstate(divide="ignore", invalid="ignore"):
                    result = (result - offset) / scale
                if zero.any():
                    result[:, zero] = 0.0 if params["zero_std"] == "zeros" else np.nan
            elif step.op in ("pca", "mnf", "ica"):
                mean, loadings = np.asarray(meta["mean"]), np.asarray(meta["loadings"])
                if (mean.shape != (result.shape[1],) or loadings.ndim != 2
                        or loadings.shape[0] != result.shape[1] or loadings.shape[1] == 0
                        or not np.isfinite(mean).all() or not np.isfinite(loadings).all()):
                    raise mismatch()
                result = np.concatenate([transform(row[None, :], mean, loadings) for row in result])
            else:
                # These entries operate per spectrum; fixed row calls make the
                # numerical result independent of the outer IO block size.
                outputs = []
                for row in result:
                    output = entry.impl(row[None, :], deepcopy(params))
                    outputs.append(output[0] if isinstance(output, tuple) else output)
                result = np.concatenate(outputs)
            if result.ndim != 2 or result.shape[0] != len(block) or 0 in result.shape:
                raise mismatch()
            finite(result)
    except ModelingError:
        raise
    except (DataError, KeyError, TypeError, ValueError, IndexError) as error:
        raise mismatch() from error
    return result


def predict(x, model):
    """PLS 1.9.1 formula, flattened and independent of IO block dimensions."""
    try:
        x = finite(np.asarray(x, dtype=np.float64))
        coef, mean, intercept = (np.asarray(model[key], dtype=np.float64)
                                 for key in ("coef", "x_mean", "intercept"))
        if (x.ndim != 2 or coef.shape != (1, x.shape[1])
                or mean.shape != (x.shape[1],) or intercept.shape != (1,)):
            raise ModelingError("FEATURE_COUNT_MISMATCH", "像素特征数与模型不一致")
        finite(coef); finite(mean); finite(intercept)
        return finite(np.asarray([((row - mean) @ coef.T + intercept).ravel()[0] for row in x])).ravel()
    except (KeyError, TypeError, ValueError) as error:
        raise ModelingError("INVALID_MODEL_ARTIFACT", "模型系数产物无效") from error


def png_rgb(rgb):
    height, width, _ = rgb.shape
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    rows = b"".join(b"\x00" + row.tobytes() for row in rgb)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return base64.b64encode(data).decode("ascii")


class InferenceRuns:
    def __init__(self, registry, paths):
        self.registry, self.paths, self.database = registry, paths, registry.database
        self.models = ModelRegistry(registry, paths)

    def get(self, identifier):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM inference_run WHERE id=?", (str(identifier),)).fetchone()
        if row is None:
            raise missing("INFERENCE_NOT_FOUND", "推理记录不存在")
        result = dict(row)
        for key in ("stats", "error"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def map(self, identifier):
        run = self.get(identifier)
        if run["status"] != "succeeded":
            raise ModelingError("INFERENCE_NOT_READY", "推理尚未成功")
        with connect_database(self.database) as db:
            row = db.execute("SELECT relative_path,sha256 FROM inference_artifact WHERE run_id=? AND kind='map'",
                             (str(identifier),)).fetchone()
        if row is None:
            raise missing("ARTIFACT_NOT_FOUND", "含量图不存在")
        base = self.paths.root.resolve()
        relative = PurePosixPath(row[0])
        path = base.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in row[0] or ":" in row[0] or not path.is_relative_to(base):
            raise ModelingError("INVALID_ARTIFACT", "含量图引用非法")
        if not path.is_file() or file_sha256(path) != row[1]:
            raise ModelingError("INVALID_ARTIFACT", "含量图缺失或校验失败")
        if path.stat().st_size > 8 * 1024 * 1024 - 1024:
            raise ModelingError("MAP_TOO_LARGE", "含量图超过桌面显示上限，统计结果仍可查看")
        return json.loads(path.read_text("utf-8"))

    def _prepare(self, model_id, cube_id, preprocess_run_id, annotation_version_id):
        model = self.models.get(model_id, calibration=True)
        cal, app = model["calibration"], model["applicability"]
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            run = db.execute("SELECT * FROM preprocess_run WHERE id=?", (preprocess_run_id,)).fetchone()
            version = db.execute("SELECT * FROM annotation_version WHERE id=?", (annotation_version_id,)).fetchone()
            if version is None or version["cube_id"] != cube_id:
                raise ModelingError("VERSION_CUBE_MISMATCH", "标注版本不属于推理数据集")
            if (run is None or run["cube_id"] != cube_id or run["status"] != "succeeded"
                    or run["annotation_version_id"] != annotation_version_id):
                raise ModelingError("PREPROCESS_RUN_NOT_READY", "预处理 run 须成功且绑定该数据集和标注版本")
            recipe = db.execute("SELECT pipeline FROM preprocess_recipe_version WHERE id=?", (run["recipe_version_id"],)).fetchone()
            if (recipe is None or run["recipe_version_id"] not in cal.get("recipe_version_ids", [])
                    or normalized_pipeline(recipe[0]) != cal.get("pipeline")):
                raise ModelingError("RECIPE_MISMATCH", "推理须使用训练 run 绑定的配方版本")
            backgrounds = {row[0] for row in db.execute("SELECT id FROM label WHERE is_background=1")}
        dataset, _ = self.registry.readable(cube_id, raw=False)
        shape = dataset.shape
        if shape[2] != cal.get("input_n_features"):
            raise ModelingError("FEATURE_COUNT_MISMATCH", "原始波段数与注册模型不一致")
        if axis_sha256(dataset.wavelengths) != app["wavelength_axis_sha256"]:
            raise ModelingError("WAVELENGTH_AXIS_MISMATCH", "波长轴与注册模型不一致")
        probe = apply_with_calibration(cal, recipe[0], np.asarray(cal.get("probe", []))[None, :])
        if probe.shape[1] != app["n_features"]:
            raise ModelingError("FEATURE_COUNT_MISMATCH", "变换后特征数与注册模型不一致")
        predict(probe, cal["model"])
        lo, hi = np.asarray(cal.get("feature_min")), np.asarray(cal.get("feature_max"))
        if (lo.shape != (app["n_features"],) or hi.shape != lo.shape
                or not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(lo > hi)):
            raise mismatch()
        base, relative = self.paths.snapshots.resolve(), PurePosixPath(version["snapshot_ref"])
        folder = base.joinpath(*relative.parts).resolve()
        if (relative.is_absolute() or ".." in relative.parts or "\\" in str(relative) or ":" in str(relative)
                or not folder.is_relative_to(base)):
            raise ModelingError("INVALID_SNAPSHOT_REF", "标注快照引用非法")
        try:
            with np.load(folder / "label_map.npz", allow_pickle=False) as archive:
                labels = archive["label_map"].copy()
            index = json.loads((folder / "label_index.json").read_text("utf-8"))
        except (OSError, ValueError, KeyError) as error:
            raise ModelingError("INVALID_SNAPSHOT_REF", "无法读取确认版标签") from error
        if labels.shape != shape[:2] or labels.dtype.kind not in "iu" or np.any(labels < -2):
            raise ModelingError("LABEL_MAP_SHAPE_MISMATCH", "标签与推理数据集不匹配")
        if not isinstance(index, dict) or any(str(i) not in index for i in np.unique(labels[labels >= 0])):
            raise ModelingError("INVALID_SNAPSHOT_REF", "标签索引缺失")
        state = np.where(labels < 0, 0, np.where(np.isin(labels, [int(i) for i, v in index.items() if v in backgrounds]), 1, 2)).astype(np.uint8)
        if not np.any(state == 2):
            raise ModelingError("NO_FOREGROUND_PIXELS", "确认版没有前景像素")
        return model, recipe[0], shape, state

    def create(self, model_id, cube_id, preprocess_run_id, annotation_version_id, *, block_rows=32):
        model, pipeline, shape, state = self._prepare(model_id, cube_id, preprocess_run_id, annotation_version_id)
        cal, app = model["calibration"], model["applicability"]
        identifier, created = str(uuid4()), now()
        with connect_database(self.database) as db:
            db.execute("INSERT INTO inference_run (id,model_id,cube_id,preprocess_run_id,annotation_version_id,status,created_at) "
                       "VALUES (?,?,?,?,?,'pending',?)", (identifier, model_id, cube_id, preprocess_run_id, annotation_version_id, created))
            db.execute("UPDATE inference_run SET status='running' WHERE id=?", (identifier,))
        folder = self.paths.root / "inferences" / identifier
        arrays = []
        try:
            folder.mkdir(parents=True)
            prediction = np.lib.format.open_memmap(folder / "prediction.npy", mode="w+", dtype=np.float64, shape=shape[:2])
            arrays.append(prediction)
            applicability = np.lib.format.open_memmap(folder / "applicability.npy", mode="w+", dtype=np.float64, shape=shape[:2])
            arrays.append(applicability)
            total, count = np.zeros(shape[2]), int(np.count_nonzero(state == 2))
            for first, last, block in row_blocks(ReadableRows(self.registry, cube_id, shape), block_rows):
                x = finite(block.reshape(-1, shape[2]))
                features = apply_with_calibration(cal, pipeline, x)
                prediction[first:last] = predict(features, cal["model"]).reshape(last-first, shape[1])
                applicability[first:last] = np.mean((features < cal["feature_min"]) | (features > cal["feature_max"]), axis=1).reshape(last-first, shape[1])
                # Accumulate in fixed image-row order, independent of IO blocks.
                for row, mask in zip(block, state[first:last] == 2):
                    total += row[mask].sum(axis=0, dtype=np.float64)
            values = np.asarray(prediction[state == 2])
            low, high = app["y_min"], app["y_max"]
            below, above = int(np.count_nonzero(values < low)), int(np.count_nonzero(values > high))
            ood = int(np.count_nonzero(applicability[state == 2] > 0))
            stats = {
                "n_pixels": shape[0]*shape[1], "n_foreground": count, "mean": float(values.mean()),
                "std": float(values.std()), "min": float(values.min()), "max": float(values.max()),
                "quantiles": dict(zip(("p05", "p25", "p50", "p75", "p95"), np.percentile(values, [5, 25, 50, 75, 95]).tolist())),
                "pixel_mean": float(values.mean()),
                "sample_prediction": float(predict(apply_with_calibration(cal, pipeline, (total/count)[None, :]), cal["model"])[0]),
                "out_of_domain_count": ood, "out_of_domain_fraction": ood/count,
                "out_of_range_count": below+above, "below_range_count": below, "above_range_count": above,
                "low": low, "high": high, "warning": WARNING, "quality_label": model["quality_label"],
                "residual_interval": cal["residual_interval"], "calibration_limitation": cal["limitation"],
                "statistics_scope": "annotated_foreground", "ood_rule": "any_feature_outside_training_range",
            }
            rgb = concentration_colors(prediction, low, high)
            rgb[state == 0], rgb[state == 1] = [225, 225, 225], [85, 85, 85]
            domain = np.where((applicability > 0)[..., None], [215, 48, 39], [35, 139, 69]).astype(np.uint8)
            domain[state == 0], domain[state == 1] = [225, 225, 225], [85, 85, 85]
            (folder / "map.json").write_text(encode({
                "width": shape[1], "height": shape[0], "mime": "image/png", "png_base64": png_rgb(rgb),
                "applicability_png_base64": png_rgb(domain), "low": low, "high": high,
                "palette": CONCENTRATION_PALETTE, "stats": stats,
            }), "utf-8")
            np.save(folder / "state.npy", state, allow_pickle=False)
            for array in arrays:
                array.flush(); array._mmap.close()
            arrays.clear()
            artifacts = [(kind, folder / name) for kind, name in (
                ("prediction", "prediction.npy"), ("state", "state.npy"),
                ("applicability", "applicability.npy"), ("map", "map.json"))]
            with connect_database(self.database) as db:
                for kind, path in artifacts:
                    db.execute("INSERT INTO inference_artifact (id,run_id,kind,relative_path,sha256,created_at) VALUES (?,?,?,?,?,?)",
                               (str(uuid4()), identifier, kind, path.relative_to(self.paths.root).as_posix(), file_sha256(path), now()))
                db.execute("UPDATE inference_run SET status='succeeded',stats=?,finished_at=? WHERE id=?",
                           (encode(stats), now(), identifier))
        except Exception as error:
            for array in arrays:
                array._mmap.close()
            for name in ("prediction.npy", "applicability.npy", "state.npy", "map.json"):
                try:
                    (folder / name).unlink(missing_ok=True)
                except OSError:
                    pass
            if folder.exists():
                try:
                    folder.rmdir()
                except OSError:
                    pass
            code = error.code if isinstance(error, DataError) else "INFERENCE_FAILED"
            detail = f"推理失败（{type(error).__name__}）"
            with connect_database(self.database) as db:
                db.execute("UPDATE inference_run SET status='failed',error=?,finished_at=? WHERE id=?",
                           (encode({"error": code, "detail": detail}), now(), identifier))
            raise ModelingError(code, detail) from error
        return self.get(identifier)
