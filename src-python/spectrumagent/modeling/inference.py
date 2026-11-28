"""Bounded inference with frozen training or explicit legacy calibration."""
from spectrumagent.storage import guard as storage
import base64
import hashlib
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
from spectrumagent.preprocess.run import file_sha256
from . import ModelingError
from .registry import ModelRegistry, axis_sha256, encode, missing, now
from .regression import predict

WARNING = "模型训练粒度＝样品均值谱；像素级预测为域外外推，仅表示含量空间分布趋势"


def mismatch():
    return ModelingError("CALIBRATION_MISMATCH", "标定缺失、维度或算子版本与配方不一致")


def training_snapshot(model):
    """Only an intact training snapshot may omit legacy inference inputs."""
    cal, app = model['calibration'], model['applicability']
    if cal.get('origin') == 'training_snapshot':
        from .regression import check_provenance, PROTOCOL
        check_provenance(cal)
        if app.get('training_protocol') != PROTOCOL or cal['training_run_id'] != model['run_id']:
            raise ModelingError('CALIBRATION_MISMATCH', '模型与训练快照的协议或来源不一致')
        return True
    if app.get('training_protocol') is not None:
        raise ModelingError('CALIBRATION_MISMATCH', '新协议模型缺少训练快照，拒绝使用重建状态')
    return False


def finite(value):
    if not np.isfinite(value).all():
        raise ModelingError("NON_FINITE_SPECTRA", "输入谱或变换、预测结果含非有限值")
    return value


def apply_with_calibration(calibration, pipeline, block):
    from spectrumagent.preprocess.fitted import transform
    try:
        return transform(calibration, pipeline, block)
    except DataError as error:
        raise ModelingError(error.code, error.payload.detail) from error



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

    def references(self, model, cube_id, preprocess_run_id, annotation_version_id, *, current=False):
        snapshot = training_snapshot(model)
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            version = None
            if annotation_version_id is not None or not snapshot:
                version = db.execute('SELECT * FROM annotation_version WHERE id=?', (annotation_version_id,)).fetchone()
                if version is None or version['cube_id'] != cube_id:
                    raise ModelingError('VERSION_CUBE_MISMATCH', '标注版本不属于推理数据集；历史模型仍需显式标注和预处理引用')
            if preprocess_run_id is not None or not snapshot:
                run = db.execute('SELECT * FROM preprocess_run WHERE id=?', (preprocess_run_id,)).fetchone()
                if (run is None or run['cube_id'] != cube_id or run['status'] != 'succeeded'
                        or run['annotation_version_id'] != annotation_version_id):
                    raise ModelingError('PREPROCESS_RUN_NOT_READY', '预处理 run 须成功且绑定该数据集和标注版本')
                if current:
                    from spectrumagent.preprocess.current import is_current_run
                    if not is_current_run(db, run):
                        raise ModelingError('PREPROCESS_RUN_NOT_READY', '请先处理当前标注，或明确使用训练快照直接预测')
            backgrounds = {row[0] for row in db.execute('SELECT id FROM label WHERE is_background=1')}
        return version, backgrounds, snapshot

    def _prepare(self, model_id, cube_id, preprocess_run_id=None, annotation_version_id=None):
        model = self.models.get(model_id, calibration=True)
        cal, app = model['calibration'], model['applicability']
        version, backgrounds, snapshot = self.references(model, cube_id, preprocess_run_id, annotation_version_id, current=True)
        pipeline = cal.get('pipeline')
        if pipeline is None:
            raise ModelingError('RECIPE_MISMATCH','模型缺少已训练的预处理定义')
        provenance = cal.get("provenance")
        if not snapshot and provenance is not None:
            required = {"fit_scope", "fit_sample_count", "fitted_on", "source_preprocess_run_ids",
                        "source_input_fingerprints", "report_fit_scope", "distinct_fit_populations",
                        "non_interchangeable_reason"}
            if (not isinstance(provenance, dict) or not required.issubset(provenance)
                    or provenance["fit_scope"] != "sample_mean"
                    or provenance["fitted_on"] != "registration"
                    or provenance["report_fit_scope"] != "labeled_pixels"
                    or provenance["distinct_fit_populations"] is not True
                    or type(provenance["fit_sample_count"]) is not int or provenance["fit_sample_count"] <= 0
                    or any(not isinstance(provenance[key], list) or not provenance[key]
                           or any(not isinstance(value, str) for value in provenance[key])
                           for key in ("source_preprocess_run_ids", "source_input_fingerprints"))
                    or not isinstance(provenance["non_interchangeable_reason"], str)
                    or not provenance["non_interchangeable_reason"].strip()):
                raise ModelingError("CALIBRATION_PROVENANCE_UNAVAILABLE", "注册标定溯源结构无效")
        dataset, _ = self.registry.readable(cube_id, raw=False)
        shape = dataset.shape
        if shape[2] != cal.get("input_n_features"):
            raise ModelingError("FEATURE_COUNT_MISMATCH", "原始波段数与注册模型不一致")
        if axis_sha256(dataset.wavelengths) != app["wavelength_axis_sha256"]:
            raise ModelingError("WAVELENGTH_AXIS_MISMATCH", "波长轴与注册模型不一致")
        probe = apply_with_calibration(cal, pipeline, np.asarray(cal.get("probe", []))[None, :])
        if probe.shape[1] != app["n_features"]:
            raise ModelingError("FEATURE_COUNT_MISMATCH", "变换后特征数与注册模型不一致")
        predict(probe, cal["model"])
        lo, hi = np.asarray(cal.get("feature_min")), np.asarray(cal.get("feature_max"))
        if (lo.shape != (app["n_features"],) or hi.shape != lo.shape
                or not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(lo > hi)):
            raise mismatch()
        if version is None:
            # An unannotated image has no implied object mask or target truth.
            return model, pipeline, shape, np.full(shape[:2], 2, dtype=np.uint8)
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
        return model, pipeline, shape, state

    def create(self, model_id, cube_id, preprocess_run_id=None, annotation_version_id=None, *, block_rows=32):
        model, pipeline, shape, state = self._prepare(model_id, cube_id, preprocess_run_id, annotation_version_id)
        cal, app = model["calibration"], model["applicability"]
        dataset, _ = self.registry.readable(cube_id, raw=False)
        source_hashes = {'header': file_sha256(dataset.header_path), 'data': file_sha256(dataset.data_path)}
        statistics_scope = 'annotated_foreground' if annotation_version_id is not None else 'whole_image'
        identifier, created = str(uuid4()), now()
        with connect_database(self.database) as db:
            db.execute("INSERT INTO inference_run (id,model_id,cube_id,preprocess_run_id,annotation_version_id,status,created_at) "
                       "VALUES (?,?,?,?,?,'pending',?)", (identifier, model_id, cube_id, preprocess_run_id, annotation_version_id, created))
            db.execute("UPDATE inference_run SET status='running' WHERE id=?", (identifier,))
        folder = self.paths.root / "inferences" / identifier
        arrays = []
        try:
            storage.mkdir(folder, parents=True)
            prediction = np.lib.format.open_memmap(storage.resolve_write(folder / "prediction.npy", kind="ARTIFACT_WRITE"), mode="w+", dtype=np.float64, shape=shape[:2])
            arrays.append(prediction)
            applicability = np.lib.format.open_memmap(storage.resolve_write(folder / "applicability.npy", kind="ARTIFACT_WRITE"), mode="w+", dtype=np.float64, shape=shape[:2])
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
            if source_hashes != {'header': file_sha256(dataset.header_path), 'data': file_sha256(dataset.data_path)}:
                raise ModelingError('SOURCE_CHANGED', '预测数据在读取过程中变化，本次结果未保存为成功')
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
                "low": low, "high": high, "warning": WARNING + ('；未提供标注，当前统计为整图（包含背景），不能解释为目标物含量' if statistics_scope == 'whole_image' else ''), "quality_label": model["quality_label"],
                "residual_interval": cal["residual_interval"], "calibration_limitation": cal["limitation"],
                "calibration_origin": cal["origin"],
                "fit_scope": (cal.get("provenance") or {}).get("fit_scope"),
                "calibration_provenance_present": bool(cal.get("provenance")),
                "statistics_scope": statistics_scope, "ood_rule": "any_feature_outside_training_range",
                'input_source_hashes': source_hashes, 'wavelength_axis_sha256': app['wavelength_axis_sha256'],
                'model_calibration_sha256': hashlib.sha256(encode(cal).encode()).hexdigest(),
                'training_protocol': app.get('training_protocol', 'sample_pls_full_fit_legacy'),
            }
            rgb = concentration_colors(prediction, low, high)
            rgb[state == 0], rgb[state == 1] = [225, 225, 225], [85, 85, 85]
            domain = np.where((applicability > 0)[..., None], [215, 48, 39], [35, 139, 69]).astype(np.uint8)
            domain[state == 0], domain[state == 1] = [225, 225, 225], [85, 85, 85]
            (storage.resolve_write(folder / "map.json", kind="WRITE_TEXT")).write_text(encode({
                "width": shape[1], "height": shape[0], "mime": "image/png", "png_base64": png_rgb(rgb),
                "applicability_png_base64": png_rgb(domain), "low": low, "high": high,
                "palette": CONCENTRATION_PALETTE, "stats": stats,
            }), "utf-8")
            np.save(storage.resolve_write(folder / "state.npy", kind="ARTIFACT_WRITE"), state, allow_pickle=False)
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
                    storage.unlink(folder / name, missing_ok=True)
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
