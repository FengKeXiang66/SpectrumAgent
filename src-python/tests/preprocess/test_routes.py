"""11.4: all twelve HTTP operations reuse shipped stores and run/compare engines."""
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.api.preprocess import MAX_ARTIFACT_BYTES
from .run_fixtures import run_case, step


BASE = "/api/v1/preprocess"
SUMMARY_FIELDS = {"id", "status", "b01_branch", "input_fingerprint", "created_at", "finished_at", "error_code"}


@pytest.fixture
def preprocess_api(run_case):
    c = run_case
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    with connect_database(c.paths.database) as db:
        project = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (c.cube,)).fetchone()[0]
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer "+identity.token
        yield SimpleNamespace(c=c, client=client, app=app, project=project,
                              boot_id=identity.boot_id, pid=identity.pid,
                              runner=app.state.preprocess_runner, comparison=app.state.preprocess_compare)


def create(client, code="new", steps=None, **kwargs):
    return client.post(BASE+"/recipes", json={"code": code, "name": "测试配方", "description": "route fixture",
        "pipeline": {"steps": [] if steps is None else steps}, **kwargs})


def run_request(api, recipe=None, **kwargs):
    if recipe is None:
        recipe = api.c.recipe([])
    return api.client.post(f"/api/v1/datasets/{api.c.cube}/preprocess/runs", json={
        "annotation_version_id": api.c.version, "recipe_version_id": recipe, **kwargs})


def test_all_twelve_operations_success_and_delete_idempotence(preprocess_api):
    a = preprocess_api
    client = a.client
    assert client.get(BASE+"/recipes").status_code == 200
    made = create(client, note="first")
    assert made.status_code == 201, made.text
    recipe = made.json()
    recipe_id, version_id = recipe["id"], recipe["versions"][0]["id"]
    assert client.get(BASE+f"/recipes/{recipe_id}").json() == recipe
    added = client.post(BASE+f"/recipes/{recipe_id}/versions", json={"pipeline": {"steps": [step("snv")]}, "note": "second"})
    assert added.status_code == 201 and added.json()["version_no"] == 2
    assert client.get(BASE+f"/recipes/{recipe_id}").json()["versions"][0] == recipe["versions"][0]
    relation = BASE+f"/projects/{a.project}/recipes/{recipe_id}"
    first = client.post(relation)
    assert first.status_code == 200 and client.post(relation).json() == first.json()
    assert client.get(BASE+f"/projects/{a.project}/recipes").json()[0]["id"] == recipe_id
    for _ in range(2):
        deleted = client.delete(relation)
        assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(BASE+f"/projects/{a.project}/recipes").json() == []
    assert len(client.get(BASE+f"/recipes/{recipe_id}").json()["versions"]) == 2
    executed = run_request(a, version_id, block_size=3, guard="clip", note="run note")
    assert executed.status_code == 200, executed.text
    run = executed.json()
    assert run["status"] == "succeeded" and run["finished_at"] and run["note"] == "run note"
    assert run["b01_branch"] == "scale"
    details = client.get(BASE+f"/runs/{run['id']}")
    assert details.status_code == 200 and details.json() == run
    summaries = client.get(f"/api/v1/datasets/{a.c.cube}/preprocess/runs").json()
    assert len(summaries) == 1 and set(summaries[0]) == SUMMARY_FIELDS and summaries[0]["error_code"] is None
    npz = client.get(BASE+f"/runs/{run['id']}/artifacts/sample_spectra")
    assert npz.status_code == 200 and npz.headers["content-type"] == "application/octet-stream"
    with np.load(BytesIO(npz.content)) as data:
        expected = a.c.values[a.c.label_map == 0].mean(axis=0)/65535
        np.testing.assert_allclose(data["mean_0"], expected, rtol=0, atol=1e-12)
    report = client.get(BASE+f"/runs/{run['id']}/artifacts/report")
    assert report.status_code == 200 and report.headers["content-type"] == "application/json"
    assert report.json()["metrics"] == run["metrics"]
    versions = [added.json()["id"], version_id]
    compared = client.post(f"/api/v1/datasets/{a.c.cube}/preprocess/compare", json={
        "annotation_version_id": a.c.version, "recipe_version_ids": versions})
    assert compared.status_code == 200, compared.text
    assert [r["recipe_version_id"] for r in compared.json()["runs"]] == versions
    assert [r["fisher"] for r in compared.json()["ranking"]] == sorted(
        [r["fisher"] for r in compared.json()["ranking"]], reverse=True)
    assert len(compared.json()["boundaries"]) == 3


@pytest.mark.parametrize("body", [
    {"code": "", "name": "x", "pipeline": {"steps": []}},
    {"code": "x", "name": " ", "pipeline": {"steps": []}},
    {"code": "x", "name": "x", "pipeline": {"steps": [], "extra": 1}},
    {"code": "x", "name": "x", "pipeline": {"steps": [step("snv", unexpected=1)]}},
    {"code": "x", "name": "x", "pipeline": {"steps": []}, "unknown": True},
    {"code": "x", "name": "x", "pipeline": {"steps": []}, "note": "x"*2001},
    {"code": "x", "name": "x"},
])
def test_bad_recipe_body_structured_400(preprocess_api, body):
    response = preprocess_api.client.post(BASE+"/recipes", json=body)
    assert response.status_code == 400
    assert set(response.json()) == {"error", "detail", "context"}


def test_duplicate_code_and_version_bad_body_400(preprocess_api):
    a = preprocess_api
    made = create(a.client)
    assert made.status_code == 201
    assert create(a.client).status_code == 400
    for body in ({}, {"pipeline": {"steps": []}, "note": "x"*2001},
                 {"pipeline": {"steps": [step("snv", unexpected=1)]}}):
        assert a.client.post(BASE+f"/recipes/{made.json()['id']}/versions", json=body).status_code == 400


@pytest.mark.parametrize("method,path,body", [
    ("get", "/recipes/{unknown}", None),
    ("post", "/recipes/{unknown}/versions", {"pipeline": {"steps": []}}),
    ("get", "/projects/{unknown}/recipes", None),
    ("post", "/projects/{project}/recipes/{unknown}", None),
    ("delete", "/projects/{project}/recipes/{unknown}", None),
    ("get", "/runs/{unknown}", None),
    ("get", "/runs/{unknown}/artifacts/report", None),
])
def test_unknown_uuid_structured_404_and_invalid_uuid_400(preprocess_api, method, path, body):
    a = preprocess_api
    url = BASE+path.format(unknown=uuid4(), project=a.project)
    response = a.client.request(method, url, **({"json": body} if body is not None else {}))
    assert response.status_code == 404 and "context" in response.json()
    invalid = BASE+path.format(unknown="not-a-uuid", project=a.project)
    assert a.client.request(method, invalid, **({"json": body} if body is not None else {})).status_code == 400


@pytest.mark.parametrize("kind", ["processed_cube", "overlay", "unknown"])
def test_artifact_kind_is_only_two(preprocess_api, kind):
    response = preprocess_api.client.get(BASE+f"/runs/{uuid4()}/artifacts/{kind}")
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"


def test_failed_run_summary_excludes_context_and_artifact_is_404(preprocess_api):
    a = preprocess_api
    recipe = a.c.recipe([step("pca", n_components=9)])
    response = run_request(a, recipe)
    assert response.status_code == 200 and response.json()["status"] == "failed"
    row = response.json()
    assert row["error"]["error"] == "INVALID_OPERATOR_PARAMS" and row["finished_at"]
    detail = a.client.get(BASE+f"/runs/{row['id']}").json()
    assert detail["error"] == row["error"] and {"metrics", "scaler_params", "error"} <= detail.keys()
    listing = a.client.get(f"/api/v1/datasets/{a.c.cube}/preprocess/runs")
    assert listing.status_code == 200
    assert set(listing.json()[0]) == SUMMARY_FIELDS and listing.json()[0]["error_code"] == "INVALID_OPERATOR_PARAMS"
    assert not {"metrics", "scaler_params", "context", "error"} & listing.json()[0].keys()
    for kind in ("report", "sample_spectra"):
        assert a.client.get(BASE+f"/runs/{row['id']}/artifacts/{kind}").status_code == 404


def test_runs_list_default_recent_fifty_sorted_and_cube_isolated(preprocess_api):
    a = preprocess_api
    recipe = a.c.recipe([])
    with connect_database(a.c.paths.database) as db:
        for index in range(55):
            db.execute("INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,error,created_at) "
                "VALUES (?,?,?,?, 'scale','fingerprint','failed',?,?)", (str(uuid4()), a.c.cube, a.c.version, recipe,
                json.dumps({"error": "FAIL", "detail": "d", "context": {"large": "x"*10000}}), f"2026-10-21T00:00:{index:02d}+00:00"))
        db.execute("INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,created_at) "
                   "VALUES (?,?,?,?, 'scale','other','succeeded','2099')", (str(uuid4()), str(uuid4()), a.c.version, recipe))
    response = a.client.get(f"/api/v1/datasets/{a.c.cube}/preprocess/runs")
    rows = response.json()
    assert response.status_code == 200 and len(rows) == 50
    assert all(set(row) == SUMMARY_FIELDS and row["error_code"] == "FAIL" for row in rows)
    assert rows[0]["created_at"].endswith("54+00:00") and rows[-1]["created_at"].endswith("05+00:00")
    assert len(response.content) < 20000


@pytest.mark.parametrize("size,expected", [(MAX_ARTIFACT_BYTES, 200), (MAX_ARTIFACT_BYTES+1, 400)])
def test_artifact_size_guard_precedes_response(preprocess_api, size, expected):
    a = preprocess_api
    row = run_request(a).json()
    entry = next(item for item in row["artifacts"] if item["kind"] == "sample_spectra")
    path = a.c.paths.preprocessed/entry["relative_path"]
    with path.open("r+b") as stream:
        stream.truncate(size)
    response = a.client.get(BASE+f"/runs/{row['id']}/artifacts/sample_spectra")
    assert response.status_code == expected
    if expected == 400:
        assert response.json()["error"] == "ARTIFACT_TOO_LARGE" and response.json()["context"]["size"] == size
    else:
        assert len(response.content) == size


@pytest.mark.parametrize("relative", ["../outside", "/absolute", "C:/outside", "dir\\outside"])
def test_artifact_path_guard(preprocess_api, relative):
    a = preprocess_api
    row = run_request(a).json()
    with connect_database(a.c.paths.database) as db:
        db.execute("UPDATE preprocess_artifact SET relative_path=? WHERE run_id=? AND kind='report'", (relative, row["id"]))
    response = a.client.get(BASE+f"/runs/{row['id']}/artifacts/report")
    assert response.status_code == 400 and response.json()["error"] == "INVALID_ARTIFACT_PATH"


@pytest.mark.parametrize("changes", [{"extra": 1}, {"block_size": 0}, {"block_size": True},
    {"guard": "guess"}, {"note": "x"*2001}, {"annotation_version_id": "wrong"}])
def test_run_bad_body_400(preprocess_api, changes):
    response = run_request(preprocess_api, **changes)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"


def test_run_and_compare_preflight_errors_keep_404_and_409(preprocess_api):
    a = preprocess_api
    unknown = str(uuid4())
    for body in ({"annotation_version_id": unknown}, {"recipe_version_id": unknown}):
        assert run_request(a, **body).status_code == 404
    assert a.client.get(f"/api/v1/datasets/{unknown}/preprocess/runs").status_code == 404
    assert a.client.post(f"/api/v1/datasets/{unknown}/preprocess/runs", json={
        "annotation_version_id": a.c.version, "recipe_version_id": a.c.recipe([])}).status_code == 404
    recipe = a.c.recipe([step("pca", n_components=2)])
    del a.runner.operators.entries["pca"][1]
    stale = run_request(a, recipe)
    assert stale.status_code == 409 and stale.json()["error"] == "OPERATOR_VERSION_STALE"
    for versions, status in (([], 400), ([unknown], 404), ([recipe], 409)):
        response = a.client.post(f"/api/v1/datasets/{a.c.cube}/preprocess/compare", json={
            "annotation_version_id": a.c.version, "recipe_version_ids": versions})
        assert response.status_code == status


def test_single_registry_identity_headers_and_auth(preprocess_api):
    a = preprocess_api
    assert a.runner.registry is a.app.state.superpixel_engine.registry
    assert a.comparison.runner is a.runner
    for path in (BASE+"/recipes", BASE+f"/runs/{uuid4()}", f"/api/v1/datasets/{a.c.cube}/preprocess/runs"):
        response = a.client.get(path)
        assert response.headers["X-SpectrumAgent-Boot-Id"] == a.boot_id
        assert response.headers["X-SpectrumAgent-Pid"] == str(a.pid)
        unauth = a.client.get(path, headers={"Authorization": ""})
        assert unauth.status_code == 401 and "X-SpectrumAgent-Pid" not in unauth.headers


@pytest.mark.parametrize("method,path,store_method,body", [
    ("get", "/recipes", "list", None),
    ("post", "/recipes", "create", {"code": "v", "name": "v", "pipeline": {"steps": []}}),
    ("get", "/recipes/{recipe}", "get", None),
    ("post", "/recipes/{recipe}/versions", "add_version", {"pipeline": {"steps": []}}),
    ("post", "/projects/{project}/recipes/{recipe}", "select_project", None),
    ("delete", "/projects/{project}/recipes/{recipe}", "deselect_project", None),
    ("get", "/projects/{project}/recipes", "project_recipes", None)])
def test_store_bare_value_errors_never_escape_as_500(preprocess_api, monkeypatch, method, path, store_method, body):
    a = preprocess_api
    recipe = create(a.client).json()["id"]
    def fail(*args, **kwargs):
        raise ValueError("legacy store rejection")
    monkeypatch.setattr(a.runner.recipes, store_method, fail)
    response = a.client.request(method, BASE+path.format(recipe=recipe, project=a.project),
                               **({"json": body} if body is not None else {}))
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"


def test_compare_calls_runner_once_per_version_in_order_no_route_metrics(preprocess_api, monkeypatch):
    a = preprocess_api
    versions = [a.c.recipe([]), a.c.recipe([step("snv")])]
    calls = []
    def run(cube, annotation, recipe, **options):
        calls.append((cube, annotation, recipe, options))
        return {"id": str(uuid4()), "status": "succeeded", "recipe_version_id": recipe,
                "metrics": {"fisher": 1. if recipe == versions[0] else 9.}}
    monkeypatch.setattr(a.runner, "run", run)
    response = a.client.post(f"/api/v1/datasets/{a.c.cube}/preprocess/compare", json={
        "annotation_version_id": a.c.version, "recipe_version_ids": versions})
    assert response.status_code == 200
    assert calls == [(a.c.cube, a.c.version, recipe, {}) for recipe in versions]
    assert [row["fisher"] for row in response.json()["ranking"]] == [9., 1.]


def test_note_limit_accepts_exact_boundary(preprocess_api):
    a = preprocess_api
    response = create(a.client, note="n"*2000)
    assert response.status_code == 201
    recipe = response.json()
    assert len(recipe["versions"][0]["note"]) == 2000
    run = run_request(a, recipe["versions"][0]["id"], note="n"*2000)
    assert run.status_code == 200 and len(run.json()["note"]) == 2000
