"""Classification preflight and synchronous sample-level PLS run lifecycle."""
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import PurePosixPath
import hashlib
from uuid import uuid4

import numpy as np
from sklearn.cross_decomposition import PLSRegression

from backend.database import connect_database
from . import ModelingError
from .cv import plan_folds, kennard_stone
from .dataset import _build, _inputs, build_sample_training_set
from .leak import preflight_report, sample_preflight_report
from .metrics import _regression, REGRESSION_METRICS


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


class TrainingRuns:
    def __init__(self, registry, paths):
        self.registry, self.paths, self.database = registry, paths, registry.database

    def _transition(self, identifier, status, *, report=None, error=None):
        stamp = "started_at" if status == "running" else "finished_at"
        with connect_database(self.database) as db:
            db.execute(f"UPDATE training_run SET status=?,{stamp}=?,leak_report=?,error=? WHERE id=?",
                       (status, _now(), _json(report) if report is not None else None,
                        _json(error) if error is not None else None, identifier))

    def preflight(self, *, cube_ids, annotation_version_ids, preprocess_run_ids, task, target, cv_strategy, cv_folds, seed, split_strategy="none"):
        rows = _inputs(self.registry, cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
                       preprocess_run_ids=preprocess_run_ids, target=target, task=task)
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
        report = preflight_report(data["meta"], folds, strategy=cv_strategy)
        summaries = [{"fold_index": f["fold_index"], "train_count": len(f["train_idx"]), "test_count": len(f["test_idx"]),
                      "train_groups": f["train_groups"], "test_groups": f["test_groups"]} for f in folds]
        identifier = str(uuid4())
        with connect_database(self.database) as db:
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
            return [dict(row) for row in db.execute("SELECT id,status,task,created_at FROM training_run" + where +
                    " ORDER BY created_at DESC,id DESC", (str(cube_id),) if cube_id else ())]

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

    def regress(self, *, preprocess_run_ids, target_schema_id, task="regression", split_strategy="ks", test_ratio=1/3,
                cv_strategy="kfold", cv_folds=5, seed=17, n_components=None, max_components=None):
        if task != "regression" or split_strategy != "ks" or cv_strategy not in ("kfold", "loo"):
            raise ModelingError("INVALID_CV_PARAMS", "整样谱回归支持 KS 外层及 KFold/LOO 内层")
        data = build_sample_training_set(self.registry, self.paths, preprocess_run_ids=preprocess_run_ids, target_schema_id=target_schema_id)
        report = sample_preflight_report(data["meta"], [], data["X_raw"])
        if not report["passed"]:
            raise ModelingError("LEAK_PREFLIGHT_FAILED", "泄漏预检阻断训练", leak_report=report)
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
        report = sample_preflight_report(data["meta"], inner, data["X_raw"])
        report["coverage_repaired"] = split["coverage_repaired"]
        params = {"n_samples": len(y), "n_pixels_used": data["meta"]["n_pixels_used"],
                  "excluded_without_target": data["meta"]["excluded_without_target"], "test_ratio": test_ratio,
                  "train_cube_ids": groups[train].tolist(), "test_cube_ids": groups[test].tolist(),
                  "annotation_version_ids": [c["annotation_version_id"] for c in data["meta"]["cubes"]]}
        identifier = str(uuid4())
        with connect_database(self.database) as db:
            db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,"
                       "cv_folds,seed,model_family,model_params,status,created_at,split_strategy,target_schema_id) "
                       "VALUES (?,?,?,?,?,?,?,?,?,'pls',?,'pending',?,'ks',?)",
                       (identifier, _json(groups.tolist()), _json(params["annotation_version_ids"]), _json(data["preprocess_run_ids"]),
                        task, data["target"], cv_strategy, len(inner), seed, _json(params), _now(), target_schema_id))
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
            assert set(metrics) == set(REGRESSION_METRICS)
            sweep = {"curve": curve, "best_lv": best["n_components"], "elbow_lv": elbow, "selected_lv": selected,
                     "by_cv_min": best["n_components"], "by_elbow": elbow,
                     "manual_override": n_components is not None, "definition": "pooled held-out RMSECV; elbow <= best RMSECV + one SD of best fold RMSE"}
            predicted = {int(i): float(v) for indices, values in ((train, calibration), (test, prediction)) for i, v in zip(indices, values)}
            predictions = [{"cube_id": str(groups[i]), "set": "calibration" if i in train else "prediction",
                            "y_true": float(y[i]), "y_pred": predicted[i], "residual": predicted[i]-float(y[i])} for i in range(len(y))]
            folder.mkdir(parents=True)
            artifacts = {"lv_sweep": sweep, "predictions": predictions,
                         "model": {"kind": "PLSRegression", "selected_lv": selected, "coef": model.coef_.tolist(),
                                   "intercept": model.intercept_.tolist(), "x_mean": model._x_mean.tolist()}}
            records = []
            for kind, value in artifacts.items():
                raw = _json(value).encode("utf-8")
                (folder / (kind+".json")).write_bytes(raw)
                records.append((str(uuid4()), identifier, kind, f"{identifier}/{kind}.json", hashlib.sha256(raw).hexdigest(), _now()))
            params.update(selected_lv=selected, best_lv=best["n_components"], by_elbow=elbow)
            with connect_database(self.database) as db:
                db.executemany("INSERT INTO metric VALUES (?,?,NULL,'sample',?,?,?)",
                               [(str(uuid4()), identifier, name, value, _now()) for name, value in metrics.items()])
                db.executemany("INSERT INTO model_artifact VALUES (?,?,?,?,?,?)", records)
                db.execute("UPDATE training_run SET model_params=? WHERE id=?", (_json(params), identifier))
            self._transition(identifier, "succeeded", report=report)
        except Exception:
            # Only remove the three filenames created by this run, no recursive
            # cleanup of an application/user directory on failure.
            for kind in ("model", "predictions", "lv_sweep"):
                try:
                    (folder / (kind+".json")).unlink(missing_ok=True)
                except OSError:
                    pass
            if folder.exists():
                try:
                    folder.rmdir()
                except OSError:
                    pass
            self._transition(identifier, "failed", report=report, error={"error": "PLS_FIT_FAILED", "detail": "PLS 拟合或产物持久化失败"})
            raise ModelingError("PLS_FIT_FAILED", "PLS 拟合或产物持久化失败") from None
        return self.get(identifier)
