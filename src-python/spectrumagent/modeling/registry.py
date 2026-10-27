"""Versioned sample-PLS registration; reconstructed calibration is auditable, not historical proof."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.registry import validate
from . import ModelingError
from .dataset import build_sample_training_set
from .run import TrainingRuns


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def now():
    return datetime.now(timezone.utc).isoformat()


def axis_sha256(values):
    return hashlib.sha256(np.ascontiguousarray(values, dtype=np.float64).tobytes()).hexdigest()


def data_fingerprint(triples):
    return hashlib.sha256(encode(sorted(tuple(row) for row in triples)).encode("utf-8")).hexdigest()


def normalized_pipeline(value):
    operators = builtin_registry()
    pipeline = operators.parse_pipeline(value)
    return json.loads(encode({"steps": [{"op": step.op, "version": step.version,
                      "params": validate(operators.resolve(step.op, step.version).model, step.params,
                                         f"steps.{i}.params").model_dump()}
                     for i, step in enumerate(pipeline.steps)]}))


def missing(code, message):
    error = ModelingError(code, message)
    error.status_code = 404
    return error


class ModelRegistry:
    def __init__(self, registry, paths):
        self.registry, self.paths, self.database = registry, paths, registry.database

    def get(self, identifier, *, calibration=False):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM model_registry WHERE id=?", (str(identifier),)).fetchone()
            if row is None:
                raise missing("MODEL_NOT_FOUND", "注册模型不存在")
            result = dict(row)
            result["applicability"] = json.loads(result["applicability"])
            if calibration:
                result["calibration"] = json.loads(result["calibration"])
            else:
                result.pop("calibration")
            result["metrics"] = dict(db.execute(
                "SELECT name,value FROM metric WHERE run_id=? AND scope='sample' AND fold_index IS NULL",
                (result["run_id"],)))
        rpd = result["metrics"].get("rpd")
        result["quality_label"] = "仅可做半定量" if rpd is not None and rpd < 2.5 else None
        return result

    def list(self):
        with connect_database(self.database) as db:
            ids = [row[0] for row in db.execute("SELECT id FROM model_registry ORDER BY name,version DESC,id")]
        return [self.get(identifier) for identifier in ids]

    def register(self, run_id, name=None):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM training_run WHERE id=?", (str(run_id),)).fetchone()
            if row is None:
                raise missing("RUN_NOT_FOUND", "训练 run 不存在")
            run = dict(row)
        if run["task"] != "regression":
            raise ModelingError("UNSUPPORTED_TASK", "只有已训练的回归模型可注册")
        if run["status"] != "succeeded":
            raise ModelingError("RUN_NOT_READY", "只有成功的训练 run 可注册")
        label = name if name is not None else (
            f"{run['model_family']}-{run['target']}" if run["model_family"] else run["target"])
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ModelingError("INVALID_MODEL_NAME", "模型名称须为不超过200字的非空文本")
        label = label.strip()
        artifacts = TrainingRuns(self.registry, self.paths)
        model = artifacts.artifact(run_id, "model")
        predictions = artifacts.artifact(run_id, "predictions")
        refs = json.loads(run["preprocess_run_ids"])
        try:
            data = build_sample_training_set(self.registry, self.paths, preprocess_run_ids=refs,
                                             target_schema_id=run["target_schema_id"])
            if data["groups"].tolist() != json.loads(run["cube_ids"]) or [
                row["annotation_version_id"] for row in data["meta"]["cubes"]
            ] != json.loads(run["annotation_version_ids"]):
                raise ModelingError("TRAINING_REFERENCE_CHANGED", "训练引用或目标取值已缺失")
        except (DataError, OSError, ValueError) as error:
            raise ModelingError("TRAINING_DATA_UNAVAILABLE",
                                "训练数据已不可读，请在数据仍可访问时注册") from error
        with connect_database(self.database) as db:
            recipes = [db.execute("SELECT recipe_version_id FROM preprocess_run WHERE id=?", (ref,)).fetchone()[0]
                       for ref in refs]
        pipeline = normalized_pipeline(data["meta"]["cubes"][0]["pipeline"])
        dataset, _ = self.registry.readable(data["groups"][0], raw=False)
        axis = np.asarray(dataset.wavelengths, dtype=np.float64)
        # Rebuild once for IO, then repeat the small mean matrix pipeline to obtain public .steps.
        # 13.2 never stored those records; no changes to that training contract.
        fitted = builtin_registry().run(data["X_raw"], pipeline, wavelengths=axis if axis.size else None)
        if not np.isfinite(fitted.spectra).all():
            raise ModelingError("NON_FINITE_SPECTRA", "注册标定结果含非有限值")
        original = {row["cube_id"]: row for row in predictions}
        train_ids = json.loads(run["model_params"])["train_cube_ids"]
        train_mask = np.isin(data["groups"], train_ids)
        if not train_mask.any() or set(original) != set(data["groups"].tolist()):
            raise ModelingError("INVALID_MODEL_ARTIFACT", "模型训练样品引用不完整")
        ys = np.asarray([original[cube]["y_true"] for cube in train_ids], dtype=float)
        residual = np.asarray([original[cube]["residual"] for cube in train_ids], dtype=float)
        if not np.isfinite(ys).all() or not np.isfinite(residual).all():
            raise ModelingError("INVALID_MODEL_ARTIFACT", "训练目标或残差含非有限值")
        sd = float(residual.std(ddof=1)) if len(residual) > 1 else None
        mean = float(residual.mean())
        calibration = {
            "protocol": 1, "origin": "registration_reconstruction",
            "steps": fitted.steps, "pipeline": pipeline,
            "source_hashes": [{"cube_id": row["cube_id"], **row["source_hashes"]} for row in data["meta"]["cubes"]],
            "recipe_version_ids": sorted(set(recipes)), "input_n_features": data["X_raw"].shape[1],
            "probe": data["X_raw"][0].tolist(), "wavelengths": axis.tolist(), "model": model,
            "feature_min": fitted.spectra[train_mask].min(axis=0).tolist(),
            "feature_max": fitted.spectra[train_mask].max(axis=0).tolist(),
            "residual_interval": {"mean": mean, "sd": sd, "low": mean - sd if sd is not None else None,
                                  "high": mean + sd if sd is not None else None, "ddof": 1,
                                  "scope": "global_calibration_residual"},
            "limitation": "标定由注册时重建得出，非训练时实测值，可审计不可反证",
        }
        from .inference import apply_with_calibration, predict
        rebuilt = apply_with_calibration(calibration, pipeline, data["X_raw"])
        if not np.allclose(rebuilt, fitted.spectra, rtol=1e-10, atol=1e-12):
            raise ModelingError("CALIBRATION_MISMATCH", "标定重放与注册重建结果不一致")
        predict(rebuilt, model)  # Validate the frozen model dimensions before writing anything.
        applicability = {
            "y_min": float(ys.min()), "y_max": float(ys.max()),
            "n_features": fitted.spectra.shape[1], "wavelength_axis_sha256": axis_sha256(axis),
            "recipe_version_id": min(recipes), "target_schema_id": run["target_schema_id"], "task": "regression",
        }
        triples = [(row["cube_id"], row["annotation_version_id"], recipe)
                   for row, recipe in zip(data["meta"]["cubes"], recipes)]
        identifier = str(uuid4())
        # Heavy calibration stays outside the write transaction; MAX+INSERT are atomic across connections.
        with connect_database(self.database, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM model_registry WHERE name=?", (label,)).fetchone()[0]
            db.execute("INSERT INTO model_registry (id,run_id,name,version,target_schema_id,data_fingerprint,"
                       "applicability,calibration,stage,created_at) VALUES (?,?,?,?,?,?,?,?,'experiment',?)",
                       (identifier, run_id, label, version, run["target_schema_id"], data_fingerprint(triples),
                        encode(applicability), encode(calibration), now()))
        return self.get(identifier)

    def set_stage(self, identifier, stage):
        if stage not in ("experiment", "candidate", "production"):
            raise ModelingError("INVALID_MODEL_STAGE", "模型阶段须为实验、候选或生产")
        with connect_database(self.database, timeout=30) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT target_schema_id FROM model_registry WHERE id=?", (str(identifier),)).fetchone()
            if row is None:
                raise missing("MODEL_NOT_FOUND", "注册模型不存在")
            if stage == "production":
                db.execute("UPDATE model_registry SET stage='candidate' WHERE target_schema_id=? "
                           "AND stage='production' AND id<>?", (row[0], str(identifier)))
            db.execute("UPDATE model_registry SET stage=? WHERE id=?", (stage, str(identifier)))
        return self.get(identifier)
