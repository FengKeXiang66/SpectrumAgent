"""Independent batch-index schema; existing cube and training schemas stay intact."""

TABLES = (
    """CREATE TABLE IF NOT EXISTS dataset_version (
        id TEXT PRIMARY KEY NOT NULL, content_hash TEXT NOT NULL,
        created_at TEXT NOT NULL, actor TEXT NOT NULL, is_frozen INTEGER NOT NULL CHECK(is_frozen IN (0,1)),
        cube_count INTEGER NOT NULL CHECK(cube_count > 0), source_root TEXT NOT NULL,
        acq_meta TEXT NOT NULL, confirmed_at TEXT, note TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS dataset_version_item (
        version_id TEXT NOT NULL REFERENCES dataset_version(id), cube_id TEXT NOT NULL,
        content_hash TEXT NOT NULL, acq_meta TEXT NOT NULL,
        PRIMARY KEY(version_id,cube_id)
    )""",
)


def migrate(db):
    db.execute('SAVEPOINT dataset_version_init')
    try:
        for statement in TABLES:
            db.execute(statement)
        columns = {row[1] for row in db.execute('PRAGMA table_info(dataset_version_item)')}
        for column in ('annotation_version_id', 'recipe_version_id', 'preprocess_run_id', 'input_fingerprint'):
            if column in columns:
                db.execute(f'ALTER TABLE dataset_version_item DROP COLUMN {column}')
        # A non-unique index supports both deduplication and explicit independent copies.
        db.execute('CREATE INDEX IF NOT EXISTS dataset_version_content_hash ON dataset_version(content_hash)')
        for operation in ('UPDATE', 'DELETE'):
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS dataset_version_frozen_{operation.lower()}
                BEFORE {operation} ON dataset_version WHEN OLD.is_frozen=1
                BEGIN SELECT RAISE(ABORT,'DATASET_VERSION_IMMUTABLE'); END""")
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS dataset_version_item_frozen_{operation.lower()}
                BEFORE {operation} ON dataset_version_item
                WHEN EXISTS(SELECT 1 FROM dataset_version WHERE id=OLD.version_id AND is_frozen=1)
                BEGIN SELECT RAISE(ABORT,'DATASET_VERSION_IMMUTABLE'); END""")
        # INSERT OR REPLACE must not bypass the frozen parent or append a new item.
        db.execute("""CREATE TRIGGER IF NOT EXISTS dataset_version_frozen_replace
            BEFORE INSERT ON dataset_version
            WHEN EXISTS(SELECT 1 FROM dataset_version WHERE id=NEW.id AND is_frozen=1)
            BEGIN SELECT RAISE(ABORT,'DATASET_VERSION_IMMUTABLE'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS dataset_version_item_frozen_insert
            BEFORE INSERT ON dataset_version_item
            WHEN EXISTS(SELECT 1 FROM dataset_version WHERE id=NEW.version_id AND is_frozen=1)
            BEGIN SELECT RAISE(ABORT,'DATASET_VERSION_IMMUTABLE'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS dataset_version_item_frozen_move
            BEFORE UPDATE OF version_id ON dataset_version_item
            WHEN EXISTS(SELECT 1 FROM dataset_version WHERE id=NEW.version_id AND is_frozen=1)
            BEGIN SELECT RAISE(ABORT,'DATASET_VERSION_IMMUTABLE'); END""")
        db.execute('RELEASE dataset_version_init')
    except BaseException:
        db.execute('ROLLBACK TO dataset_version_init')
        db.execute('RELEASE dataset_version_init')
        raise
