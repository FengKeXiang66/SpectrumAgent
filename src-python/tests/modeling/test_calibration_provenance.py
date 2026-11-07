"""TASK-33: real registration provenance, independent baseline arithmetic and read-only replay."""
import ast
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.modeling import ModelingError
from spectrumagent.modeling.dataset import build_sample_training_set
from spectrumagent.modeling.inference import apply_with_calibration
from spectrumagent.modeling.registry import encode, normalized_pipeline
from spectrumagent.preprocess import builtin_registry
from test_inference import trained, image_case
from test_registry import COEFFICIENT_KEYS


BASE_KEYS = {"protocol", "origin", "steps", "pipeline", "source_hashes", "recipe_version_ids",
             "input_n_features", "probe", "wavelengths", "model", "feature_min", "feature_max",
             "residual_interval", "limitation"}
REASON = "注册期使用整样均值谱拟合，预处理使用逐像素已标注谱拟合，两种拟合样本不同，标定参数不可互换。"
ERROR = "CALIBRATION_PROVENANCE_UNAVAILABLE"


@pytest.fixture
def registered(regression_factory):
    return trained(regression_factory)


def calibration(c):
    return c.models.get(c.model["id"], calibration=True)["calibration"]


def save_calibration(c, cal):
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE model_registry SET calibration=? WHERE id=?", (encode(cal), c.model["id"]))


def test_registration_preserves_all_fourteen_baseline_values_and_records_real_sources(registered):
    c = registered
    cal = calibration(c)
    data = build_sample_training_set(c.registry, c.paths, preprocess_run_ids=c.runs, target_schema_id=c.schema)
    raw = data["X_raw"]
    # Independent NumPy arithmetic for the fixture's standard scaler: no registry fit/meta used as oracle.
    mean, scale = raw.mean(axis=0), raw.std(axis=0, ddof=0)
    assert np.all(scale > 0)
    transformed = (raw - mean) / scale
    pipeline = normalized_pipeline(data["meta"]["cubes"][0]["pipeline"])
    assert len(pipeline["steps"]) == 1 and pipeline["steps"][0]["params"]["method"] == "standard"
    with connect_database(c.paths.database) as db:
        train_ids = json.loads(db.execute("SELECT model_params FROM training_run WHERE id=?",
                                         (c.result["run_id"],)).fetchone()[0])["train_cube_ids"]
        refs = json.loads(db.execute("SELECT preprocess_run_ids FROM training_run WHERE id=?",
                                    (c.result["run_id"],)).fetchone()[0])
        recipes = [db.execute("SELECT recipe_version_id FROM preprocess_run WHERE id=?", (ref,)).fetchone()[0]
                   for ref in refs]
        fingerprints = [db.execute("SELECT input_fingerprint FROM preprocess_run WHERE id=?", (ref,)).fetchone()[0]
                        for ref in refs]
    predictions = {row["cube_id"]: row for row in c.training.artifact(c.result["run_id"], "predictions")}
    residual = np.asarray([predictions[cube]["residual"] for cube in train_ids], dtype=float)
    residual_mean, residual_sd = float(residual.mean()), float(residual.std(ddof=1))
    mask = np.isin(data["groups"], train_ids)
    dataset, _ = c.registry.readable(data["groups"][0], raw=False)
    baseline = {
        "protocol": 1, "origin": "registration_reconstruction", "pipeline": pipeline,
        "steps": [{**pipeline["steps"][0], "meta": {"method": "standard",
                  "fitted": [{"mean": float(m), "std": float(s)} for m, s in zip(mean, scale)],
                  "n_spectra": len(raw), "zero_scale_count": 0}}],
        "source_hashes": [{"cube_id": row["cube_id"], **row["source_hashes"]} for row in data["meta"]["cubes"]],
        "recipe_version_ids": sorted(set(recipes)), "input_n_features": raw.shape[1],
        "probe": raw[0].tolist(), "wavelengths": np.asarray(dataset.wavelengths, dtype=np.float64).tolist(),
        "model": c.training.artifact(c.result["run_id"], "model"),
        "feature_min": transformed[mask].min(axis=0).tolist(),
        "feature_max": transformed[mask].max(axis=0).tolist(),
        "residual_interval": {"mean": residual_mean, "sd": residual_sd,
                              "low": residual_mean-residual_sd, "high": residual_mean+residual_sd,
                              "ddof": 1, "scope": "global_calibration_residual"},
        "limitation": "标定由注册时重建得出，非训练时实测值，可审计不可反证",
    }
    assert set(baseline) == BASE_KEYS and set(cal) == BASE_KEYS | {"provenance"}
    for key in BASE_KEYS:
        assert cal[key] == baseline[key], key
    assert cal["provenance"] == {
        "fit_scope": "sample_mean", "fit_sample_count": int(raw.shape[0]), "fitted_on": "registration",
        "source_preprocess_run_ids": refs, "source_input_fingerprints": fingerprints,
        "report_fit_scope": "labeled_pixels", "distinct_fit_populations": True,
        "non_interchangeable_reason": REASON,
    }
    assert set(c.models.coefficients(c.model["id"])) == COEFFICIENT_KEYS
    np.testing.assert_allclose(apply_with_calibration(cal, cal["pipeline"], raw), data["X"], rtol=0, atol=1e-12)


def test_new_target_run_succeeds_without_refit_or_provenance_mutation(registered, tmp_path, monkeypatch):
    c = registered
    cal = calibration(c)
    request, pixels, _ = image_case(c, tmp_path)
    assert request["preprocess_run_id"] not in cal["provenance"]["source_preprocess_run_ids"]
    calls = []
    def no_fit(*args, **kwargs):
        calls.append(True)
        raise AssertionError("frozen replay attempted to fit")
    operators = builtin_registry()
    for op in ("standardize", "pca", "mnf", "ica"):
        operators.entries[op][1] = replace(operators.resolve(op, 1), impl=no_fit)
    monkeypatch.setattr("spectrumagent.modeling.inference.builtin_registry", lambda: operators)
    flat = pixels.reshape(-1, pixels.shape[2])
    whole = apply_with_calibration(cal, cal["pipeline"], flat)
    for size in (8, 32):
        parts = np.concatenate([apply_with_calibration(cal, cal["pipeline"], flat[i:i+size])
                                for i in range(0, len(flat), size)])
        assert np.array_equal(parts, whole)
    result = c.engine.create(**request)
    assert result["status"] == "succeeded"
    assert {key: result["stats"][key] for key in (
        "calibration_origin", "fit_scope", "calibration_provenance_present")} == {
            "calibration_origin": "registration_reconstruction", "fit_scope": "sample_mean",
            "calibration_provenance_present": True}
    assert calls == []
    assert encode(calibration(c)).encode("utf-8") == encode(cal).encode("utf-8")


@pytest.mark.parametrize("legacy", ["missing", "null"])
def test_legacy_provenance_is_explicitly_observable_and_still_predicts(registered, tmp_path, legacy):
    c = registered
    request, _, _ = image_case(c, tmp_path)
    cal = calibration(c)
    if legacy == "missing":
        del cal["provenance"]
    else:
        cal["provenance"] = None
    save_calibration(c, cal)
    result = c.engine.create(**request)
    assert result["status"] == "succeeded"
    assert result["stats"]["calibration_provenance_present"] is False
    assert result["stats"]["fit_scope"] is None
    assert result["stats"]["calibration_origin"] == "registration_reconstruction"


def test_every_required_field_and_structure_mutation_fails_closed_without_writes(registered, tmp_path):
    c = registered
    request, _, _ = image_case(c, tmp_path)
    original = calibration(c)
    mutations = []
    for key in original["provenance"]:
        value = deepcopy(original["provenance"])
        del value[key]
        mutations.append(("missing:"+key, value))
    for key, bad in [("distinct_fit_populations", False), ("distinct_fit_populations", 1),
                     ("fit_scope", "labeled_pixels"), ("fitted_on", "inference"),
                     ("report_fit_scope", "sample_mean"), ("fit_sample_count", 0),
                     ("fit_sample_count", True), ("fit_sample_count", 1.5),
                     ("source_preprocess_run_ids", []), ("source_input_fingerprints", []),
                     ("source_preprocess_run_ids", "run"), ("source_input_fingerprints", [1]),
                     ("non_interchangeable_reason", ""), ("non_interchangeable_reason", None)]:
        value = deepcopy(original["provenance"])
        value[key] = bad
        mutations.append((key+":"+repr(bad), value))
    mutations.extend([("not-object", []), ("empty-object", {})])
    for name, value in mutations:
        cal = deepcopy(original)
        cal["provenance"] = value
        save_calibration(c, cal)
        with pytest.raises(ModelingError) as caught:
            c.engine.create(**request)
        assert caught.value.code == ERROR, name
        with connect_database(c.paths.database) as db:
            assert db.execute("SELECT count(*) FROM inference_run").fetchone()[0] == 0, name
            assert db.execute("SELECT count(*) FROM inference_artifact").fetchone()[0] == 0, name
        assert not (c.paths.root/"inferences").exists(), name


def test_source_list_lengths_do_not_bind_inference_targets(registered, tmp_path):
    c = registered
    cal = calibration(c)
    cal["provenance"]["source_input_fingerprints"] = cal["provenance"]["source_input_fingerprints"][:1]
    assert len(cal["provenance"]["source_input_fingerprints"]) != len(cal["provenance"]["source_preprocess_run_ids"])
    save_calibration(c, cal)
    request, _, _ = image_case(c, tmp_path)
    assert request["preprocess_run_id"] not in cal["provenance"]["source_preprocess_run_ids"]
    assert c.engine.create(**request)["status"] == "succeeded"


@pytest.mark.parametrize("missing", ["refs", "input_fingerprint"])
def test_registration_missing_provenance_sources_is_structured_and_never_invented(registered, monkeypatch, missing):
    c = registered
    if missing == "refs":
        with connect_database(c.paths.database) as db:
            db.execute("UPDATE training_run SET preprocess_run_ids='[]' WHERE id=?", (c.result["run_id"],))
    else:
        from spectrumagent.modeling import registry as module
        original = module.build_sample_training_set
        def missing_fingerprint(*args, **kwargs):
            data = original(*args, **kwargs)
            del data["meta"]["cubes"][0]["input_fingerprint"]
            return data
        monkeypatch.setattr(module, "build_sample_training_set", missing_fingerprint)
    with pytest.raises(ModelingError) as caught:
        c.models.register(c.result["run_id"])
    assert caught.value.code == ERROR
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM model_registry").fetchone()[0] == 1


def test_three_calibration_sources_are_not_interchanged_and_validation_has_no_target_id():
    source = Path(__file__).parents[2]/"spectrumagent"
    for path in (source/"modeling").rglob("*.py"):
        assert "scaler_params" not in path.read_text("utf-8"), path.name
    export = ast.parse((source/"preprocess/export.py").read_text("utf-8"))
    for node in ast.walk(export):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            assert not (isinstance(node.slice, ast.Constant) and node.slice.value == "calibration")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            assert not (node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "calibration")
    inference = ast.parse((source/"modeling/inference.py").read_text("utf-8"))
    assert not any(isinstance(node, ast.Name) and node.id == "report" for node in ast.walk(inference))
    prepare = next(node for node in ast.walk(inference) if isinstance(node, ast.FunctionDef) and node.name == "_prepare")
    check = next(node for node in ast.walk(prepare) if isinstance(node, ast.If)
                 and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name)
                 and node.test.left.id == "provenance")
    assert not any(isinstance(node, ast.Name) and node.id == "preprocess_run_id" for node in ast.walk(check))
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len"
                   for node in ast.walk(check))
