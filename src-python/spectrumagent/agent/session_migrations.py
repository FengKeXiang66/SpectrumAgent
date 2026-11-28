"""TASK-47 metadata only. Kept separate from TASK-07's pinned DDL."""
from backend.database import connect_database


DDL = """
CREATE TABLE IF NOT EXISTS dataset_intake (
 session_id TEXT PRIMARY KEY REFERENCES agent_session(id), document_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_external_annotation (
 cube_id TEXT PRIMARY KEY REFERENCES dataset_registry(id) ON DELETE CASCADE,
 source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL, header_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_canvas_focus (
 session_id TEXT PRIMARY KEY REFERENCES agent_session(id), cube_id TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_session_scope (
 session_id TEXT PRIMARY KEY REFERENCES agent_session(id),
 scope_kind TEXT NOT NULL CHECK(scope_kind IN ('global','dataset_version')),
 dataset_version_ref TEXT, version_content_hash TEXT,
 member_count INTEGER NOT NULL CHECK(member_count>=0),
 scope_schema_version INTEGER NOT NULL DEFAULT 1 CHECK(scope_schema_version=1),
 creation_key TEXT UNIQUE, creation_payload_hash TEXT, creation_audit_json TEXT NOT NULL DEFAULT '{}',
 CHECK((scope_kind='global' AND dataset_version_ref IS NULL AND version_content_hash IS NULL AND member_count=0)
 OR (scope_kind='dataset_version' AND dataset_version_ref IS NOT NULL AND length(version_content_hash)=64 AND member_count>0))
);
CREATE TABLE IF NOT EXISTS agent_session_member (
 session_id TEXT NOT NULL REFERENCES agent_session_scope(session_id),
 ordinal INTEGER NOT NULL CHECK(ordinal>0), cube_id TEXT NOT NULL, content_hash TEXT NOT NULL CHECK(length(content_hash)=64),
 PRIMARY KEY(session_id,cube_id), UNIQUE(session_id,ordinal)
);
CREATE TABLE IF NOT EXISTS agent_session_request (
 session_id TEXT NOT NULL REFERENCES agent_session(id), request_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, input_kind TEXT NOT NULL, boot_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','completed','failed','interrupted')),
 created_at TEXT NOT NULL, finished_at TEXT, events_complete INTEGER NOT NULL DEFAULT 0 CHECK(events_complete IN (0,1)),
 PRIMARY KEY(session_id,request_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS agent_session_one_running ON agent_session_request(session_id) WHERE status='running';
CREATE INDEX IF NOT EXISTS agent_session_list_order ON agent_session(created_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS agent_session_event (
 session_id TEXT NOT NULL REFERENCES agent_session(id), seq INTEGER NOT NULL CHECK(seq>0), request_id TEXT,
 kind TEXT NOT NULL CHECK(kind IN ('user','decision','step','plan','human_check','workspace','clarify','done','error')),
 payload_json TEXT NOT NULL, created_at TEXT NOT NULL, origin TEXT NOT NULL, source_key TEXT NOT NULL,
 PRIMARY KEY(session_id,seq), UNIQUE(session_id,source_key)
);
CREATE INDEX IF NOT EXISTS agent_session_event_request ON agent_session_event(session_id,request_id,seq);
CREATE TRIGGER IF NOT EXISTS agent_session_member_bound_insert BEFORE INSERT ON agent_session_member
 WHEN NOT EXISTS (SELECT 1 FROM agent_session_scope WHERE session_id=NEW.session_id AND scope_kind='dataset_version'
 AND NEW.ordinal<=member_count)
 OR NEW.ordinal<>(SELECT COALESCE(MAX(ordinal),0)+1 FROM agent_session_member WHERE session_id=NEW.session_id)
 BEGIN SELECT RAISE(ABORT,'SESSION_SNAPSHOT_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS agent_session_request_transition BEFORE UPDATE ON agent_session_request
 WHEN OLD.status<>'running' OR NEW.status NOT IN ('completed','failed','interrupted')
 OR NEW.session_id<>OLD.session_id OR NEW.request_id<>OLD.request_id OR NEW.payload_hash<>OLD.payload_hash
 OR NEW.input_kind<>OLD.input_kind OR NEW.boot_id<>OLD.boot_id OR NEW.created_at<>OLD.created_at
 BEGIN SELECT RAISE(ABORT,'SESSION_REQUEST_IMMUTABLE'); END;
CREATE TRIGGER IF NOT EXISTS agent_session_request_no_delete BEFORE DELETE ON agent_session_request
 BEGIN SELECT RAISE(ABORT,'SESSION_REQUEST_IMMUTABLE'); END;
CREATE TABLE IF NOT EXISTS agent_session_archive (
 session_id TEXT PRIMARY KEY REFERENCES agent_session(id),
 archived_at TEXT NOT NULL
);
"""


def migrate(db):
    """Call explicitly at application startup, after the original domains."""
    # executescript implicitly commits; use individual complete statements so a
    # caller's transaction (including fault-injection tests) remains atomic.
    import sqlite3
    statement = ''
    for line in DDL.splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement)
            statement = ''
    for table in ('agent_session_scope', 'agent_session_member', 'agent_session_event', 'agent_session_archive'):
        for action in ('UPDATE', 'DELETE'):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} "
                       "BEGIN SELECT RAISE(ABORT,'SESSION_SNAPSHOT_IMMUTABLE'); END")
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='project'").fetchone():
        from spectrumagent.projects import initialize
        initialize(db)
    db.execute("INSERT OR IGNORE INTO agent_session_scope(session_id,scope_kind,member_count) "
               "SELECT id,'global',0 FROM agent_session")


def initialize(database):
    from spectrumagent.projects import backup_before_migration
    backup_before_migration(database)
    with connect_database(database) as db:
        db.execute('BEGIN IMMEDIATE')
        migrate(db)
