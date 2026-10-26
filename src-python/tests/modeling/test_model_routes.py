from copy import deepcopy
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.modeling.run import TrainingRuns


@pytest.fixture
def model_api(model_case):
    c = model_case
    identity = EngineIdentity()
    with TestClient(create_app(c.paths, identity)) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        yield c, client


def body(c):
    return {**deepcopy(c.arguments), "task": "classification", "cv_strategy": "group_kfold", "cv_folds": 2, "seed": 17}


def count(c, table="training_run"):
    with connect_database(c.paths.database) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_three_routes_exact_shapes_sorted_list_and_no_models_or_metrics(model_api):
    c, client = model_api
    response = client.post("/api/v1/models/runs/preflight", json=body(c))
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {"run_id", "status", "leak_report", "folds", "n_samples", "n_features", "build_seconds"}
    assert result["status"] == "succeeded" and result["n_samples"] == 96 and result["n_features"] == 8
    assert "X-SpectrumAgent-Boot-Id" in response.headers
    for fold in result["folds"]:
        assert set(fold) == {"fold_index", "train_count", "test_count", "train_groups", "test_groups"}
        assert len(fold["train_groups"]) == len(fold["test_groups"]) == 2
        assert not set(fold["train_groups"]) & set(fold["test_groups"])
    details = client.get("/api/v1/models/runs/"+result["run_id"]).json()
    assert set(details) == {"run_id", "status", "task", "cv_strategy", "cv_folds", "n_samples", "leak_report", "folds", "metrics"}
    assert details["metrics"] == [] and details["n_samples"] == 96
    second = client.post("/api/v1/models/runs/preflight", json=body(c)).json()
    listing = client.get("/api/v1/models/runs", params={"cube_id": c.cubes[0]}).json()
    assert [r["id"] for r in listing] == [second["run_id"], result["run_id"]]
    assert all(set(row) == {"id", "status", "task", "created_at"} for row in listing)
    assert client.get("/api/v1/models/runs", params={"cube_id": "missing"}).json() == []
    assert client.get("/api/v1/models/runs/missing").status_code == 404
    assert count(c, "metric") == count(c, "model_artifact") == 0
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT model_family,model_params FROM training_run").fetchall() == [(None, None)]*2
    serialized = json.dumps([result, details, listing])
    for forbidden in ('"X"', '"y"', '"train_idx"', '"test_idx"', '"path"', '"relative_path"', '"predictions"'):
        assert forbidden not in serialized


@pytest.mark.parametrize("kind,code", [("length", "ARGUMENT_LENGTH_MISMATCH"), ("version", "VERSION_CUBE_MISMATCH"),
    ("run", "PREPROCESS_RUN_NOT_READY"), ("regression", "TARGET_UNSUPPORTED"),
    ("groups", "INSUFFICIENT_GROUPS"), ("shape", "LABEL_MAP_SHAPE_MISMATCH")])
def test_six_validation_errors_leave_zero_training_rows(model_api, kind, code):
    c, client = model_api
    request = body(c)
    if kind == "length":
        request["preprocess_run_ids"] = []
    elif kind == "version":
        request["annotation_version_ids"][0] = c.versions[1]
    elif kind == "run":
        with connect_database(c.paths.database) as db:
            db.execute("UPDATE preprocess_run SET status='running' WHERE id=?", (c.runs[0],))
    elif kind == "regression":
        request.update(task="regression", target="strength")
    elif kind == "groups":
        for key in ("cube_ids", "annotation_version_ids", "preprocess_run_ids"):
            request[key] = request[key][:1]
    else:
        with connect_database(c.paths.database) as db:
            ref = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=?", (c.versions[0],)).fetchone()[0]
        np.savez_compressed(c.paths.snapshots/ref/"label_map.npz", label_map=np.zeros((1, 1), np.int32))
    response = client.post("/api/v1/models/runs/preflight", json=request)
    assert response.status_code == 400 and response.json()["error"] == code, response.text
    assert count(c) == 0
    print(f"VALIDATION_ZERO_ROWS kind={kind} error={code} training_run=0")


@pytest.mark.parametrize("change", [{"cv_folds": True}, {"spectra": [[1, 2]]}, {"seed": "17"}])
def test_body_schema_refuses_before_writing(model_api, change):
    c, client = model_api
    response = client.post("/api/v1/models/runs/preflight", json={**body(c), **change})
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"
    assert count(c) == 0


def test_validation_order_is_all_versions_then_runs_then_task_then_groups(model_api):
    c, client = model_api
    request = body(c)
    request["preprocess_run_ids"][0] = "missing"
    request["annotation_version_ids"][3] = "missing"
    assert client.post("/api/v1/models/runs/preflight", json=request).json()["error"] == "VERSION_CUBE_MISMATCH"
    request["annotation_version_ids"] = c.versions
    request.update(task="regression", target="strength")
    assert client.post("/api/v1/models/runs/preflight", json=request).json()["error"] == "PREPROCESS_RUN_NOT_READY"
    request["preprocess_run_ids"] = c.runs
    for key in ("cube_ids", "annotation_version_ids", "preprocess_run_ids"):
        request[key] = request[key][:1]
    assert client.post("/api/v1/models/runs/preflight", json=request).json()["error"] == "TARGET_UNSUPPORTED"
    assert count(c) == 0


def test_duplicate_fingerprint_fails_run_with_structured_error_no_training(model_api):
    c, client = model_api
    with connect_database(c.paths.database) as db:
        fp = db.execute("SELECT input_fingerprint FROM preprocess_run WHERE id=?", (c.runs[0],)).fetchone()[0]
        db.execute("UPDATE preprocess_run SET input_fingerprint=? WHERE id=?", (fp, c.runs[1]))
    response = client.post("/api/v1/models/runs/preflight", json=body(c))
    assert response.status_code == 200 and response.json()["status"] == "failed"
    assert response.json()["leak_report"]["duplicate_content"]["duplicate_count"] > 0
    with connect_database(c.paths.database) as db:
        status, error, start, end = db.execute("SELECT status,error,started_at,finished_at FROM training_run").fetchone()
        assert status == "failed" and json.loads(error)["error"] == "LEAK_PREFLIGHT_FAILED" and start and end
    assert count(c, "metric") == count(c, "model_artifact") == 0


def test_lifecycle_and_random_request_explicitly_report_group_leakage(model_case, monkeypatch):
    c = model_case
    engine = TrainingRuns(c.registry, c.paths)
    transition, observed = engine._transition, []
    def observe(identifier, status, **kwargs):
        observed.append(engine.get(identifier)["status"])
        transition(identifier, status, **kwargs)
    monkeypatch.setattr(engine, "_transition", observe)
    result = engine.preflight(**body(c))
    assert result["status"] == "succeeded" and observed == ["pending", "running"]
    random = engine.preflight(**{**body(c), "cv_strategy": "random"})
    assert random["status"] == "failed" and random["leak_report"]["random_split_requested"] is True
    assert random["leak_report"]["preprocess_full_fit"]["affected_steps"] == ["standardize"]


def test_model_routes_authentication_still_required(model_api):
    c, client = model_api
    client.headers.pop("Authorization")
    assert client.post("/api/v1/models/runs/preflight", json=body(c)).status_code == 401
    assert client.get("/api/v1/models/runs").status_code == 401
    assert count(c) == 0


def test_reader_failure_does_not_expose_paths_or_create_training_run(model_api):
    c, client = model_api
    dataset, _ = c.registry.get(c.cubes[0])
    from pathlib import Path
    Path(dataset.data_path).unlink()
    response = client.post("/api/v1/models/runs/preflight", json=body(c))
    assert response.status_code == 400 and response.json()["error"] == "SOURCE_CHANGED"
    assert response.json()["context"] == {} and dataset.data_path not in response.text
    assert str(c.paths.root) not in response.text and count(c) == 0
