"""Add training snapshots without altering the legacy dataset-version schema."""

TABLES = (
    """CREATE TABLE IF NOT EXISTS training_set_version (
        id TEXT PRIMARY KEY NOT NULL, content_hash TEXT NOT NULL,
        created_at TEXT NOT NULL, actor TEXT NOT NULL,
        is_frozen INTEGER NOT NULL CHECK(is_frozen IN (0,1)),
        member_count INTEGER NOT NULL CHECK(member_count > 0),
        label_summary TEXT NOT NULL, source_note TEXT, confirmed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS training_set_member (
        version_id TEXT NOT NULL REFERENCES training_set_version(id), cube_id TEXT NOT NULL,
        label_id TEXT, annotation_version_id TEXT NOT NULL, recipe_version_id TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL, n_pixels INTEGER NOT NULL CHECK(n_pixels > 0),
        PRIMARY KEY(version_id,cube_id)
    )""",
)


def migrate(db):
    db.execute('SAVEPOINT training_set_init')
    try:
        for statement in TABLES:
            db.execute(statement)
        # Deliberately non-unique: callers may request an independent index.
        db.execute('CREATE INDEX IF NOT EXISTS training_set_content_hash ON training_set_version(content_hash)')
        for operation in ('UPDATE', 'DELETE'):
            guard = 'OLD.is_frozen=1'
            if operation == 'UPDATE':
                guard += ' OR EXISTS(SELECT 1 FROM training_set_version WHERE id=NEW.id AND is_frozen=1)'
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS training_set_frozen_{operation.lower()}
                BEFORE {operation} ON training_set_version WHEN {guard}
                BEGIN SELECT RAISE(ABORT,'TRAINING_SET_IMMUTABLE'); END""")
            db.execute(f"""CREATE TRIGGER IF NOT EXISTS training_set_member_frozen_{operation.lower()}
                BEFORE {operation} ON training_set_member
                WHEN EXISTS(SELECT 1 FROM training_set_version WHERE id=OLD.version_id AND is_frozen=1)
                BEGIN SELECT RAISE(ABORT,'TRAINING_SET_IMMUTABLE'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS training_set_frozen_replace
            BEFORE INSERT ON training_set_version
            WHEN EXISTS(SELECT 1 FROM training_set_version WHERE id=NEW.id AND is_frozen=1)
            BEGIN SELECT RAISE(ABORT,'TRAINING_SET_IMMUTABLE'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS training_set_member_frozen_insert
            BEFORE INSERT ON training_set_member
            WHEN EXISTS(SELECT 1 FROM training_set_version WHERE id=NEW.version_id AND is_frozen=1)
            BEGIN SELECT RAISE(ABORT,'TRAINING_SET_IMMUTABLE'); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS training_set_member_frozen_move
            BEFORE UPDATE OF version_id ON training_set_member
            WHEN EXISTS(SELECT 1 FROM training_set_version WHERE id=NEW.version_id AND is_frozen=1)
            BEGIN SELECT RAISE(ABORT,'TRAINING_SET_IMMUTABLE'); END""")
        db.execute('RELEASE training_set_init')
    except BaseException:
        db.execute('ROLLBACK TO training_set_init')
        db.execute('RELEASE training_set_init')
        raise
