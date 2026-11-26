"""A fixed-parameter train/test run, independent of conversational orchestration."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
from threading import Lock, RLock
from time import sleep
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
from .inputs import CheckedStream, check_sources, check_split, enforce_split, load_input, record_source, sha256, split_preflight
from .pipeline import SpectralPipeline
from .report import metrics, representative_curves, curve_plot, html_report
from .schema import ExperimentConfig, TrainingSampling


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)


_JSON_LOCKS=tuple(RLock() for _ in range(16))


def _json_lock(path):
    # Bounded stripes avoid a lock object for every historical artifact. Keep a
    # poller from repeatedly opening the destination during atomic replacement.
    return _JSON_LOCKS[hash(os.path.normcase(os.path.abspath(path)))%len(_JSON_LOCKS)]


def read_json(path):
    """Read a complete status snapshot, tolerating transient Windows sharing."""
    with _json_lock(path):
        for attempt in range(6):
            try:return json.loads(Path(path).read_text('utf-8'))
            except PermissionError:
                if os.name!='nt' or attempt==5:raise
                sleep(.01*(attempt+1))


def write_json(path, value):
    with _json_lock(path):return _write_json(path,value)


def _write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        storage.resolve_write(temporary, kind="EXPERIMENT_JSON").write_text(encode(value), encoding="utf-8")
        # Windows readers briefly hold the destination without delete sharing.
        # Keep the atomic write and allow that read to finish before publishing.
        for attempt in range(6):
            try:
                storage.replace(temporary, path)
                break
            except PermissionError as error:
                if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 5:
                    raise
                sleep(.01 * (attempt + 1))
    finally:
        if temporary.exists():
            storage.unlink(temporary)


def save_arrays(path, *, check=None, **arrays):
    with storage.resolve_write(path, kind="EXPERIMENT_ARRAYS").open("wb") as stream:
        np.savez_compressed(CheckedStream(stream,check) if check else stream, **arrays)


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
        self.root = paths.experiment_archive
        self.lock = Lock()
        from .archive import ExperimentArchive
        self.archive = ExperimentArchive(self)

    def folder(self, identifier):
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError()
        except (ValueError, AttributeError, TypeError):
            raise DataError("EXPERIMENT_NOT_FOUND", "实验编号无效") from None
        folder = self.root / identifier
        if folder.resolve().parent != self.root.resolve():
            raise DataError('EXPERIMENT_NOT_FOUND', '实验目录越界')
        return folder

    def get(self, identifier):
        folder = self.folder(identifier)
        try:
            status = read_json(folder / "status.json")
        except FileNotFoundError:
            error = DataError("EXPERIMENT_NOT_FOUND", "实验不存在")
            error.status_code = 404
            raise error from None
        if status["status"] == "succeeded":
            return json.loads((folder / "result.json").read_text("utf-8"))
        return status

    def artifact(self, identifier, name, *, check=None):
        result = self.get(identifier)
        manifest = result.get("artifacts", {})
        if name not in manifest:
            raise DataError("EXPERIMENT_ARTIFACT_NOT_FOUND", "实验产物不存在")
        path = self.folder(identifier) / name
        if not path.is_file() or sha256(path,check) != manifest[name]["sha256"]:
            raise DataError("EXPERIMENT_ARTIFACT_CHANGED", "实验产物缺失或校验失败")
        return path

    def run(self, config: ExperimentConfig, *, expected_sources=None, progress=None, on_detail=None):
        from spectrumagent.annotation.palette import model_colors
        config = config.model_copy(update={'class_colors': model_colors(self.paths.database, config)})
        if config.training_sampling is not None:
            config = config.model_copy(update={'training_sampling':None})
        # BLAS thread limits are process-wide; serial execution avoids overlap.
        if not self.lock.acquire(blocking=False):
            raise DataError("EXPERIMENT_BUSY", "已有数值实验正在运行")
        identifier = str(uuid4())
        folder = self.folder(identifier)
        started = datetime.now(timezone.utc).isoformat()
        def advance(phase):
            write_json(folder / 'status.json', {'experiment_id': identifier, 'status': 'running',
                       'phase': phase, 'started_at': started})
            if progress:
                progress(phase)
        try:
            storage.mkdir(folder, parents=True)
            write_json(folder / "config.json", config.model_dump(mode="json"))
            if on_detail:
                on_detail(experiment_id=identifier)
            advance('checking')
            with threadpool_limits(limits=2):
                options = {}
                if expected_sources is not None:
                    options['expected_sources'] = expected_sources
                options['progress'] = advance
                if on_detail:
                    options['on_detail'] = on_detail
                result = self._execute(identifier, folder, config, **options)
            advance('reporting')
            write_json(folder / "status.json", {"experiment_id": identifier, "status": "succeeded",
                       'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat()})
            return result
        except Exception as error:
            failure = error if isinstance(error, DataError) else DataError("EXPERIMENT_FAILED", "数值实验失败", reason=str(error))
            if folder.is_dir():
                write_json(folder / "status.json", {"experiment_id": identifier, "status": "cancelled" if failure.code == 'EXPERIMENT_CANCELLED' else "failed", "error": failure.as_dict(),
                           'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat()})
            raise DataError(failure.code, failure.payload.detail, **{**failure.payload.context, "experiment_id": identifier}) from error
        finally:
            self.lock.release()

    def _execute(self, identifier, folder, config, *, expected_sources=None, progress=None, on_detail=None):
        if progress:
            progress('preparing')
        split_source = {}
        if config.split_manifest:
            from .group_split import load_saved_plan, manifest_path
            reference = config.split_manifest
            try:
                path = manifest_path(self.paths.exports, reference.split_id)
                sides = load_saved_plan(path, reference.sha256)
                for role, title in (('train', '训练'), ('test', '测试')):
                    spec = getattr(config, role)
                    expected = [(row['hdr'], row['img'], row['annotation'], row['sample_id'] or row['hdr'])
                                for row in sides[title]]
                    if spec.kind != 'roi_images' or expected != [
                            (member.header_path, member.data_path, member.roi_path, member.sample_id)
                            for member in spec.members]:
                        raise ValueError('训练与测试图像必须与已保存划分一致')
                record_source(path, split_source)
                split_bytes = path.read_bytes()
                if hashlib.sha256(split_bytes).hexdigest() != reference.sha256:
                    raise ValueError('划分清单已变化，请重新加载并审阅')
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise DataError('EXPERIMENT_INPUT_CHANGED', str(error)) from error
        def prepare(role):
            spec = getattr(config, role)
            if on_detail:
                def input_progress(**details):
                    on_detail(**({'role':role, **details} if details else {}))
                return load_input(spec, config.wavelengths_nm, config.classes, progress=input_progress)
            return load_input(spec, config.wavelengths_nm, config.classes)

        train, test = prepare('train'), prepare('test')
        if config.split_manifest:
            for title, data in (('训练',train),('测试',test)):
                for row in sides[title]:
                    if row.get('img_sha256') and data.sources[row['img']]['sha256'] != row['img_sha256']:
                        raise DataError('EXPERIMENT_INPUT_CHANGED', 'IMG 内容与配对清单不一致，请重新配对。')
        source_manifest = {**train.sources, **test.sources, **split_source}
        if expected_sources is not None and {key: item['sha256'] for key, item in source_manifest.items()} != expected_sources:
            raise DataError('EXPERIMENT_INPUT_CHANGED', '实验输入自方案核验后发生变化，请重新检查并展示方案')
        _, split_checks = split_preflight(config, source_manifest)
        split_checks = check_split(split_checks, train, test)
        enforce_split(config.test_usage, split_checks)
        external_sources = []
        for item in source_manifest.values():
            if item['path'] in split_source:
                continue
            path = Path(item['path'])
            # Replays are managed outputs. External-input registration would reject
            # their location inside the workspace. Verify the owning run and digest.
            replay_root = (self.paths.exports / 'center-replays').resolve()
            if path.parent.parent == replay_root:
                from .center_replay import verified_output
                item['center_replay_id'] = verified_output(path, item['sha256'])
            elif path.parent.parent == (self.paths.exports/'workspace-training').resolve():
                from .workspace_training import verified_output
                item['annotation_snapshot_id'] = verified_output(path, item['sha256'])
            else:
                external_sources.append(path)
        if external_sources:
            storage.for_database(self.paths.database).add_sources(external_sources)
        if set(train.y.tolist()) != set(config.classes):
            raise DataError("EXPERIMENT_CLASSES_MISSING", "训练数据必须覆盖所有声明类别")
        if train.sampling:
            config = config.model_copy(update={'training_sampling':TrainingSampling.model_validate(train.sampling)})
            write_json(folder / 'config.json', config.model_dump(mode='json'))
        if split_source:
            storage.resolve_write(folder / 'split_plan.json', kind='EXPERIMENT_SPLIT').write_bytes(split_bytes)
        write_json(folder / "sources.json", source_manifest)
        model = ExperimentModel(config)
        if progress:
            progress('training')
        train_features = model.fit(train.X, train.y)
        if progress:
            progress('testing')
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
            if data.sampling:
                summaries[role]['sampling'] = data.sampling
            write_json(folder / (role + "_origins.json"),
                       {'sampling':data.sampling, 'origins':data.origins} if data.sampling else data.origins)
        if progress:
            progress('reporting')
        for role, data, features in (("train", train, train_features), ("test", test, test_features)):
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
        check_sources(source_manifest, on_detail)
        config_document = config.model_dump(mode="json")
        result = {"experiment_id": identifier, "model_id": identifier, "status": "succeeded", "protocol": "explicit_train_test_v1",
                  "created_at": datetime.now(timezone.utc).isoformat(), "config": config_document,
                  "config_sha256": hashlib.sha256(encode(config_document).encode()).hexdigest(),
                  "model_sha256": sha256(model_path), "score_definition": "uncalibrated_pls_response",
                  "metrics": scores, "datasets": summaries, "fit_warnings": model.fit_warnings,
                  "split_checks": split_checks,
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
