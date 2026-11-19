"""A fixed-parameter train/test run, independent of conversational orchestration."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from threading import Lock
from uuid import UUID, uuid4
import warnings

import joblib
import numpy as np
import scipy
import sklearn
from sklearn.cross_decomposition import PLSRegression
from threadpoolctl import threadpool_limits

from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage
from .inputs import load_input, check_split, check_sources, sha256
from .pipeline import SpectralPipeline
from .report import metrics, representative_curves, curve_plot, html_report
from .schema import ExperimentConfig


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        storage.resolve_write(temporary, kind="EXPERIMENT_JSON").write_text(encode(value), encoding="utf-8")
        storage.replace(temporary, path)
    finally:
        if temporary.exists():
            storage.unlink(temporary)


def save_arrays(path, **arrays):
    with storage.resolve_write(path, kind="EXPERIMENT_ARRAYS").open("wb") as stream:
        np.savez_compressed(stream, **arrays)


class ExperimentModel:
    """Only self-produced trusted joblib artifacts should be loaded by callers."""
    def __init__(self, config):
        self.config = config
        self.pipeline = SpectralPipeline(config.preprocessing)
        self.classes_ = np.asarray(sorted(config.classes), dtype=np.int64)
        self.estimator = PLSRegression(**config.model.model_dump())

    def fit(self, X, y):
        features = self.pipeline.fit_transform(X)
        rank = int(np.linalg.matrix_rank(features-features.mean(axis=0)))
        if self.config.model.n_components > min(rank, len(X)-1, features.shape[1]):
            raise DataError("EXPERIMENT_LV_INVALID", "潜变量数量超出训练样本或特征秩", rank=rank)
        hot = (y[:, None] == self.classes_).astype(float)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.estimator.fit(features, hot)
        self.fit_warnings = [str(item.message) for item in caught]
        return features

    def decision_function(self, X, wavelengths_nm):
        if not np.array_equal(wavelengths_nm, self.config.wavelengths_nm):
            raise DataError("EXPERIMENT_AXIS_INVALID", "预测波长与训练波长不一致")
        X = np.asarray(X)
        if X.ndim != 2 or X.shape[1] != len(wavelengths_nm) or not np.isfinite(X).all():
            raise DataError("EXPERIMENT_INPUT_INVALID", "预测需有限且维度匹配的数值光谱")
        values = self.estimator.predict(self.pipeline.transform(X))
        if not np.isfinite(values).all():
            raise DataError("EXPERIMENT_DEGENERATE", "模型响应包含非有限值")
        return values

    def predict(self, X, wavelengths_nm):
        return self.classes_[self.decision_function(X, wavelengths_nm).argmax(axis=1)]


class ExperimentService:
    def __init__(self, paths):
        self.paths = paths
        self.root = paths.artifact_root / "experiments"
        self.lock = Lock()

    def folder(self, identifier):
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise DataError("EXPERIMENT_NOT_FOUND", "实验编号无效") from None
        return self.root / identifier

    def get(self, identifier):
        folder = self.folder(identifier)
        try:
            status = json.loads((folder / "status.json").read_text("utf-8"))
        except FileNotFoundError:
            error = DataError("EXPERIMENT_NOT_FOUND", "实验不存在")
            error.status_code = 404
            raise error from None
        if status["status"] == "succeeded":
            return json.loads((folder / "result.json").read_text("utf-8"))
        return status

    def artifact(self, identifier, name):
        result = self.get(identifier)
        manifest = result.get("artifacts", {})
        if name not in manifest:
            raise DataError("EXPERIMENT_ARTIFACT_NOT_FOUND", "实验产物不存在")
        path = self.folder(identifier) / name
        if not path.is_file() or sha256(path) != manifest[name]["sha256"]:
            raise DataError("EXPERIMENT_ARTIFACT_CHANGED", "实验产物缺失或校验失败")
        return path

    def run(self, config: ExperimentConfig):
        # BLAS thread limits are process-wide; serial execution avoids overlap.
        if not self.lock.acquire(blocking=False):
            raise DataError("EXPERIMENT_BUSY", "已有数值实验正在运行")
        identifier = str(uuid4())
        folder = self.folder(identifier)
        try:
            storage.mkdir(folder, parents=True)
            write_json(folder / "config.json", config.model_dump(mode="json"))
            write_json(folder / "status.json", {"experiment_id": identifier, "status": "running"})
            with threadpool_limits(limits=2):
                result = self._execute(identifier, folder, config)
            write_json(folder / "status.json", {"experiment_id": identifier, "status": "succeeded"})
            return result
        except Exception as error:
            failure = error if isinstance(error, DataError) else DataError("EXPERIMENT_FAILED", "数值实验失败", reason=str(error))
            if folder.is_dir():
                write_json(folder / "status.json", {"experiment_id": identifier, "status": "failed", "error": failure.as_dict()})
            raise DataError(failure.code, failure.payload.detail, **{**failure.payload.context, "experiment_id": identifier}) from error
        finally:
            self.lock.release()

    def _execute(self, identifier, folder, config):
        train = load_input(config.train, config.wavelengths_nm, config.classes)
        test = load_input(config.test, config.wavelengths_nm, config.classes)
        source_manifest = {**train.sources, **test.sources}
        storage.for_database(self.paths.database).add_sources([item["path"] for item in source_manifest.values()])
        check_split(train, test)
        if set(train.y.tolist()) != set(config.classes):
            raise DataError("EXPERIMENT_CLASSES_MISSING", "训练数据必须覆盖所有声明类别")
        write_json(folder / "sources.json", source_manifest)
        model = ExperimentModel(config)
        train_features = model.fit(train.X, train.y)
        test_features = model.pipeline.transform(test.X)
        predictions, scores, summaries, curves = {}, {}, {}, {}
        for role, data, features in (("train", train, train_features), ("test", test, test_features)):
            responses = np.concatenate([model.decision_function(data.X[start:start+8192], config.wavelengths_nm)
                                        for start in range(0, len(data.X), 8192)])
            prediction = model.classes_[responses.argmax(axis=1)]
            predictions[role] = prediction
            scores[role] = metrics(data.y, prediction, config.classes, config.additional_metrics)
            scores[role].update(evaluation_unit=data.unit, purpose="training_fit" if role == "train" else config.test_usage)
            summaries[role] = {"observations": len(data.y), "excluded_centers": data.excluded,
                               "class_counts": {str(label): int((data.y == label).sum()) for label in sorted(config.classes)}}
            save_arrays(folder / (role + "_prepared.npz"), X=data.X, y=data.y, wavelengths_nm=config.wavelengths_nm)
            save_arrays(folder / (role + "_predictions.npz"), truth=data.y, prediction=prediction, responses=responses,
                        classes=model.classes_)
            write_json(folder / (role + "_origins.json"), data.origins)
            axis = (list(range(1, features.shape[1]+1)) if any(s.op == "pca" for s in config.preprocessing)
                    else config.wavelengths_nm)
            for stage, matrix, x_axis in (("input", data.X, config.wavelengths_nm), ("processed", features, axis)):
                name = role + "_" + stage
                curves[name] = representative_curves(matrix, data.y, config.classes, x_axis)
                curve_plot(curves[name], storage.resolve_write(folder / (name+".png"), kind="EXPERIMENT_PLOT"), name)
        model_path = storage.resolve_write(folder / "model.joblib", kind="EXPERIMENT_MODEL")
        joblib.dump(model, model_path)
        # Exercise the exact saved artifact before declaring this run complete.
        reloaded = joblib.load(model_path)
        for role, data in (("train", train), ("test", test)):
            actual = np.concatenate([reloaded.predict(data.X[start:start+8192], config.wavelengths_nm)
                                     for start in range(0, len(data.X), 8192)])
            if not np.array_equal(actual, predictions[role]):
                raise DataError("EXPERIMENT_MODEL_INVALID", "保存后模型预测与运行结果不同")
        check_sources(source_manifest)
        config_document = config.model_dump(mode="json")
        result = {"experiment_id": identifier, "status": "succeeded", "protocol": "explicit_train_test_v1",
                  "created_at": datetime.now(timezone.utc).isoformat(), "config": config_document,
                  "config_sha256": hashlib.sha256(encode(config_document).encode()).hexdigest(),
                  "model_sha256": sha256(model_path), "score_definition": "uncalibrated_pls_response",
                  "metrics": scores, "datasets": summaries, "fit_warnings": model.fit_warnings,
                  "split_checks": {"same_file": False, "exact_duplicate_spectrum": False,
                                   "physical_sample_independence": "only_explicit_image_sample_ids_checked"},
                  "environment": {"python": platform.python_version(), "numpy": np.__version__,
                                  "scipy": scipy.__version__, "sklearn": sklearn.__version__, "joblib": joblib.__version__},
                  "code_sha256": {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))}}
        write_json(folder / "curves.json", curves)
        write_json(folder / "metrics.json", scores)
        storage.resolve_write(folder / "report.html", kind="EXPERIMENT_REPORT").write_text(html_report(result), encoding="utf-8")
        result["artifacts"] = {p.name: {"sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted(folder.iterdir())
                               if p.name not in ("status.json", "result.json") and p.is_file()}
        write_json(folder / "result.json", result)
        return result
