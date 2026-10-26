import sqlite3
import pytest

from backend.database import connect_database
from spectrumagent.modeling.migrations import migrate

LEGACY_DDL = "\nCREATE TABLE IF NOT EXISTS training_run (\n id TEXT PRIMARY KEY, cube_ids TEXT NOT NULL, annotation_version_ids TEXT NOT NULL,\n preprocess_run_ids TEXT NOT NULL, task TEXT NOT NULL CHECK(task IN ('regression','classification')),\n target TEXT NOT NULL, cv_strategy TEXT NOT NULL CHECK(cv_strategy IN ('group_kfold','random')),\n cv_folds INTEGER NOT NULL, seed INTEGER NOT NULL, model_family TEXT, model_params TEXT,\n status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),\n leak_report TEXT, error TEXT, started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL\n);\nCREATE TABLE IF NOT EXISTS training_fold (\n id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id), fold_index INTEGER NOT NULL,\n train_count INTEGER NOT NULL, test_count INTEGER NOT NULL,\n train_groups TEXT NOT NULL, test_groups TEXT NOT NULL, UNIQUE(run_id,fold_index)\n);\nCREATE TABLE IF NOT EXISTS metric (\n id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id), fold_index INTEGER,\n scope TEXT NOT NULL CHECK(scope IN ('pixel','sample')),\n name TEXT NOT NULL CHECK(name IN ('oa','kappa','rmse','r2','rmsep')),\n value REAL, created_at TEXT NOT NULL, UNIQUE(run_id,fold_index,scope,name)\n);\nCREATE TABLE IF NOT EXISTS model_artifact (\n id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id),\n kind TEXT NOT NULL CHECK(kind IN ('model','confusion','predictions')),\n relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,kind)\n);\n"


def test_132_upgrade_preserves_three_rows_per_table_and_foreign_keys(legacy_case):
    with connect_database(legacy_case.paths.database) as db:
        for statement in LEGACY_DDL.split(";"):
            if statement.strip():
                db.execute(statement)
        for i in range(3):
            db.execute("INSERT INTO training_run VALUES (?, '[]','[]','[]','classification','label','group_kfold',2,17,NULL,NULL,'succeeded',NULL,NULL,NULL,NULL,'fixture')", (str(i),))
            db.execute("INSERT INTO training_fold VALUES (?,?,0,2,2,'[0]','[1]')", (str(i),str(i)))
            db.execute("INSERT INTO metric VALUES (?,?,NULL,'pixel','oa',0.5,'fixture')", (str(i),str(i)))
            db.execute("INSERT INTO model_artifact VALUES (?,?,'model','legacy.json','hash','fixture')", (str(i),str(i)))
        tables = ("training_run", "training_fold", "metric", "model_artifact")
        before = {table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in tables}
        fold_schema = db.execute("SELECT sql FROM sqlite_master WHERE name='training_fold'").fetchone()[0]
        original_columns = {table: db.execute(f'PRAGMA table_info({table})').fetchall() for table in tables}
        original_sql = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        migrate(db)
        migrate(db)
        for table in tables:
            after = db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
            assert len(after) == len(before[table]) == 3
            assert [row[:len(before[table][0])] for row in after] == before[table]
        assert db.execute("SELECT DISTINCT split_strategy,target_schema_id FROM training_run").fetchall() == [("none",None)]
        assert db.execute("SELECT sql FROM sqlite_master WHERE name='training_fold'").fetchone()[0] == fold_schema
        for table in tables:
            current = db.execute(f'PRAGMA table_info({table})').fetchall()
            assert current[:len(original_columns[table])] == original_columns[table]
        current_sql = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        for name,sql in original_sql.items():
            if name not in ('training_run','metric','model_artifact'):
                assert current_sql[name] == sql
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("training_fold", "metric", "model_artifact"):
            assert db.execute(f"PRAGMA foreign_key_list({table})").fetchone()[2] == "training_run"
        for name in ("r2p", "rpd", "rer", "bias"):
            db.execute("INSERT INTO metric VALUES (?, '0', NULL, 'sample', ?, NULL, 'fixture')", (name,name))
        db.execute("INSERT INTO model_artifact VALUES ('sweep','0','lv_sweep','sweep.json','hash','fixture')")
        for strategy in ("kfold","loo"):
            db.execute("UPDATE training_run SET cv_strategy=? WHERE id='0'",(strategy,))
        assert db.execute("SELECT count(*) FROM sample_target").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE training_run SET task='regression' WHERE id='0'")
        db.execute("UPDATE training_run SET task='regression',split_strategy='ks' WHERE id='0'")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE training_run SET task='classification' WHERE id='0'")
        db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,cv_folds,seed,status,created_at) VALUES ('default','[]','[]','[]','classification','label','random',2,17,'pending','fixture')")
        assert db.execute("SELECT split_strategy FROM training_run WHERE id='default'").fetchone()[0]=='none'
        db.commit()
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        print("MIGRATION_132 rows=3/3/3/3 preserved; FK check=[]; commit=pass; repeat=pass; training_fold untouched; A14b=pass")
