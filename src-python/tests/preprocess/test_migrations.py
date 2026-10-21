"""TASK-05 §3 five-table schema: compare to independently executed task-card DDL."""
from pathlib import Path
import sqlite3

import pytest

from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.preprocess.migrations import BUILTIN_CODE, DDL, migrate
from spectrumagent.preprocess.recipes import RecipeStore


TABLES = ["preprocess_recipe","preprocess_recipe_version","project_recipe","preprocess_run","preprocess_artifact"]
ROOT = Path(__file__).resolve().parents[3]


def snapshot(db):
    return {table:{"table_info":db.execute(f"PRAGMA table_info({table})").fetchall(),
                   "foreign_key_list":db.execute(f"PRAGMA foreign_key_list({table})").fetchall()}
            for table in TABLES}


def test_ddl_verbatim_and_all_table_columns_types_notnull_defaults_foreign_keys(tmp_path):
    card = (ROOT/"TASK-05-预处理.md").read_text("utf-8").split("```sql\n",1)[1].split("\n```",1)[0]
    assert DDL.strip() == card.strip()
    database = tmp_path/"ledger.sqlite3"
    DatasetRegistry(database)
    RecipeStore(database)
    with sqlite3.connect(":memory:") as expected:
        expected.executescript(card)
        with connect_database(database) as actual:
            assert snapshot(actual) == snapshot(expected)
            assert actual.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_twice_same_connection_schema_and_seed_rows_identical(tmp_path):
    database = tmp_path/"ledger.sqlite3"
    DatasetRegistry(database)
    with connect_database(database) as db:
        migrate(db)
        first = snapshot(db)
        rows = {table:db.execute(f"SELECT * FROM {table}").fetchall() for table in TABLES}
        migrate(db)
        assert snapshot(db) == first
        assert {table:db.execute(f"SELECT * FROM {table}").fetchall() for table in TABLES} == rows
        assert db.execute("SELECT count(*) FROM preprocess_recipe WHERE code=?",(BUILTIN_CODE,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM preprocess_recipe_version").fetchone()[0] == 1
    assert RecipeStore(database).list() == RecipeStore(database).list()


def test_annotation_fk_notnull_and_other_table_references_enforced(tmp_path):
    database = tmp_path/"ledger.sqlite3"
    DatasetRegistry(database)
    store = RecipeStore(database)
    version_id = store.list()[0]["versions"][0]["id"]
    with connect_database(database) as db:
        sql = "INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,created_at) VALUES (?,?,?,?,?,?,?,?)"
        base = ["run","cube","unknown-annotation",version_id,"scale","digest","pending","fixture"]
        with pytest.raises(sqlite3.IntegrityError,match="FOREIGN KEY"):
            db.execute(sql,base)
        base[2] = None
        with pytest.raises(sqlite3.IntegrityError,match="NOT NULL"):
            db.execute(sql,base)
        db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) "
                   "VALUES ('ann','cube',1,'cube/v1',6,6,'{}','fixture')")
        base[2] = "ann"
        db.execute(sql,base)
        with pytest.raises(sqlite3.IntegrityError,match="FOREIGN KEY"):
            db.execute("INSERT INTO preprocess_artifact (id,run_id,kind,relative_path,sha256,created_at) VALUES ('artifact','missing','report','a','digest','fixture')")
        with pytest.raises(sqlite3.IntegrityError,match="FOREIGN KEY"):
            db.execute("INSERT INTO project_recipe VALUES ('missing',?,'fixture')",(store.list()[0]["id"],))


def test_preprocess_migration_requires_prior_annotation_migration():
    with sqlite3.connect(":memory:") as db:
        with pytest.raises(RuntimeError,match="TASK-04"):
            migrate(db)
        assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'preprocess_%'").fetchall()
