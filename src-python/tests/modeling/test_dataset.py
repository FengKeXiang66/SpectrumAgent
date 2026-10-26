import sqlite3

import pytest

from backend.database import connect_database
from spectrumagent.modeling.migrations import migrate
from conftest import insert_run


def test_migration_upgrades_21_tables_repeats_without_changing_existing_schema(legacy_case):
    with connect_database(legacy_case.paths.database) as db:
        before = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert len(before) == 21
        migrate(db)
        migrate(db)
        after = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        assert set(after) - set(before) == {"training_run", "training_fold", "metric", "model_artifact"}
        assert all(after[name] == sql for name, sql in before.items())


@pytest.mark.parametrize("status", ["pending", "running", "succeeded", "failed", "cancelled"])
def test_training_status_four_states_only(legacy_case, status):
    with connect_database(legacy_case.paths.database) as db:
        migrate(db)
        if status == "cancelled":
            with pytest.raises(sqlite3.IntegrityError):
                insert_run(db, status=status)
        else:
            insert_run(db, status=status)
            assert db.execute("SELECT model_family,status FROM training_run").fetchone() == (None, status)


@pytest.mark.parametrize("table", ["training_fold", "metric"])
def test_fold_and_metric_uniqueness(legacy_case, table):
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
