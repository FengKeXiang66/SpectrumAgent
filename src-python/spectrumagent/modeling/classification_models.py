"""Classification-specific registration without fake continuous target schemas."""
import json
from uuid import uuid4
import numpy as np
from backend.database import connect_database
from . import ModelingError
from .evaluation import Evaluations, encode, digest, stamp


class ClassificationModels:
    def __init__(self, registry, paths):
        self.store = Evaluations(registry, paths)
        self.registry, self.paths, self.database = registry, paths, registry.database

    def register(self, evaluation_id, name=None):
        ev = self.store.get(evaluation_id)
        if ev.get('complete') is False:
            raise ModelingError('INCOMPLETE_EVALUATION', '部分结果不能登记为完整模型评价')
        pack = self.store.artifact(evaluation_id, "model")
        label = (name or "PLS-DA").strip()
        if not label or len(label) > 200:
            raise ModelingError("INVALID_MODEL_NAME", "模型名称须为1至200字")
        coefficient = np.asarray(pack["model"]["coef"])
        if coefficient.shape != (len(ev["classes"]), len(pack["columns"])) or not np.isfinite(coefficient).all():
            raise ModelingError("INVALID_MODEL_ARTIFACT", "分类系数与类别/特征轴不匹配")
        with connect_database(self.database, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            status = db.execute("SELECT status FROM training_run WHERE id=?", (ev["run_id"],)).fetchone()
            if not status or status[0] != "succeeded":
                raise ModelingError("RUN_NOT_READY", "仅成功的分类训练可注册")
            prior = db.execute("SELECT id FROM classification_model WHERE evaluation_id=? AND name=?", (evaluation_id, label)).fetchone()
            if prior:
                identifier = prior[0]
            else:
                projects = {db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (c["cube_id"],)).fetchone()[0]
                            for c in ev["cubes"]}
                if len(projects) != 1:
                    raise ModelingError("PROJECT_MISMATCH", "分类模型须属于同一项目")
                version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM classification_model WHERE name=?", (label,)).fetchone()[0]
                identifier = str(uuid4())
                db.execute("INSERT INTO classification_model VALUES (?,?,?,?,?,?,?,?,'experiment',?)",
                           (identifier, ev["run_id"], evaluation_id, label, version, next(iter(projects)),
                            digest([c["id"] for c in ev["classes"]]), ev["artifacts"]["model"]["sha256"], stamp()))
        return self.get(identifier)

    def get(self, identifier, calibration=False):
        with connect_database(self.database) as db:
            row = db.execute("SELECT id,run_id,evaluation_id,name,version,project_id,catalog_hash,model_hash,stage,created_at "
                             "FROM classification_model WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise ModelingError("MODEL_NOT_FOUND", "分类模型版本不存在")
        fields = ("id", "run_id", "evaluation_id", "name", "version", "project_id", "catalog_hash", "model_hash", "stage", "created_at")
        result = dict(zip(fields, row))
        ev = self.store.get(result["evaluation_id"])
        pack = self.store.artifact(result["evaluation_id"], "model")
        if ev["artifacts"]["model"]["sha256"] != result["model_hash"]:
            raise ModelingError("ARTIFACT_HASH_MISMATCH", "注册模型与冻结训练产物不一致")
        result.update(task="classification", quality_label=None, deployable=True,
                      classes=ev["classes"], protocol=ev["protocol"],
                      metrics={k: ev["populations"]["accepted"]["scores"]["sample"][k] for k in ("oa", "aa", "kappa", "macro_f1")},
                      applicability={"task": "classification", "n_features": len(pack["columns"]),
                                     "wavelength_axis_sha256": digest(pack["input_wavelengths"])},
                      target_schema_id=None, data_fingerprint=digest(ev["input_identity"]))
        if calibration:
            result["calibration"] = pack
        return result

    def list(self):
        with connect_database(self.database) as db:
            ids = [r[0] for r in db.execute("SELECT id FROM classification_model ORDER BY name,version DESC,id")]
        return [self.get(identifier) for identifier in ids]

    def set_stage(self, identifier, stage):
        if stage not in ("experiment", "candidate"):
            raise ModelingError("INVALID_MODEL_STAGE", "分类版本仅开放实验/候选；基线不等于生产")
        self.get(identifier)
        with connect_database(self.database) as db:
            db.execute("UPDATE classification_model SET stage=? WHERE id=?", (stage, identifier))
        return self.get(identifier)

    def baseline(self, identifier, clear=False):
        model = self.get(identifier)
        ev = self.store.get(model["evaluation_id"])
        scope = encode({"project": model["project_id"], "task": "classification", "catalog": model["catalog_hash"],
                        "protocol": ev["protocol"], "definition": ev["definition"]})
        with connect_database(self.database) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT model_id FROM classification_baseline WHERE scope_key=?", (scope,)).fetchone()
            if clear:
                db.execute("DELETE FROM classification_baseline WHERE scope_key=?", (scope,))
            else:
                db.execute("INSERT INTO classification_baseline VALUES (?,?,?,?) ON CONFLICT(scope_key) "
                           "DO UPDATE SET model_id=excluded.model_id,evaluation_id=excluded.evaluation_id,updated_at=excluded.updated_at",
                           (scope, identifier, model["evaluation_id"], stamp()))
            db.execute("INSERT INTO classification_baseline_event VALUES (?,?,?,?,?)",
                       (str(uuid4()), scope, old[0] if old else None, None if clear else identifier, stamp()))
        return {"model_id": identifier, "evaluation_id": model["evaluation_id"], "stage": model["stage"],
                "baseline": not clear, "previous_model_id": old[0] if old else None}
