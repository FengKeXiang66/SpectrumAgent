"""Classification preflight and synchronous sample-level PLS run lifecycle."""
from spectrumagent.storage import guard as storage
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import PurePosixPath
import hashlib
from uuid import uuid4
from time import perf_counter
import sys

import numpy as np

from backend.database import connect_database
from . import ModelingError
from .cv import plan_folds, kennard_stone
from .dataset import _build, _inputs, build_sample_training_set
from .leak import preflight_report, sample_preflight_report, skipped_training_report
from .metrics import _regression, REGRESSION_METRICS, classification_scores, classification_fold_summary
from spectrumagent.preprocess.run import code_version
from spectrumagent.data import DataError
from spectrumagent.preprocess.drafts import assert_runs_available


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


def classification_probabilities(raw):
    values = np.asarray(raw, dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ModelingError("INVALID_CLASS_PROBABILITIES", "PLS-DA 输出须为有限类别矩阵")
    weights = np.exp(values-values.max(axis=1, keepdims=True))
    return weights/weights.sum(axis=1, keepdims=True)


class TrainingRuns:
    def __init__(self, registry, paths):
        self.registry, self.paths, self.database = registry, paths, registry.database

    def _transition(self, identifier, status, *, report=None, error=None):
        stamp = "started_at" if status == "running" else "finished_at"
        with connect_database(self.database) as db:
            db.execute(f"UPDATE training_run SET status=?,{stamp}=?,leak_report=?,error=? WHERE id=?",
                       (status, _now(), _json(report) if report is not None else None,
                        _json(error) if error is not None else None, identifier))

    def _preflight_data(self, *, cube_ids, annotation_version_ids, preprocess_run_ids, task, target, cv_strategy, cv_folds, seed, split_strategy="none",
                        recipe_version_id=None, dataset_version_ref=None, check_leakage=True):
        rows = _inputs(self.registry, cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
                       preprocess_run_ids=preprocess_run_ids, target=target, task=task,
                       recipe_version_id=recipe_version_id, dataset_version_ref=dataset_version_ref)
        with connect_database(self.database) as db:
            db.execute('BEGIN')
            assert_runs_available(db,preprocess_run_ids)
        if split_strategy != "none":
            raise ModelingError("INVALID_SPLIT", "分类预检没有外层留出划分")
        groups_count = len(set(cube_ids))
        if groups_count < 2 or (cv_strategy == "group_kfold" and groups_count < cv_folds):
            detail = ("单数据集无法分组交叉验证" if groups_count < 2 else
                      f"实际组数 {groups_count}，请求折数 {cv_folds}")
            raise ModelingError("INSUFFICIENT_GROUPS", detail,
                                n_groups=groups_count, requested_folds=cv_folds)
        # All schema/reference/shape/CV validation completes before INSERT.
        data = _build(self.registry, self.paths, rows)
        folds = plan_folds(data["y"], data["groups"], task=task, strategy=cv_strategy, folds=cv_folds, seed=seed)
        report = preflight_report(data["meta"], folds, strategy=cv_strategy) if check_leakage else skipped_training_report()
        return rows, data, folds, report

    def preflight(self, *, cube_ids, annotation_version_ids, preprocess_run_ids, task, target, cv_strategy, cv_folds, seed, split_strategy="none",
                  evaluation_protocol=None, sample_groups=None):
        if evaluation_protocol is None:
            _, data, folds, report = self._preflight_data(cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
                preprocess_run_ids=preprocess_run_ids, task=task, target=target, cv_strategy=cv_strategy,
                cv_folds=cv_folds, seed=seed, split_strategy=split_strategy)
        else:
            from .classification import load_data, class_support_report
            if task != "classification" or cv_strategy != "group_kfold" or split_strategy != "none" or evaluation_protocol not in ("nested_group_cv", "exploratory_group_cv"):
                raise ModelingError("INVALID_CV_PARAMS", "分类评价协议不匹配")
            started = perf_counter()
            rows = _inputs(self.registry, cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
                           preprocess_run_ids=preprocess_run_ids, target=target)
            inputs = load_data(self.registry, self.paths, rows, sample_groups)
            folds = plan_folds(inputs["y"], inputs["groups"], task=task, strategy=cv_strategy, folds=cv_folds, seed=seed)
            if evaluation_protocol == "nested_group_cv" and any(len(f["train_groups"]) < 2 for f in folds):
                raise ModelingError("INSUFFICIENT_NESTED_GROUPS", "外层训练侧至少两个组才能进行内层选优")
            means = np.stack([inputs["X"][inputs["cube_index"] == i].mean(axis=0) for i in range(len(rows))])
            report = sample_preflight_report({"cubes": inputs["cubes"]}, folds, means)
            report["class_support"] = class_support_report(inputs["y"], inputs["groups"], inputs["classes"], folds,
                                                            protocol=evaluation_protocol, seed=seed)
            report["preprocess_full_fit"] = {"acknowledged": False, "reason": "严格训练采用各层训练侧拟合", "affected_steps": []}
            report["group_kind"] = inputs["group_kind"]
            data = {"meta": {"n_samples": len(inputs["y"]), "n_features": inputs["X"].shape[1], "build_seconds": perf_counter()-started}}
        summaries = [{"fold_index": f["fold_index"], "train_count": len(f["train_idx"]), "test_count": len(f["test_idx"]),
                      "train_groups": f["train_groups"], "test_groups": f["test_groups"]} for f in folds]
        identifier = str(uuid4())
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            assert_runs_available(db,preprocess_run_ids)
            db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,"
                       "cv_strategy,cv_folds,seed,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,'pending',?)",
                       (identifier, _json(cube_ids), _json(annotation_version_ids), _json(preprocess_run_ids),
                        task, target, cv_strategy, cv_folds, seed, _now()))
            db.executemany("INSERT INTO training_fold VALUES (?,?,?,?,?,?,?)",
                           [(str(uuid4()), identifier, f["fold_index"], f["train_count"], f["test_count"],
                             _json(f["train_groups"]), _json(f["test_groups"])) for f in summaries])
        self._transition(identifier, "running")
        status = "succeeded" if report["passed"] else "failed"
        error = None if report["passed"] else {"error": "LEAK_PREFLIGHT_FAILED",
                 "group_violations": report["group_cross_fold"]["violation_count"],
                 "duplicate_count": report["duplicate_content"]["duplicate_count"]}
        self._transition(identifier, status, report=report, error=error)
        return {"run_id": identifier, "status": status, "leak_report": report, "folds": summaries,
                "n_samples": data["meta"]["n_samples"], "n_features": data["meta"]["n_features"],
                "build_seconds": data["meta"]["build_seconds"]}

    def get(self, identifier):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM training_run WHERE id=?", (str(identifier),)).fetchone()
            if row is None:
                error = ModelingError("RUN_NOT_FOUND", "训练预检run不存在")
                error.status_code = 404
                raise error
            if row["task"] == "classification" and row["status"] == "succeeded":
                from .evaluation import Evaluations
                snapshot = Evaluations(self.registry, self.paths).latest(str(identifier))
                if snapshot:
                    from .classification import result
                    return result(snapshot, json.loads(row["leak_report"] or "{}"))
            if db.execute("SELECT 1 FROM model_artifact WHERE run_id=? AND kind='confusion'", (str(identifier),)).fetchone():
                confusion = self.artifact(identifier, "confusion")
                metrics = {scope: dict(db.execute("SELECT name,value FROM metric WHERE run_id=? AND scope=? AND fold_index IS NULL",
                                                 (str(identifier), scope))) for scope in ("pixel", "sample")}
                params = json.loads(row["model_params"])
                result = {"run_id": row["id"], "status": row["status"], "task": row["task"],
                        "cv_strategy": row["cv_strategy"], "cv_folds": row["cv_folds"], "group_by": "sample_id",
                        "n_samples": params["n_samples"], "n_pixels_used": params["n_pixels_used"],
                        "selected_lv": params["selected_lv"], "best_lv": params["best_lv"],
                        "by_cv_min": params["best_lv"], "by_elbow": params["by_elbow"],
                        "metrics": metrics, "confusion": confusion,
                        "leak_report": json.loads(row["leak_report"]), "error": None}
                manifest = self.artifact(identifier, "model").get("manifest", {})
                if "band_selection" in manifest:
                    result["bands"] = manifest["band_selection"]
                return result
            if row["task"] == "regression" and row["split_strategy"] == "ks":
                metrics = dict(db.execute("SELECT name,value FROM metric WHERE run_id=? AND scope='sample' AND fold_index IS NULL", (str(identifier),)))
                params = json.loads(row["model_params"]) if row["model_params"] else {}
                return {"run_id": row["id"], "status": row["status"], "task": row["task"], "target": row["target"],
                        "target_schema_id": row["target_schema_id"], "split_strategy": row["split_strategy"],
                        "cv_strategy": row["cv_strategy"], "cv_folds": row["cv_folds"],
                        "n_samples": params.get("n_samples", 0), "n_pixels_used": params.get("n_pixels_used", 0),
                        "selected_lv": params.get("selected_lv"), "best_lv": params.get("best_lv"),
                        "by_cv_min": params.get("best_lv"), "by_elbow": params.get("by_elbow"),
                        "metrics": metrics, "semi_quantitative": metrics.get("rpd") is not None and metrics["rpd"] < 2.5,
                        "quality_label": "仅可做半定量" if metrics.get("rpd") is not None and metrics["rpd"] < 2.5 else None,
                        "leak_report": json.loads(row["leak_report"]) if row["leak_report"] else None,
                        "error": json.loads(row["error"]) if row["error"] else None,
                        "predictions": self.artifact(identifier, "predictions") if row["status"] == "succeeded" else []}
            folds = []
            for fold in db.execute("SELECT fold_index,train_count,test_count,train_groups,test_groups FROM training_fold "
                                   "WHERE run_id=? ORDER BY fold_index", (str(identifier),)):
                item = dict(fold)
                for key in ("train_groups", "test_groups"):
                    item[key] = json.loads(item[key])
                folds.append(item)
        return {"run_id": row["id"], "status": row["status"], "task": row["task"], "cv_strategy": row["cv_strategy"],
                "cv_folds": row["cv_folds"], "n_samples": folds[0]["train_count"]+folds[0]["test_count"] if folds else 0,
                "leak_report": json.loads(row["leak_report"]) if row["leak_report"] else None, "folds": folds, "metrics": []}

    def list(self, cube_id=None):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            where = " WHERE EXISTS (SELECT 1 FROM json_each(training_run.cube_ids) WHERE value=?)" if cube_id else ""
            rows = db.execute("SELECT training_run.id,status,task,training_run.created_at,c.run_id AS trained,"
                "m.oa,m.kappa,json_extract(model_params,'$.selected_lv') AS lv FROM training_run "
                "LEFT JOIN model_artifact c ON c.run_id=training_run.id AND c.kind='confusion' "
                "LEFT JOIN (SELECT run_id,MAX(CASE WHEN name='oa' THEN value END) AS oa,"
                "MAX(CASE WHEN name='kappa' THEN value END) AS kappa FROM metric "
                "WHERE scope='sample' AND fold_index IS NULL GROUP BY run_id) m ON m.run_id=training_run.id" + where +
                " ORDER BY training_run.created_at DESC,training_run.id DESC", (str(cube_id),) if cube_id else ())
            result = []
            for row in rows:
                item = {key: row[key] for key in ("id", "status", "task", "created_at")}
                if row["trained"] is not None:
                    item.update({key: row[key] for key in ("oa", "kappa", "lv")})
                result.append(item)
            return result

    def artifact(self, identifier, kind):
        with connect_database(self.database) as db:
            row = db.execute("SELECT relative_path,sha256 FROM model_artifact WHERE run_id=? AND kind=?", (str(identifier), kind)).fetchone()
        if row is None:
            error = ModelingError("ARTIFACT_NOT_FOUND", "模型产物尚不存在")
            error.status_code = 404
            raise error
        relative, base = PurePosixPath(row[0]), (self.paths.root / "models").resolve()
        path = base.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in row[0] or ":" in row[0] or not path.is_relative_to(base):
            raise ModelingError("INVALID_ARTIFACT", "模型产物引用非法")
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row[1]:
                raise ModelingError("ARTIFACT_HASH_MISMATCH", "模型产物摘要不一致")
            return json.loads(raw)
        except (OSError, ValueError) as error:
            raise ModelingError("INVALID_ARTIFACT", "模型产物不可读") from error

    def classify(self, *, cube_ids, annotation_version_ids, preprocess_run_ids, task="classification", target="label",
                 cv_strategy="group_kfold", cv_folds=5, seed=17, split_strategy="none", confidence_threshold=0,
                 n_components=None, max_components=None, band_selection=None, dataset_version_ref=None, recipe_version_id=None,
                 evaluation_protocol=None, sample_groups=None):
        import sklearn
        from sklearn.cross_decomposition import PLSRegression

        from .training_state import CURRENT
        control = CURRENT.get()
        if not cube_ids or len(cube_ids) != len(annotation_version_ids) or len(cube_ids) != len(preprocess_run_ids):
            raise ModelingError("ARGUMENT_LENGTH_MISMATCH", "三个引用数组须等长且非空")
        cube_ids, annotation_version_ids, preprocess_run_ids = map(list, zip(*sorted(
            zip(cube_ids, annotation_version_ids, preprocess_run_ids), key=lambda row: row[0])))
        started = perf_counter()
        if band_selection is not None and band_selection != "ipls":
            raise ModelingError("INVALID_BAND_SELECTION", "波段选择仅支持 ipls 或全波段")
        if task != "classification" or target != "label" or cv_strategy != "group_kfold" or split_strategy != "none":
            raise ModelingError("INVALID_CV_PARAMS", "PLS-DA 强制按 sample_id 分组，无外层划分")
        if isinstance(confidence_threshold, bool) or not isinstance(confidence_threshold, (int, float)) or not 0 <= confidence_threshold < 1:
            raise ModelingError("INVALID_CONFIDENCE_THRESHOLD", "置信度阈值须在 [0,1)，默认 0 不拒识")
        for value in (n_components, max_components):
            if value is not None and (type(value) is not int or not 1 <= value <= 20):
                raise ModelingError("INVALID_LV", "分类 LV 范围为 1–20")
        if evaluation_protocol is not None:
            if evaluation_protocol not in ("nested_group_cv", "exploratory_group_cv"):
                raise ModelingError("INVALID_CV_PARAMS", "未知分类评价协议")
            from .classification import train
            rows = _inputs(self.registry, cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
                           preprocess_run_ids=preprocess_run_ids, target=target, task=task,
                           recipe_version_id=recipe_version_id, dataset_version_ref=dataset_version_ref)
            with self.registry.recycle.coordinator.job():
                return train(self, rows, cv_folds=cv_folds, seed=seed, threshold=float(confidence_threshold),
                             maximum=max_components, manual=n_components, ipls=band_selection == "ipls",
                             protocol=evaluation_protocol, training_set_ref=None,
                             dataset_version_ref=dataset_version_ref, sample_groups=sample_groups)
        rows, data, folds, report = self._preflight_data(cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
            preprocess_run_ids=preprocess_run_ids, task=task, target=target, cv_strategy=cv_strategy,
            cv_folds=cv_folds, seed=seed, split_strategy=split_strategy,
            recipe_version_id=recipe_version_id, dataset_version_ref=dataset_version_ref, check_leakage=False)
        if [cube["cube_id"] for cube in data["meta"]["cubes"]] != cube_ids:
            raise ModelingError("MODEL_INPUT_UNAVAILABLE", "训练指纹与输入数据集逐位不一致",
                                cube_ids=cube_ids, version_id=dataset_version_ref)
        report["group_by"] = "sample_id"
        report["sample_ids"] = {str(cube["group"]): cube["cube_id"] for cube in data["meta"]["cubes"]}
        X, y, groups = data["X"], data["y"], data["groups"]
        if band_selection == "ipls" and X.shape[1] < 20:
            raise ModelingError("INSUFFICIENT_IPLS_FEATURES", "iPLS 需要至少 20 个特征列，不能减少区间数", n_features=X.shape[1])
        labels = np.unique(y)
        if len(labels) < 2:
            raise ModelingError("INSUFFICIENT_CLASSES", "PLS-DA 至少需要两个已标类别")
        maximum = min(20, X.shape[1], min(len(fold["train_idx"])-1 for fold in folds), max_components or 20)
        if maximum < 1 or n_components is not None and n_components > maximum:
            raise ModelingError("INVALID_LV", "LV 不得超过折内训练像素数减一及特征数", maximum=maximum)
        one_hot = (y[:, None] == labels[None, :]).astype(float)
        params = {"n_samples": len(np.unique(groups)), "n_pixels_used": len(y), "group_by": "sample_id",
                  "confidence_threshold": float(confidence_threshold), "n_components": n_components,
                  "max_components": max_components, "effective_max_components": maximum}
        identifier, created = str(uuid4()), _now()
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            assert_runs_available(db,preprocess_run_ids)
            db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,"
                       "cv_strategy,cv_folds,seed,model_family,model_params,status,created_at,split_strategy) "
                       "VALUES (?,?,?,?,?,?,?,?,?,'plsda',?,'pending',?,'none')",
                       (identifier, _json(cube_ids), _json(annotation_version_ids), _json(preprocess_run_ids),
                        task, target, cv_strategy, cv_folds, seed, _json(params), created))
            db.executemany("INSERT INTO training_fold VALUES (?,?,?,?,?,?,?)",
                [(str(uuid4()), identifier, fold["fold_index"], len(fold["train_idx"]), len(fold["test_idx"]),
                  _json(fold["train_groups"]), _json(fold["test_groups"])) for fold in folds])
        self._transition(identifier, "running", report=report)
        folder = self.paths.root / "models" / identifier
        try:
            curve = []
            for lv in range(1, maximum+1):
                errors, fold_rmse = [], []
                for fold in folds:
                    a, b = fold["train_idx"], fold["test_idx"]
                    model = PLSRegression(n_components=lv).fit(X[a], one_hot[a])
                    residual = model.predict(X[b])-one_hot[b]
                    errors.extend((residual**2).ravel().tolist())
                    fold_rmse.append(float(np.sqrt(np.mean(residual**2))))
                curve.append({"n_components": lv, "rmsecv": float(np.sqrt(np.mean(errors))),
                              "sd": float(np.std(fold_rmse, ddof=1))})
            best = min(curve, key=lambda point: (point["rmsecv"], point["n_components"]))
            # Same recommendation rule as the existing PLS regression path.
            elbow = next(point["n_components"] for point in curve if point["rmsecv"] <= best["rmsecv"]+best["sd"])
            selected = n_components if n_components is not None else best["n_components"]
            if band_selection == "ipls":
                intervals = np.array_split(np.arange(X.shape[1]), 20)
                scan_lv = min(best["n_components"], min(len(cols) for cols in intervals))
                if scan_lv < 1:
                    raise ModelingError("INVALID_IPLS_LV", "iPLS 扫描 LV 必须至少为 1")
                band_curve = []
                for index, cols in enumerate(intervals, 1):
                    errors, fold_rmse = [], []
                    for fold in folds:
                        a, b = fold["train_idx"], fold["test_idx"]
                        model = PLSRegression(n_components=scan_lv).fit(X[a][:, cols], one_hot[a])
                        residual = model.predict(X[b][:, cols])-one_hot[b]
                        errors.extend((residual**2).ravel().tolist())
                        fold_rmse.append(float(np.sqrt(np.mean(residual**2))))
                    band_curve.append({"index": index, "start_col": int(cols[0])+1, "end_col": int(cols[-1])+1,
                                       "rmsecv": float(np.sqrt(np.mean(errors))), "sd": float(np.std(fold_rmse, ddof=1))})
                chosen = sorted(sorted(band_curve, key=lambda point: (point["rmsecv"], point["index"]))[:6],
                                key=lambda point: point["index"])
                indices = sorted(int(col) for point in chosen for col in intervals[point["index"]-1])
                comparison = {scope: {} for scope in ("pixel", "sample")}
                for name, features in (("full", X), ("selected", X[:, indices])):
                    compared_probability = np.empty_like(one_hot)
                    for fold in folds:
                        a, b = fold["train_idx"], fold["test_idx"]
                        model = PLSRegression(n_components=scan_lv).fit(features[a], one_hot[a])
                        compared_probability[b] = classification_probabilities(model.predict(features[b]))
                    compared = labels[compared_probability.argmax(axis=1)].copy()
                    compared[compared_probability.max(axis=1) < confidence_threshold] = -2
                    compared_scores = classification_scores(y, compared, groups, labels=labels.tolist())
                    for scope in comparison:
                        comparison[scope][name] = {metric: compared_scores[scope][metric] for metric in ("oa", "kappa")}
                bands = {"method": "ipls", "n_intervals": 20, "keep": 6, "lv": scan_lv,
                         "definition": "扫描与对比同 LV；与 metric 表最终训练 LV 可能不同",
                         "intervals": chosen, "indices": indices, "curve": band_curve, "comparison": comparison,
                         "limitation": "特征列由预处理链决定，不必然对应原始波长"}
            probability = np.empty_like(one_hot)
            fold_index = np.empty(len(y), dtype=np.int64)
            for fold in folds:
                a, b = fold["train_idx"], fold["test_idx"]
                model = PLSRegression(n_components=selected).fit(X[a], one_hot[a])
                probability[b] = classification_probabilities(model.predict(X[b]))
                fold_index[b] = fold["fold_index"]
            confidence = probability.max(axis=1)
            predicted = labels[probability.argmax(axis=1)].copy()
            predicted[confidence < confidence_threshold] = -2
            scores = classification_scores(y, predicted, groups, labels=labels.tolist())
            fold_scores = [classification_scores(y[f["test_idx"]], predicted[f["test_idx"]],
                          groups[f["test_idx"]], labels=labels.tolist()) for f in folds]
            sweep = {"best_lv": best["n_components"], "elbow_lv": elbow, "selected_lv": selected,
                     "by_cv_min": best["n_components"], "by_elbow": elbow, "manual_override": n_components is not None,
                     "definition": "pooled held-out one-hot RMSECV; elbow <= best RMSECV + one SD of best fold RMSE",
                     "curve": curve}
            model = PLSRegression(n_components=selected).fit(X, one_hot)
            params["estimator"] = model.get_params()
            params["operator"] = {"name": "train_plsda", "version": 1}
            manifest = {"dataset_versions": [{"cube_id": cube["cube_id"], "source_hashes": cube["source_hashes"],
                         "input_fingerprint": cube["input_fingerprint"]} for cube in data["meta"]["cubes"]],
                        "annotation_version_ids": annotation_version_ids, "preprocess_run_ids": preprocess_run_ids,
                        "recipe_version_ids": [row["run"]["recipe_version_id"] for row in rows],
                        "pipeline_versions": [row["pipeline"] for row in rows],
                        "params": {**params, "selected_lv": selected, "task": task, "target": target,
                                   "cv_strategy": cv_strategy, "cv_folds": cv_folds, "split_strategy": split_strategy},
                        "seed": seed, "code_version": code_version(), "metrics": scores,
                        "artifact_path": f"{identifier}/model.json", "operator": "train_plsda", "operator_version": 1,
                        "actor": "local", "duration_s": perf_counter()-started,
                        "env": {"python": sys.version, "numpy": np.__version__, "sklearn": sklearn.__version__},
                        "dataset_version_ref": dataset_version_ref,
                        "training_set_ref": None}
            threshold = {"confidence_threshold": float(confidence_threshold), "uncertain_pixels": int((predicted == -2).sum()),
                         "accepted_pixels": int((predicted >= 0).sum()), "total_pixels": len(y)}
            artifacts = {
                "confusion": {"scores": scores, "folds": [{"fold_index": f["fold_index"], **score} for f, score in zip(folds, fold_scores)],
                              "fold_summary": classification_fold_summary(fold_scores), "threshold": threshold, "lv": sweep, "manifest": manifest},
                "predictions": {"labels": labels.tolist(), "probabilities": probability.tolist(), "confidence": confidence.tolist(),
                                "y_true": y.tolist(), "y_pred": predicted.tolist(), "groups": groups.tolist(), "fold_index": fold_index.tolist()},
                "model": {"kind": "PLS-DA", "labels": labels.tolist(), "selected_lv": selected,
                          "probability": "softmax(z-max(z))", "confidence_threshold": float(confidence_threshold),
                          "coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(),
                          "x_mean": model._x_mean.tolist(), "x_std": model._x_std.tolist(),
                          "y_mean": model._y_mean.tolist(), "y_std": model._y_std.tolist(), "manifest": manifest},
                "lv_sweep": sweep}
            if band_selection == "ipls":
                artifacts["model"]["manifest"] = {**manifest, "band_selection": bands}
            storage.mkdir(folder, parents=True)
            records = []
            for kind, value in artifacts.items():
                raw = _json(value).encode("utf-8")
                storage.resolve_write(folder / (kind+".json"), kind="WRITE_BYTES").write_bytes(raw)
                records.append((str(uuid4()), identifier, kind, f"{identifier}/{kind}.json", hashlib.sha256(raw).hexdigest(), _now()))
            params.update(selected_lv=selected, best_lv=best["n_components"], by_elbow=elbow)
            with connect_database(self.database) as db:
                db.executemany("INSERT INTO metric VALUES (?,?,NULL,?,?,?,?)",
                    [(str(uuid4()), identifier, scope, name, scores[scope][name], _now())
                     for scope in ("pixel", "sample") for name in ("oa", "kappa")])
                db.executemany("INSERT INTO model_artifact VALUES (?,?,?,?,?,?)", records)
                db.execute("UPDATE training_run SET status='succeeded',finished_at=?,model_params=?,leak_report=? WHERE id=?",
                           (_now(), _json(params), _json(report), identifier))
        except Exception as error:
            for kind in ("model", "confusion", "predictions", "lv_sweep"):
                try:
                    storage.unlink(folder / (kind+".json"), missing_ok=True)
                except (OSError, DataError):
                    pass
            if folder.exists():
                try:
                    storage.resolve_delete(folder).rmdir()
                except (OSError, DataError):
                    pass
            detail = f"PLS-DA 拟合或持久化失败（{type(error).__name__}）"
            self._transition(identifier, "failed", report=report, error={"error": "PLSDA_FIT_FAILED", "detail": detail})
            raise ModelingError("PLSDA_FIT_FAILED", detail) from error
        return self.get(identifier)

    def regress(self, *, preprocess_run_ids, target_schema_id, task="regression", split_strategy="ks", test_ratio=1/3,
                cv_strategy="kfold", cv_folds=5, seed=17, n_components=None, max_components=None):
        from sklearn.cross_decomposition import PLSRegression

        if task != "regression" or split_strategy != "ks" or cv_strategy not in ("kfold", "loo"):
            raise ModelingError("INVALID_CV_PARAMS", "整样谱回归支持 KS 外层及 KFold/LOO 内层")
        data = build_sample_training_set(self.registry, self.paths, preprocess_run_ids=preprocess_run_ids, target_schema_id=target_schema_id)
        report = skipped_training_report()
        X, y, groups = data["X"], data["y"], data["groups"]
        split = kennard_stone(X, y, groups.tolist(), test_ratio=test_ratio)
        train, test = split["train_idx"], split["test_idx"]
        # One row per cube: group=cube is platform-derived. GroupKFold(K) is
        # equivalent to KFold's group exclusion here, not LOO unless K=n.
        # Future batches replace this group key; X/Y continue to join by cube.
        inner = plan_folds(y[train], groups[train], task="regression", strategy=cv_strategy,
                           folds=len(train) if cv_strategy == "loo" else cv_folds, seed=seed)
        maximum = min(X.shape[1], min(len(f["train_idx"])-1 for f in inner))
        if max_components is not None:
            maximum = min(maximum, max_components)
        if maximum < 1 or n_components is not None and not 1 <= n_components <= maximum:
            raise ModelingError("INVALID_LV", "LV 必须不超过内层训练样品数减一及特征数", maximum=maximum)
        report["coverage_repaired"] = split["coverage_repaired"]
        params = {"n_samples": len(y), "n_pixels_used": data["meta"]["n_pixels_used"],
                  "excluded_without_target": data["meta"]["excluded_without_target"], "test_ratio": test_ratio,
                  "train_cube_ids": groups[train].tolist(), "test_cube_ids": groups[test].tolist(),
                  "annotation_version_ids": [c["annotation_version_id"] for c in data["meta"]["cubes"]]}
        identifier = str(uuid4())
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            assert_runs_available(db,data['preprocess_run_ids'])
            db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,"
                       "cv_folds,seed,model_family,model_params,status,created_at,split_strategy,target_schema_id) "
                       "VALUES (?,?,?,?,?,?,?,?,?,'pls',?,'pending',?,'ks',?)",
                       (identifier, _json(groups.tolist()), _json(params["annotation_version_ids"]), _json(data["preprocess_run_ids"]),
                        task, data["target"], cv_strategy, len(inner), seed, _json(params), _now(), target_schema_id))
            # training_fold records the INNER CV folds here; the outer KS hold-out
            # lives only in model_params.train_cube_ids/test_cube_ids. 13.1
            # classification rows use the same table for evaluation folds, so do
            # not read this table across tasks without checking model_params.
            db.executemany("INSERT INTO training_fold VALUES (?,?,?,?,?,?,?)", [(str(uuid4()), identifier, f["fold_index"],
                           len(f["train_idx"]), len(f["test_idx"]), _json(f["train_groups"]), _json(f["test_groups"])) for f in inner])
        self._transition(identifier, "running", report=report)
        folder = self.paths.root / "models" / identifier
        try:
            curve = []
            for lv in range(1, maximum+1):
                errors, fold_rmse = [], []
                for fold in inner:
                    a, b = train[fold["train_idx"]], train[fold["test_idx"]]
                    model = PLSRegression(n_components=lv).fit(X[a], y[a])
                    residual = model.predict(X[b]).reshape(-1)-y[b]
                    errors.extend((residual**2).tolist())
                    fold_rmse.append(float(np.sqrt(np.mean(residual**2))))
                curve.append({"n_components": lv, "lv": lv, "rmsecv": float(np.sqrt(np.mean(errors))),
                              "sd": float(np.std(fold_rmse, ddof=1)) if len(inner) > 1 else 0.})
            best = min(curve, key=lambda point: (point["rmsecv"], point["n_components"]))
            elbow = next(point["n_components"] for point in curve if point["rmsecv"] <= best["rmsecv"]+best["sd"])
            selected = n_components if n_components is not None else best["n_components"]
            model = PLSRegression(n_components=selected).fit(X[train], y[train])
            calibration, prediction = model.predict(X[train]).reshape(-1), model.predict(X[test]).reshape(-1)
            metrics = {**_regression(y[train], calibration, "calibration"), **_regression(y[test], prediction, "prediction")}
            if set(metrics) != set(REGRESSION_METRICS):
                raise ModelingError("INVALID_METRIC_INPUT", "回归指标集合与七指标口径不符")
            sweep = {"curve": curve, "best_lv": best["n_components"], "elbow_lv": elbow, "selected_lv": selected,
                     "by_cv_min": best["n_components"], "by_elbow": elbow,
                     "manual_override": n_components is not None, "definition": "pooled held-out RMSECV; elbow <= best RMSECV + one SD of best fold RMSE"}
            predicted = {int(i): float(v) for indices, values in ((train, calibration), (test, prediction)) for i, v in zip(indices, values)}
            predictions = [{"cube_id": str(groups[i]), "set": "calibration" if i in train else "prediction",
                            "y_true": float(y[i]), "y_pred": predicted[i], "residual": predicted[i]-float(y[i])} for i in range(len(y))]
            storage.mkdir(folder, parents=True)
            artifacts = {"lv_sweep": sweep, "predictions": predictions,
                         "model": {"kind": "PLSRegression", "selected_lv": selected, "coef": model.coef_.tolist(),
                                   "intercept": model.intercept_.tolist(), "x_mean": model._x_mean.tolist()}}
            records = []
            for kind, value in artifacts.items():
                raw = _json(value).encode("utf-8")
                (storage.resolve_write(folder / (kind+".json"), kind="WRITE_BYTES")).write_bytes(raw)
                records.append((str(uuid4()), identifier, kind, f"{identifier}/{kind}.json", hashlib.sha256(raw).hexdigest(), _now()))
            params.update(selected_lv=selected, best_lv=best["n_components"], by_elbow=elbow)
            with connect_database(self.database) as db:
                db.executemany("INSERT INTO metric VALUES (?,?,NULL,'sample',?,?,?)",
                               [(str(uuid4()), identifier, name, value, _now()) for name, value in metrics.items()])
                db.executemany("INSERT INTO model_artifact VALUES (?,?,?,?,?,?)", records)
                db.execute("UPDATE training_run SET model_params=? WHERE id=?", (_json(params), identifier))
            self._transition(identifier, "succeeded", report=report)
        except Exception as error:
            # Only remove the three filenames created by this run, no recursive
            # cleanup of an application/user directory on failure. The cause is
            # chained (never from None) so tracebacks keep the failing frame;
            # only the exception type reaches the message, never its text.
            for kind in ("model", "predictions", "lv_sweep"):
                try:
                    storage.unlink(folder / (kind+".json"), missing_ok=True)
                except OSError:
                    pass
            if folder.exists():
                try:
                    folder.rmdir()
                except OSError:
                    pass
            detail = f"PLS 拟合或产物持久化失败（{type(error).__name__}）"
            self._transition(identifier, "failed", report=report, error={"error": "PLS_FIT_FAILED", "detail": detail})
            raise ModelingError("PLS_FIT_FAILED", detail) from error
        return self.get(identifier)
