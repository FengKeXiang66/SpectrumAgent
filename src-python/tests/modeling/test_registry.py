"""13.4 registration transactions, frozen calibration and explicit failure."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
from uuid import uuid4

import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.modeling import ModelingError
from spectrumagent.modeling.dataset import build_sample_training_set
from spectrumagent.modeling.registry import ModelRegistry, data_fingerprint, normalized_pipeline
from spectrumagent.modeling.run import TrainingRuns
from spectrumagent.preprocess import builtin_registry
from spectrumagent.modeling.inference import apply_with_calibration


@contextmanager
def fails(code):
    with pytest.raises(ModelingError) as caught:
        yield caught
    assert caught.value.code == code


def trained(factory, pipeline=None):
    c = factory()
    c.targets.import_csv(c.project, c.csv_text)
    if pipeline is not None:
        with connect_database(c.paths.database) as db:
            db.execute("UPDATE preprocess_recipe_version SET pipeline=?", (json.dumps(pipeline),))
    c.training = TrainingRuns(c.registry, c.paths)
    c.result = c.training.regress(**c.arguments)
    assert c.result["status"] == "succeeded"
    c.models = ModelRegistry(c.registry, c.paths)
    return c


def test_registration_versions_identity_domain_and_null_family(regression_factory):
    c = trained(regression_factory)
    with connect_database(c.paths.database) as db:
        old_sql = db.execute("SELECT sql FROM sqlite_master WHERE name='model_artifact'").fetchone()[0]
        db.execute("UPDATE training_run SET model_family=NULL")
    a = c.models.register(c.result["run_id"])
    b = c.models.register(c.result["run_id"])
    assert (a["name"], a["version"], b["version"]) == ("含量", 1, 2)
    assert a["data_fingerprint"] == b["data_fingerprint"]
    assert a["stage"] == "experiment" and a["target_schema_id"] == c.schema
    app = a["applicability"]
    assert set(app) == {"y_min", "y_max", "n_features", "wavelength_axis_sha256",
                        "recipe_version_id", "target_schema_id", "task"}
    cal = c.models.get(a["id"], calibration=True)["calibration"]
    assert len(cal["source_hashes"]) == 12 and all(len(row["data"]) == len(row["header"]) == 64 for row in cal["source_hashes"])
    assert "可审计不可反证" in cal["limitation"]
    assert cal["steps"][0]["meta"]["fitted"]
    raw = build_sample_training_set(c.registry, c.paths, **{key:c.arguments[key] for key in ("preprocess_run_ids", "target_schema_id")})
    pred = c.training.artifact(c.result["run_id"], "predictions")
    ys = [row["y_true"] for row in pred if row["set"] == "calibration"]
    residual = np.array([row["residual"] for row in pred if row["set"] == "calibration"])
    assert (app["y_min"], app["y_max"]) == (min(ys), max(ys))
    assert cal["residual_interval"]["low"] == pytest.approx(residual.mean()-residual.std(ddof=1))
    assert cal["residual_interval"]["high"] == pytest.approx(residual.mean()+residual.std(ddof=1))
    np.testing.assert_allclose(apply_with_calibration(cal, cal["pipeline"], raw["X_raw"]), raw["X"])
    triples = [(cube, version, app["recipe_version_id"]) for cube,version in zip(c.cubes,c.versions)]
    assert data_fingerprint(triples[::-1]) == a["data_fingerprint"]
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT sql FROM sqlite_master WHERE name='model_artifact'").fetchone()[0] == old_sql
        assert db.execute("SELECT count(*) FROM model_artifact").fetchone()[0] == 3
    assert "calibration" not in a


def test_concurrent_version_and_production_switches(regression_factory):
    c = trained(regression_factory)
    with ThreadPoolExecutor(3) as pool:
        rows = list(pool.map(lambda _: c.models.register(c.result["run_id"], "parallel"), range(3)))
    assert sorted(row["version"] for row in rows) == [1, 2, 3]
    c.models.set_stage(rows[0]["id"], "production")
    c.models.set_stage(rows[1]["id"], "production")
    assert c.models.get(rows[0]["id"])["stage"] == "candidate"
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(lambda row: c.models.set_stage(row["id"], "production"), rows))
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM model_registry WHERE stage='production'").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE model_registry SET stage='production'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE model_registry SET stage='invalid'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE model_registry SET version=1 WHERE name='parallel'")
    c.models.set_stage(rows[0]["id"], "experiment")
    with fails("INVALID_MODEL_STAGE"):
        c.models.set_stage(rows[0]["id"], "bad")


def test_classification_and_unready_runs_rejected_before_io(legacy_case, insert_run):
    from spectrumagent.modeling.migrations import migrate
    c = legacy_case
    with connect_database(c.paths.database) as db:
        migrate(db); insert_run(db, status="succeeded")
    models = ModelRegistry(c.registry,c.paths)
    with fails("UNSUPPORTED_TASK"):
        models.register("training")
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE training_run SET task='regression',split_strategy='ks',status='pending'")
    with fails("RUN_NOT_READY"):
        models.register("training")
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM model_registry").fetchone()[0] == 0


def test_unreadable_training_explicit_chained_error_zero_writes(regression_factory, monkeypatch):
    c = trained(regression_factory)
    before = sorted(str(path.relative_to(c.paths.root)) for path in c.paths.root.rglob("*"))
    original = ModelingError("SOURCE_CHANGED", "private-source-path")
    def unavailable(*args, **kwargs):
        raise original
    monkeypatch.setattr("spectrumagent.modeling.registry.build_sample_training_set", unavailable)
    with pytest.raises(ModelingError) as caught:
        c.models.register(c.result["run_id"])
    assert caught.value.code == "TRAINING_DATA_UNAVAILABLE"
    assert "请在数据仍可访问时注册" in str(caught.value)
    assert caught.value.__cause__ is original
    with connect_database(c.paths.database) as db:
        assert db.execute("SELECT count(*) FROM model_registry").fetchone()[0] == 0
    assert sorted(str(path.relative_to(c.paths.root)) for path in c.paths.root.rglob("*")) == before
    print("C14 registry=0; filesystem unchanged; original cause retained")


@pytest.mark.parametrize("op,params", [
    ("standardize", {"method":"standard"}), ("standardize", {"method":"minmax"}),
    ("pca", {"n_components":3}), ("mnf", {"n_components":3}), ("ica", {"n_components":3}),
])
def test_all_fitted_calibrations_saved_and_block_invariant(op, params, monkeypatch):
    rng = np.random.default_rng(134)
    train = rng.normal(size=(68,8)); pixels = rng.normal(size=(257,8))
    pipeline = normalized_pipeline({"steps":[{"op":op,"version":1,"params":params}]})
    fit = builtin_registry().run(train,pipeline)
    cal = {"protocol":1,"pipeline":pipeline,"steps":fit.steps,"input_n_features":8}
    if op == "standardize":
        assert fit.steps[0]["meta"]["fitted"]
    else:
        assert fit.steps[0]["meta"]["mean"] and fit.steps[0]["meta"]["loadings"]
    # No fitted entry may be called during replay.
    def no_fit(*args, **kwargs):
        raise AssertionError("inference attempted to fit")
    registry = builtin_registry()
    from dataclasses import replace
    registry.entries[op][1] = replace(registry.resolve(op,1), impl=no_fit)
    monkeypatch.setattr("spectrumagent.modeling.inference.builtin_registry", lambda:registry)
    whole = apply_with_calibration(cal,pipeline,pixels)
    for size in (8,32):
        parts = np.concatenate([apply_with_calibration(cal,pipeline,pixels[i:i+size]) for i in range(0,len(pixels),size)])
        assert np.array_equal(whole,parts)
    np.testing.assert_allclose(apply_with_calibration(cal,pipeline,train),fit.spectra,atol=1e-12)
    broken = deepcopy(cal); broken["steps"][0]["version"] = 99
    with fails("CALIBRATION_MISMATCH"):
        apply_with_calibration(broken,pipeline,pixels)
    broken = deepcopy(cal); broken["steps"][0]["meta"] = {}
    with fails("CALIBRATION_MISMATCH"):
        apply_with_calibration(broken,pipeline,pixels)
    print(f"C13 {op}/{params}: whole == blocks8 == blocks32; no refit")


@pytest.mark.parametrize("op",["pca","mnf","ica"])
def test_reduced_registration_calibration_persisted(regression_factory,op):
    c = trained(regression_factory,{"steps":[{"op":op,"version":1,"params":{"n_components":3}}]})
    row = c.models.register(c.result["run_id"])
    cal = c.models.get(row["id"],calibration=True)["calibration"]
    assert row["applicability"]["n_features"] == 3 and cal["input_n_features"] == 8
    assert cal["steps"][0]["meta"]["mean"] and cal["steps"][0]["meta"]["loadings"]


@pytest.mark.parametrize("op,params",[
    ("snv",{}),("msc",{"reference":[.2,.6,.3,.9,.4,.8,.5,.7]}),
    ("emsc",{"reference":[.2,.6,.3,.9,.4,.8,.5,.7],"polynomial_order":2}),
    ("standardize",{"method":"area"}),("standardize",{"method":"vector"}),
    ("sg_smooth",{"window":3,"polyorder":1}),
    ("sg_derivative",{"window":3,"polyorder":1,"order":1}),
    ("crop",{"source":[1.,2.,3.,4.,5.,6.,7.,8.],"range":[2.,7.]}),
    ("resample",{"source":[1.,2.,3.,4.,5.,6.,7.,8.],"target":[1.,3.,5.,7.],"method":"linear"}),
    ("continuum",{"method":"convex_hull"}),
    ("reflectance",{"hdr":{"data_type":5},"branch":"passthrough"}),
])
def test_row_operators_json_roundtrip_and_block_replay(op,params):
    x=np.random.default_rng(134).uniform(.1,.9,(65,8))
    pipeline=normalized_pipeline({"steps":[{"op":op,"version":1,"params":params}]})
    fit=builtin_registry().run(x,pipeline)
    # Exercise actual JSON persistence, especially CropParams.range tuples.
    cal=json.loads(json.dumps({"protocol":1,"pipeline":pipeline,"steps":fit.steps,"input_n_features":8}))
    whole=apply_with_calibration(cal,pipeline,x)
    np.testing.assert_allclose(whole,fit.spectra,rtol=1e-12,atol=1e-12)
    assert np.array_equal(whole,np.concatenate([apply_with_calibration(cal,pipeline,x[i:i+8]) for i in range(0,65,8)]))
