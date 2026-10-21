"""TASK-05 §5 B07: append-only global recipes, read-only project association."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError
from spectrumagent.preprocess.migrations import BUILTIN_CODE, BUILTIN_PIPELINE
from spectrumagent.preprocess.recipes import RecipeStore, input_fingerprint


PIPELINE = {"steps":[{"op":"standardize","version":1,"params":{"method":"standard"}}]}
DATASET = "11111111-1111-4111-8111-111111111111"
VERSION_A = "22222222-2222-4222-8222-222222222222"
VERSION_B = "33333333-3333-4333-8333-333333333333"
SOURCE_HASHES = {"sample.raw":hashlib.sha256(b"fixture binary").hexdigest(),
                 "sample.hdr":hashlib.sha256(b"fixture header").hexdigest()}


@pytest.fixture
def store(tmp_path):
    database = tmp_path / "recipes.sqlite3"
    DatasetRegistry(database)  # #04 migrations run first, no preprocess central assembly.
    return RecipeStore(database)


def test_builtin_exact_code_chain_versions_and_default_provenance(store):
    recipe = store.list()[0]
    assert recipe["code"] == BUILTIN_CODE == "plastic-snv-sg1" and recipe["builtin"] == 1
    assert "场景示例默认值、可改" in recipe["description"]
    assert recipe["versions"][0]["pipeline"] == BUILTIN_PIPELINE == {"steps":[
        {"op":"snv","version":1,"params":{}},
        {"op":"sg_derivative","version":1,"params":{"order":1,"window":15,"polyorder":2}}]}
    assert all(step["op"] != "reflectance" for step in recipe["versions"][0]["pipeline"]["steps"])
    store.registry.parse_pipeline(recipe["versions"][0]["pipeline"])


def test_create_append_versions_history_immutable_and_params_not_fitted(store):
    recipe = store.create("new","测试配方",None,PIPELINE,note="first")
    first = deepcopy(recipe["versions"][0])
    second_pipeline = {"steps":[{"op":"snv","version":1,"params":{}}]}
    second = store.add_version(recipe["id"],json.dumps(second_pipeline),note="second plain note")
    listed = store.get(recipe["id"])
    assert [row["version_no"] for row in listed["versions"]] == [1,2]
    assert listed["versions"][0] == first
    assert second["pipeline"] == second_pipeline and second["note"] == "second plain note"
    assert listed["versions"][0]["pipeline"] == PIPELINE
    assert "fitted" not in first["pipeline"]["steps"][0]["params"]
    listed["versions"][0]["pipeline"]["steps"].clear()
    assert store.get(recipe["id"])["versions"][0] == first
    assert [row["code"] for row in store.list()] == ["new","plastic-snv-sg1"]


def test_api_has_no_update_delete_or_overwrite_methods(store):
    for name in ("update","delete","overwrite","update_version","delete_recipe","delete_version"):
        assert not hasattr(store,name)


def test_project_selection_is_same_shared_recipe_not_copy_and_idempotent(store):
    recipe = store.create("shared","共享",None,PIPELINE)
    with connect_database(store.database) as db:
        project = db.execute("SELECT id FROM project").fetchone()[0]
        db.execute("INSERT INTO project (id,name,created_at) VALUES ('second','第二项目','fixture')")
    first = store.select_project(project,recipe["id"])
    assert store.select_project(project,recipe["id"]) == first
    store.select_project("second",recipe["id"])
    store.add_version(recipe["id"],{"steps":[{"op":"snv","version":1,"params":{}}]})
    for identifier in (project,"second"):
        selected = store.project_recipes(identifier)
        assert len(selected) == 1 and selected[0]["id"] == recipe["id"] and len(selected[0]["versions"]) == 2
    with connect_database(store.database) as db:
        assert db.execute("SELECT count(*) FROM project_recipe").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM preprocess_recipe WHERE code='shared'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM preprocess_recipe_version WHERE recipe_id=?",(recipe["id"],)).fetchone()[0] == 2


def test_bad_pipeline_before_write_and_duplicate_code_rollback(store):
    before = store.list()
    with pytest.raises(DataError) as caught:
        store.create("bad","坏配方",None,{"steps":[{"op":"standardize","version":1,"params":{"method":"guess"}}]})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS" and store.list() == before
    recipe = store.create("unique","唯一",None,PIPELINE)
    with pytest.raises(sqlite3.IntegrityError):
        store.create("unique","重复",None,PIPELINE)
    assert len(store.get(recipe["id"])["versions"]) == 1


def test_concurrent_appends_get_unique_monotonic_versions(store):
    recipe = store.create("concurrent","并发",None,PIPELINE)
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda _:store.add_version(recipe["id"],PIPELINE),range(8)))
    assert sorted(row["version_no"] for row in versions) == list(range(2,10))
    assert [row["version_no"] for row in store.get(recipe["id"])["versions"]] == list(range(1,10))


def test_store_never_executes_pipeline_or_creates_runs(store,monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail("11.2 must not execute a run")
    monkeypatch.setattr(store.registry,"run",forbidden)
    store.create("only_storage","仅存储",None,PIPELINE)
    with connect_database(store.database) as db:
        assert db.execute("SELECT count(*) FROM preprocess_run").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM preprocess_artifact").fetchone()[0] == 0


def test_fingerprint_really_switches_annotation_version_then_restores_without_io(monkeypatch):
    def forbidden(*args,**kwargs):
        pytest.fail("fingerprint must use supplied stored digests, never read source files")
    monkeypatch.setattr(Path,"open",forbidden)
    original = input_fingerprint(DATASET,SOURCE_HASHES,VERSION_A,6)
    changed = input_fingerprint(DATASET,SOURCE_HASHES,VERSION_B,6)
    restored = input_fingerprint(DATASET,SOURCE_HASHES,VERSION_A,6)
    assert original != changed and original == restored
    payload = "|".join([DATASET,SOURCE_HASHES["sample.hdr"],SOURCE_HASHES["sample.raw"],VERSION_A,"6"])
    assert original == hashlib.sha256(payload.encode()).hexdigest()


def test_fingerprint_order_repeatability_and_other_inputs():
    a = input_fingerprint(DATASET,SOURCE_HASHES,VERSION_A,6)
    assert input_fingerprint(DATASET,dict(reversed(list(SOURCE_HASHES.items()))),VERSION_A,6) == a
    assert input_fingerprint(DATASET,SOURCE_HASHES,VERSION_A,7) != a
    altered = dict(SOURCE_HASHES,**{"sample.raw":hashlib.sha256(b"changed fixture").hexdigest()})
    assert input_fingerprint(DATASET,altered,VERSION_A,6) != a


def test_default_recipe_can_execute_on_another_spectral_input(store):
    recipe = store.list()[0]
    x = np.arange(40,dtype=np.float64).reshape(2,20)+1
    result = store.registry.run(x,recipe["versions"][0]["pipeline"])
    assert result.spectra.shape == x.shape
