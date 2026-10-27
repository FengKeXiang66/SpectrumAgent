import sqlite3
import tracemalloc

import numpy as np

import pytest

from backend.database import connect_database
from spectrumagent.modeling.migrations import migrate
from spectrumagent.modeling.dataset import build_training_set
from spectrumagent.data import DataError, SpectrumDataSet
from spectrumagent.data.readers.header import classic, read_text
from spectrumagent.preprocess import builtin_registry


def test_migration_upgrades_21_tables_repeats_without_changing_existing_schema(legacy_case):
    with connect_database(legacy_case.paths.database) as db:
        before = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert len(before) == 21
        migrate(db)
        migrate(db)
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert set(after) - set(before) == {"training_run", "training_fold", "metric", "model_artifact", "sample_target", "model_registry", "inference_run", "inference_artifact"}
        assert all(after[name] == sql for name, sql in before.items())


@pytest.mark.parametrize("status", ["pending", "running", "succeeded", "failed", "cancelled"])
def test_training_status_four_states_only(legacy_case, status, insert_run):
    with connect_database(legacy_case.paths.database) as db:
        migrate(db)
        if status == "cancelled":
            with pytest.raises(sqlite3.IntegrityError):
                insert_run(db, status=status)
        else:
            insert_run(db, status=status)
            assert db.execute("SELECT model_family,status FROM training_run").fetchone() == (None, status)


@pytest.mark.parametrize("table", ["training_fold", "metric"])
def test_fold_and_metric_uniqueness(legacy_case, table, insert_run):
    with connect_database(legacy_case.paths.database) as db:
        migrate(db)
        insert_run(db)
        if table == "training_fold":
            sql = "INSERT INTO training_fold VALUES (?,'training',0,3,3,'[0]','[1]')"
        else:
            sql = "INSERT INTO metric VALUES (?,'training',0,'pixel','oa',1,'fixture')"
        db.execute(sql, ("first",))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, ("second",))


def test_training_pixels_match_whole_cube_recipe_and_exclude_both_negative_states(model_case, monkeypatch):
    c = model_case
    monkeypatch.setattr(SpectrumDataSet, "to_numpy", lambda *_: pytest.fail("full materialization forbidden"))
    original = SpectrumDataSet.read_region
    reads = []
    def bounded(dataset, first, last, left, right):
        assert last - first <= 32
        reads.append(last-first)
        return original(dataset, first, last, left, right)
    monkeypatch.setattr(SpectrumDataSet, "read_region", bounded)
    result = build_training_set(c.registry, c.paths, **c.arguments)
    assert result["X"].shape == (96, 8) and result["X"].dtype == np.float64
    assert result["y"].dtype == np.int64 and result["groups"].dtype == np.int32
    for index in range(4):
        raw = c.values[index][c.maps[index] >= 0]
        expected = (raw-raw.mean(axis=0))/raw.std(axis=0)
        chosen = result["groups"] == index
        np.testing.assert_allclose(result["X"][chosen], expected, atol=1e-12)
        np.testing.assert_array_equal(result["y"][chosen], c.maps[index][c.maps[index] >= 0])
        assert chosen.sum() == 24
    assert reads and result["meta"]["n_samples"] == 96


def test_training_snapshot_shape_mismatch_is_explicit(model_case):
    c = model_case
    with connect_database(c.paths.database) as db:
        ref = db.execute("SELECT snapshot_ref FROM annotation_version WHERE id=?", (c.versions[0],)).fetchone()[0]
    np.savez_compressed(c.paths.snapshots/ref/"label_map.npz", label_map=np.zeros((1, 1), np.int32))
    with pytest.raises(DataError) as error:
        build_training_set(c.registry, c.paths, **c.arguments)
    assert error.value.code == "LABEL_MAP_SHAPE_MISMATCH"


def test_training_build_reports_tracemalloc_peak(model_case):
    c = model_case
    tracemalloc.start()
    try:
        result = build_training_set(c.registry, c.paths, **c.arguments)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak >= result["X"].nbytes and result["meta"]["n_samples"] == 96
    print(f"MODEL_BUILD_MEMORY samples=96 bands=8 peak_bytes={peak}")


def test_reader_reflectance_equals_raw_plus_b01_for_reachable_branches(reflectance_cube):
    c = reflectance_cube
    reflected, _ = c.registry.readable(c.cube, raw=False)
    raw, _ = c.registry.readable(c.cube, raw=True)
    hdr = classic(read_text(c.header))
    original = raw.read_region(0, 3, 0, 4)
    converted = builtin_registry().run(original.reshape(-1, 8), {"steps": [
        {"op": "reflectance", "version": 1, "params": {"hdr": hdr, "guard": "clip"}}
    ]})
    assert converted.steps[0]["meta"]["branch"] == c.branch
    assert np.array_equal(original, c.values.astype(np.float64))
    assert np.array_equal(reflected.read_region(0, 3, 0, 4), converted.spectra.reshape(3, 4, 8))
    assert reflected.shape[2] == converted.spectra.shape[1] == 8
    print(f"B01_EQUIVALENCE branch={c.branch} array_equal=True n_features=8")
