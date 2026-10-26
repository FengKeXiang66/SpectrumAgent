"""Additive training ledger; existing annotation/preprocess schemas stay intact."""
DDL = """
CREATE TABLE IF NOT EXISTS training_run (
 id TEXT PRIMARY KEY, cube_ids TEXT NOT NULL, annotation_version_ids TEXT NOT NULL,
 preprocess_run_ids TEXT NOT NULL, task TEXT NOT NULL CHECK(task IN ('regression','classification')),
 target TEXT NOT NULL, cv_strategy TEXT NOT NULL CHECK(cv_strategy IN ('group_kfold','random')),
 cv_folds INTEGER NOT NULL, seed INTEGER NOT NULL, model_family TEXT, model_params TEXT,
 status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),
 leak_report TEXT, error TEXT, started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_fold (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id), fold_index INTEGER NOT NULL,
 train_count INTEGER NOT NULL, test_count INTEGER NOT NULL,
 train_groups TEXT NOT NULL, test_groups TEXT NOT NULL, UNIQUE(run_id,fold_index)
);
CREATE TABLE IF NOT EXISTS metric (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id), fold_index INTEGER,
 scope TEXT NOT NULL CHECK(scope IN ('pixel','sample')),
 name TEXT NOT NULL CHECK(name IN ('oa','kappa','rmse','r2','rmsep')),
 value REAL, created_at TEXT NOT NULL, UNIQUE(run_id,fold_index,scope,name)
);
CREATE TABLE IF NOT EXISTS model_artifact (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id),
 kind TEXT NOT NULL CHECK(kind IN ('model','confusion','predictions')),
 relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,kind)
);
"""


def migrate(db):
    for statement in DDL.split(";"):
        if statement.strip():
            db.execute(statement)
