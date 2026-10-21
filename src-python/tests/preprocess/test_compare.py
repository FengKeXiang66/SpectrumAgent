import sqlite3

import numpy as np
import pytest

from spectrumagent.data import DataError
from spectrumagent.preprocess.compare import CompareEngine, PixelMetrics
from .run_fixtures import run_case, step


def test_metrics_pixel_snr_quantiles_pooled_pairwise_fisher_and_three_boundaries():
    x = np.array([[1., 2., 4.], [2., 4., 5.], [5., 8., 9.], [7., 9., 11.]])
    labels = np.array([0, 0, 1, 1])
    metrics = PixelMetrics()
    metrics.update(x[:2], labels[:2])
    metrics.update(x[2:], labels[2:])
    result, _ = metrics.result(labeled=True)
    expected = x.mean(axis=1)/np.sqrt(np.mean(np.diff(x, axis=1)**2, axis=1))
    for key, value in (("mean", expected.mean()), ("median", np.median(expected)),
                       ("p10", np.percentile(expected, 10)), ("p90", np.percentile(expected, 90))):
        assert result["snr"][key] == pytest.approx(value)
    between = np.linalg.norm(x[:2].mean(axis=0)-x[2:].mean(axis=0))
    within = (x[:2].var(axis=0).sum()+x[2:].var(axis=0).sum())/2
    assert result["interclass_distance"] == pytest.approx(between)
    assert result["intraclass_variance"] == pytest.approx(within)
    assert result["fisher"] == pytest.approx(between/within)
    assert len(result["boundaries"]) == 3


def test_zero_variance_nan_and_unlabeled_explicit_limits():
    metrics = PixelMetrics()
    metrics.update(np.array([[1., 1., 1.], [2., 2., 2.], [np.nan, 3., 4.]]), np.array([0, 1, 2]))
    result, _ = metrics.result(labeled=True)
    assert result["snr_nan_count"] == 2 and result["nan_spectra_skipped"] == 1
    assert len(result["excluded_classes"]) == 2 and result["fisher"] is None
    assert result["snr"]["mean"] is None
    result, _ = metrics.result(labeled=False)
    assert "fisher" not in result and "interclass_distance" not in result and result["limitations"]


def test_compare_reuses_run_and_sql_authorizer_explodes_aggregate_reads(run_case, monkeypatch):
    c = run_case
    first = c.recipe([])
    second = c.recipe([step("snv")])
    import backend.database as module
    from backend.database import connect_database
    original = module.open_database
    denied = []
    def guarded(*args, **kwargs):
        db = original(*args, **kwargs)
        def authorizer(action, table, *_):
            if action == sqlite3.SQLITE_READ and table == "sample_spectrum":
                denied.append(table)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        db.set_authorizer(authorizer)
        return db
    # All connect_database aliases resolve this opener, including registry/helpers.
    monkeypatch.setattr(module, "open_database", guarded)
    with connect_database(c.paths.database) as db:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("SELECT * FROM " + "sample_" + "spectrum")
    denied.clear()
    calls, execute = [], c.runner.run
    def run(*args, **kwargs):
        calls.append(args[2])
        return execute(*args, **kwargs)
    monkeypatch.setattr(c.runner, "run", run)
    result = CompareEngine(c.runner).compare(c.cube, c.version, [first, second])
    assert calls == [first, second] and denied == []
    assert all(row["status"] == "succeeded" for row in result["runs"])
    assert len(result["ranking"]) == 2
    assert result["ranking"][0]["fisher"] >= result["ranking"][1]["fisher"]
    assert len(result["boundaries"]) == 3


def test_compare_requires_explicit_nonempty_versions(run_case):
    with pytest.raises(DataError) as caught:
        CompareEngine(run_case.runner).compare(run_case.cube, run_case.version, [])
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"


def test_unlabeled_real_run_only_snr_no_sample_spectrum(run_case):
    c = run_case
    c.label_map[:] = -1
    np.savez_compressed(c.paths.snapshots/c.cube/"v1"/"label_map.npz", label_map=c.label_map)
    row = c.runner.run(c.cube, c.version, c.recipe([]))
    assert row["status"] == "succeeded" and row["metrics"]["limitations"]
    assert "fisher" not in row["metrics"] and c.spectra(row) == {}
