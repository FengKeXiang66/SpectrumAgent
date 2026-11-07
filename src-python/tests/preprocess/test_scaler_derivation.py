"""TASK-33: derive the stored snapshot independently from a real successful report."""
import json

import pytest

from backend.database import connect_database
from .run_fixtures import run_case, step


@pytest.mark.parametrize("steps,branch", [
    ([step("standardize", method="standard")], "single"),
    ([step("standardize", method="standard"), step("standardize", method="minmax")], "multiple"),
    ([], "none"),
    ([step("standardize", method="area")], "empty-fitted"),
    ([step("standardize", method="vector")], "empty-fitted"),
], ids=["single", "multiple", "none", "area", "vector"])
def test_scaler_snapshot_is_derived_from_real_report_bytes(run_case, steps, branch):
    c = run_case
    run = c.runner.run(c.cube, c.version, c.recipe(steps))
    assert run["status"] == "succeeded", run["error"]
    report = c.report(run)
    assert [record["op"] for record in report["steps"]] == [record["op"] for record in steps]
    records = [record["meta"]["fitted"] for record in report["steps"] if record["op"] == "standardize"]
    value = records[0] if len(records) == 1 else (records if records else None)
    expected = None if value is None else json.dumps(value, allow_nan=False)
    with connect_database(c.paths.database) as db:
        stored = db.execute("SELECT scaler_params FROM preprocess_run WHERE id=?", (run["id"],)).fetchone()[0]
    assert stored == expected
    assert run["scaler_params"] == value
    if expected is not None:
        assert stored.encode("utf-8") == expected.encode("utf-8")
    if branch == "single":
        assert len(value) == c.values.shape[2] and set(value[0]) == {"mean", "std"}
    elif branch == "multiple":
        assert len(value) == 2 and all(len(fitted) == c.values.shape[2] for fitted in value)
    elif branch == "none":
        assert stored is None and value is None
    else:
        assert records == [[]] and stored == "[]" and value == []
