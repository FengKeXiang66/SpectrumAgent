"""TASK-36: failures expose probability/metric drift, leakage or HTTP OOF leakage."""
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.database import connect_database
from spectrumagent.modeling import ModelingError
from spectrumagent.modeling.dataset import build_training_set
from spectrumagent.modeling.metrics import classification_scores, derive_classification
from spectrumagent.modeling.run import TrainingRuns, classification_probabilities
from spectrumagent.app import create_app
from backend.identity import EngineIdentity


def arguments(c, **changes):
    return {**c.arguments, "task": "classification", "cv_strategy": "group_kfold",
            "cv_folds": 2, "seed": 17, "split_strategy": "none", "max_components": 3, **changes}


def test_softmax_is_stable_normalized_and_argmax_preserving():
    raw = np.array([[10000., 10001., 9999.], [-10000., -10000., -10000.]])
    probability = classification_probabilities(raw)
    np.testing.assert_allclose(probability.sum(axis=1), 1.)
    np.testing.assert_allclose(probability[0], np.exp([-1., 0., -2.])/np.exp([-1., 0., -2.]).sum())
    np.testing.assert_allclose(probability[1], [1/3]*3)
    np.testing.assert_array_equal(probability.argmax(axis=1), raw.argmax(axis=1))
    assert np.isfinite(probability).all() and np.all((probability >= 0) & (probability <= 1))


def test_confusion_formulas_keep_undefined_classes_out_of_macro_f1():
    result = derive_classification({"oa": 2/3, "kappa": 0., "labels": [0, 1, 2],
                                    "confusion": [[2, 0, 0], [1, 0, 0], [0, 0, 0]]})
    assert result["per_class"][0] == {"label": 0, "precision": 2/3, "recall": 1., "f1": .8}
    assert result["per_class"][1] == {"label": 1, "precision": None, "recall": 0., "f1": None}
    assert result["per_class"][2] == {"label": 2, "precision": None, "recall": None, "f1": None}
    assert result["aa"] == .5 and result["macro_f1"] == .8


def test_rejection_excludes_uncertain_pixels_and_all_rejected_is_null():
    result = classification_scores([0, 1, 1, 0], [0, -2, 0, -2], [0, 0, 1, 1], labels=[0, 1])
    assert result["pixel"]["oa"] == .5
    assert sum(map(sum, result["pixel"]["confusion"])) == 2
    assert result["sample"]["oa"] == .5
    empty = classification_scores([0, 1], [-2, -2], [0, 1], labels=[0, 1])
    for scope in ("pixel", "sample"):
        assert empty[scope]["confusion"] == [[0, 0], [0, 0]]
        assert all(empty[scope][key] is None for key in ("oa", "kappa", "aa", "macro_f1"))


def test_real_classification_persists_metrics_and_oof_but_never_inlines_oof(model_case, monkeypatch):
    c = model_case
    engine = TrainingRuns(c.registry, c.paths)
    first = engine.classify(**arguments(c))
    second = engine.classify(**arguments(c))
    assert first["status"] == second["status"] == "succeeded"
    assert first["metrics"] == second["metrics"]
    assert first["confusion"]["scores"] == second["confusion"]["scores"]
    assert first["confusion"]["threshold"] == {"confidence_threshold": 0., "uncertain_pixels": 0,
                                               "accepted_pixels": 96, "total_pixels": 96}
    assert first["n_samples"] == 4 and first["n_pixels_used"] == 96
    assert 1 <= first["by_cv_min"] <= 3 and 1 <= first["by_elbow"] <= 3
    manifest = first["confusion"]["manifest"]
    assert manifest["annotation_version_ids"] == c.versions
    assert manifest["preprocess_run_ids"] == c.runs and manifest["seed"] == 17
    assert manifest["recipe_version_ids"] and manifest["code_version"]
    assert manifest["operator"] == "train_plsda" and manifest["duration_s"] >= 0
    predictions = engine.artifact(first["run_id"], "predictions")
    probability = np.asarray(predictions["probabilities"])
    assert probability.shape == (96, 2)
    np.testing.assert_allclose(probability.sum(axis=1), 1.)
    assert set(predictions["y_true"]) == {0, 1}
    assert set(predictions["fold_index"]) == {0, 1}
    with connect_database(c.paths.database) as db:
        assert set(db.execute("SELECT scope,name FROM metric WHERE run_id=?", (first["run_id"],))) == {
            (scope, name) for scope in ("pixel", "sample") for name in ("oa", "kappa")}
        assert db.execute("SELECT count(*) FROM metric WHERE run_id=?", (first["run_id"],)).fetchone()[0] == 4
    listing = next(row for row in engine.list() if row["id"] == first["run_id"])
    assert listing["oa"] == first["metrics"]["sample"]["oa"]
    assert listing["kappa"] == first["metrics"]["sample"]["kappa"]
    assert listing["lv"] == first["selected_lv"]
    original = engine.artifact
    def bounded(identifier, kind):
        assert kind != "predictions", "OOF must stay off HTTP reads"
        return original(identifier, kind)
    monkeypatch.setattr(engine, "artifact", bounded)
    assert "predictions" not in json.dumps([engine.get(first["run_id"]), engine.list()])


def test_manual_lv_and_explicit_threshold_are_saved(model_case):
    c = model_case
    result = TrainingRuns(c.registry, c.paths).classify(**arguments(c, n_components=1, confidence_threshold=.99))
    assert result["selected_lv"] == 1 and result["confusion"]["lv"]["manual_override"] is True
    threshold = result["confusion"]["threshold"]
    assert threshold["confidence_threshold"] == .99
    assert threshold["accepted_pixels"] + threshold["uncertain_pixels"] == 96


def test_raw_sample_means_feed_existing_cosine_preflight(model_case):
    c = model_case
    data = build_training_set(c.registry, c.paths, **c.arguments)
    np.testing.assert_allclose(data["sample_means_raw"], [x[m >= 0].mean(axis=0) for x, m in zip(c.values, c.maps)])


def test_duplicate_input_blocks_before_fitting(model_case, monkeypatch):
    c = model_case
    with connect_database(c.paths.database) as db:
        fp = db.execute("SELECT input_fingerprint FROM preprocess_run WHERE id=?", (c.runs[0],)).fetchone()[0]
        db.execute("UPDATE preprocess_run SET input_fingerprint=? WHERE id=?", (fp, c.runs[1]))
    monkeypatch.setattr("spectrumagent.modeling.run.PLSRegression.fit", lambda *a, **k: pytest.fail("leaking inputs reached fit"))
    with pytest.raises(ModelingError) as failure:
        TrainingRuns(c.registry, c.paths).classify(**arguments(c))
    assert failure.value.code == "LEAK_PREFLIGHT_FAILED"
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM model_artifact").fetchone()[0] == 0


def test_near_duplicate_raw_means_also_block_before_fitting(model_case, monkeypatch):
    c = model_case
    engine = TrainingRuns(c.registry, c.paths)
    prepare = engine._preflight_data
    def near_duplicates(**kwargs):
        rows, data, folds, report = prepare(**kwargs)
        data["sample_means_raw"][1] = data["sample_means_raw"][0]*2
        return rows, data, folds, report
    monkeypatch.setattr(engine, "_preflight_data", near_duplicates)
    monkeypatch.setattr("spectrumagent.modeling.run.PLSRegression.fit", lambda *a, **k: pytest.fail("near duplicates reached fit"))
    with pytest.raises(ModelingError) as failure:
        engine.classify(**arguments(c))
    assert failure.value.code == "LEAK_PREFLIGHT_FAILED"
    assert failure.value.payload.context["leak_report"]["near_duplicate_spectra"]["pair_count"] >= 1


def test_failed_artifact_write_leaves_failed_run_without_metrics_or_artifact_rows(model_case, monkeypatch):
    c = model_case
    from spectrumagent.storage import guard
    resolve = guard.resolve_write
    def fail_confusion(path, *, kind):
        if path.name == "confusion.json":
            raise OSError("controlled write failure")
        return resolve(path, kind=kind)
    monkeypatch.setattr(guard, "resolve_write", fail_confusion)
    with pytest.raises(ModelingError) as failure:
        TrainingRuns(c.registry, c.paths).classify(**arguments(c))
    assert failure.value.code == "PLSDA_FIT_FAILED"
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT status FROM training_run").fetchone()[0] == "failed"
        assert db.execute("SELECT count(*) FROM metric").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM model_artifact").fetchone()[0] == 0
    assert not list((c.paths.root/"models").glob("*/*.json"))


@pytest.mark.parametrize("change", [{"cv_strategy": "random"}, {"split_strategy": "ks"},
                                    {"confidence_threshold": 1}, {"confidence_threshold": -.1},
                                    {"n_components": 21}])
def test_classification_cannot_disable_grouping_or_use_invalid_threshold_lv(model_case, change):
    c = model_case
    with pytest.raises(ModelingError):
        TrainingRuns(c.registry, c.paths).classify(**arguments(c, **change))
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM training_run").fetchone()[0] == 0


@pytest.fixture
def classification_api(model_case):
    c = model_case
    identity = EngineIdentity()
    with TestClient(create_app(c.paths, identity)) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield c, client


def test_existing_runs_route_dispatches_classification_and_reads_bounded_results(classification_api):
    c, client = classification_api
    response = client.post("/api/v1/models/runs", json=arguments(c))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["task"] == "classification" and result["group_by"] == "sample_id"
    assert result["confusion"]["threshold"]["confidence_threshold"] == 0
    detail = client.get("/api/v1/models/runs/" + result["run_id"]).json()
    assert detail == result
    listing = client.get("/api/v1/models/runs").json()
    assert set(listing[0]) == {"id", "task", "status", "created_at", "oa", "kappa", "lv"}
    assert listing[0]["oa"] == result["metrics"]["sample"]["oa"]
    assert listing[0]["kappa"] == result["metrics"]["sample"]["kappa"]
    assert "predictions" not in json.dumps([detail, listing])


@pytest.mark.parametrize("change", [{"unknown": 1}, {"cv_strategy": "random"}, {"cv_strategy": "kfold"},
    {"split_strategy": "ks"}, {"confidence_threshold": 1}, {"confidence_threshold": True},
    {"confidence_threshold": -.1}, {"n_components": 21}, {"target": "strength"}, {"seed": "17"}])
def test_classification_schema_refuses_invalid_inputs_before_writing(classification_api, change):
    c, client = classification_api
    response = client.post("/api/v1/models/runs", json={**arguments(c), **change})
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST", response.text
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM training_run").fetchone()[0] == 0


def test_five_fold_training_through_existing_http_route(regression_factory):
    c = regression_factory(10)
    identity = EngineIdentity()
    request = {"cube_ids": c.cubes, "annotation_version_ids": c.versions, "preprocess_run_ids": c.runs,
               "task": "classification", "target": "label", "cv_strategy": "group_kfold", "cv_folds": 5,
               "seed": 17, "split_strategy": "none", "confidence_threshold": 0, "max_components": 2}
    with TestClient(create_app(c.paths, identity)) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        response = client.post("/api/v1/models/runs", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "succeeded" and result["cv_folds"] == 5
    assert len(result["confusion"]["folds"]) == 5
    assert result["confusion"]["threshold"]["uncertain_pixels"] == 0


def test_manifest_records_actual_estimator_defaults_and_runtime_versions(model_case):
    c = model_case
    result = TrainingRuns(c.registry, c.paths).classify(**arguments(c, n_components=1))
    manifest = result["confusion"]["manifest"]
    with connect_database(c.paths.database) as db:
        params = json.loads(db.execute("SELECT model_params FROM training_run WHERE id=?", (result["run_id"],)).fetchone()[0])
    assert {"n_components", "scale", "max_iter", "tol", "copy"} <= params["estimator"].keys()
    assert params["estimator"]["n_components"] == 1
    assert params["estimator"] == manifest["params"]["estimator"]
    assert params["operator"] == {"name": "train_plsda", "version": 1}
    assert all(manifest["env"][name] for name in ("python", "numpy", "sklearn"))
