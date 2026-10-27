"""Training ledger; 13.2 upgrades preserve historical classification rows and FKs."""
DDL = """
CREATE TABLE IF NOT EXISTS training_run (
 id TEXT PRIMARY KEY, cube_ids TEXT NOT NULL, annotation_version_ids TEXT NOT NULL,
 preprocess_run_ids TEXT NOT NULL, task TEXT NOT NULL CHECK(task IN ('regression','classification')),
 target TEXT NOT NULL, cv_strategy TEXT NOT NULL CHECK(cv_strategy IN ('group_kfold','random','kfold','loo')),
 cv_folds INTEGER NOT NULL, seed INTEGER NOT NULL, model_family TEXT, model_params TEXT,
 status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),
 leak_report TEXT, error TEXT, started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL,
 split_strategy TEXT NOT NULL DEFAULT 'none' CHECK(split_strategy IN ('none','ks','spxy','random','stratified')),
 target_schema_id TEXT REFERENCES label_schema(id),
 CHECK((task='classification' AND split_strategy='none') OR
       (task='regression' AND split_strategy IN ('ks','spxy','random','stratified')))
);
CREATE TABLE IF NOT EXISTS training_fold (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id), fold_index INTEGER NOT NULL,
 train_count INTEGER NOT NULL, test_count INTEGER NOT NULL,
 train_groups TEXT NOT NULL, test_groups TEXT NOT NULL, UNIQUE(run_id,fold_index)
);
CREATE TABLE IF NOT EXISTS metric (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id), fold_index INTEGER,
 scope TEXT NOT NULL CHECK(scope IN ('pixel','sample')),
 name TEXT NOT NULL CHECK(name IN ('oa','kappa','rmse','r2','rmsep','r2p','rpd','rer','bias')),
 value REAL, created_at TEXT NOT NULL, UNIQUE(run_id,fold_index,scope,name)
);
CREATE TABLE IF NOT EXISTS model_artifact (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id),
 kind TEXT NOT NULL CHECK(kind IN ('model','confusion','predictions','lv_sweep')),
 relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,kind)
);
CREATE TABLE IF NOT EXISTS sample_target (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
 cube_id TEXT NOT NULL REFERENCES dataset_registry(id),
 schema_id TEXT NOT NULL REFERENCES label_schema(id), value REAL NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('import','annotation')), created_at TEXT NOT NULL,
 UNIQUE(cube_id,schema_id)
);
CREATE TABLE IF NOT EXISTS model_registry (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id),
 name TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0),
 target_schema_id TEXT NOT NULL REFERENCES label_schema(id),
 data_fingerprint TEXT NOT NULL, applicability TEXT NOT NULL, calibration TEXT NOT NULL,
 stage TEXT NOT NULL DEFAULT 'experiment' CHECK(stage IN ('experiment','candidate','production')),
 created_at TEXT NOT NULL, UNIQUE(name,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS model_registry_one_production
 ON model_registry(target_schema_id) WHERE stage='production';
CREATE TABLE IF NOT EXISTS inference_run (
 id TEXT PRIMARY KEY, model_id TEXT NOT NULL REFERENCES model_registry(id),
 cube_id TEXT NOT NULL REFERENCES dataset_registry(id),
 preprocess_run_id TEXT NOT NULL REFERENCES preprocess_run(id),
 annotation_version_id TEXT NOT NULL REFERENCES annotation_version(id),
 status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),
 stats TEXT, error TEXT, created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS inference_artifact (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES inference_run(id),
 kind TEXT NOT NULL CHECK(kind IN ('prediction','state','applicability','map')),
 relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(run_id,kind)
);
"""


def migrate(db):
    columns = {row[1] for row in db.execute("PRAGMA table_info(training_run)")}
    upgrade = bool(columns) and "target_schema_id" not in columns
    deferred = db.execute("PRAGMA defer_foreign_keys").fetchone()[0]
    db.execute("SAVEPOINT modeling_132")
    try:
        if upgrade:
            # Create-copy-drop-rename is essential for the parent: renaming the
            # old parent would rewrite training_fold's FK. That table is never
            # altered, renamed or copied. foreign_keys stays ON throughout.
            names = ("training_run", "metric", "model_artifact")
            for name in names:
                statement = next(s for s in DDL.split(";") if f"CREATE TABLE IF NOT EXISTS {name} (" in s)
                db.execute(statement.replace(f"{name} (", f"{name}_132 (", 1))
                old_columns = [row[1] for row in db.execute(f"PRAGMA table_info({name})")]
                fields = ",".join(old_columns)
                db.execute(f"INSERT INTO {name}_132 ({fields}) SELECT {fields} FROM {name}")
            db.execute("PRAGMA defer_foreign_keys=ON")
            for name in ("metric", "model_artifact", "training_run"):
                db.execute(f"DROP TABLE {name}")
            for name in names:
                db.execute(f"ALTER TABLE {name}_132 RENAME TO {name}")
        for statement in DDL.split(";"):
            if statement.strip():
                db.execute(statement)
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Modeling migration foreign-key audit failed")
        # SQLite retains a deferred DROP counter even after the parent exists
        # again. Clear it only AFTER auditing every actual FK, then restore the
        # caller's deferral setting. Never disable foreign_keys or skip audit.
        db.execute("PRAGMA defer_foreign_keys=OFF")
        if deferred:
            db.execute("PRAGMA defer_foreign_keys=ON")
        db.execute("RELEASE modeling_132")
    except BaseException:
        db.execute("ROLLBACK TO modeling_132")
        db.execute("RELEASE modeling_132")
        db.execute(f"PRAGMA defer_foreign_keys={int(deferred)}")
        raise
