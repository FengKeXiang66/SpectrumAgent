"""Synchronous data/CV preflight lifecycle; no model or metric is produced."""
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from backend.database import connect_database
from . import ModelingError
from .cv import plan_folds
from .dataset import _build, _inputs
from .leak import preflight_report


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

    def preflight(self, *, cube_ids, annotation_version_ids, preprocess_run_ids, task, target, cv_strategy, cv_folds, seed):
        rows = _inputs(self.registry, cube_ids=cube_ids, annotation_version_ids=annotation_version_ids,
                       preprocess_run_ids=preprocess_run_ids, target=target, task=task)
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
