"""Durable operation ledger. Business transactions own this connection.

Stored beside recipes and runs; startup reconciles abandoned execution leases
without automatically repeating computations.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from uuid import uuid4

from backend.database import connect_database
from spectrumagent.data import DataError


RESERVED_INPUT_FIELDS = frozenset({'operation_id', 'submission_ref', 'action_ref', 'authorization_source',
                                  'owner_session_id', 'execution_context', 'server_context', 'operation_context',
                                  'batch_admission','confirmation_context'})
DDL = """CREATE TABLE IF NOT EXISTS business_operation (
 operation_id TEXT PRIMARY KEY NOT NULL,
 submission_ref TEXT NOT NULL,
 action_ref TEXT NOT NULL,
 owner_session_id TEXT NOT NULL,
 authorization_source TEXT NOT NULL,
 kind TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('registered','running','succeeded','failed','needs_reconciliation')),
 run_id TEXT UNIQUE,
 executor_id TEXT,
 evidence_root TEXT,
 evidence_directory TEXT,
 receipt_json TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 UNIQUE(submission_ref,action_ref)
)"""


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class Submission:
    submission_ref: str
    action_ref: str
    owner_session_id: str
    authorization_source: str

    def __post_init__(self):
        if any(type(v) is not str or not re.fullmatch(r'[A-Za-z0-9:._-]{1,256}', v) for v in
               (self.submission_ref, self.action_ref, self.owner_session_id, self.authorization_source)):
            raise TypeError('server submission identity required')


current_submission = ContextVar('business_submission', default=None)


@dataclass(frozen=True)
class BatchAdmission:
    submission_ref: str
    members: frozenset


current_admission = ContextVar('batch_admission',default=None)


def admitted(submission,member):
    admission=current_admission.get()
    return (type(admission) is BatchAdmission and admission.submission_ref==submission.submission_ref
            and tuple(member[key] for key in ('cube_id','annotation_version_id','recipe_version_id')) in admission.members)


def explicit_submission(reference=None, *, action='0', owner='application', source='http_explicit'):
    return Submission(reference or str(uuid4()), action, owner, source)


@contextmanager
def execution_context(submission):
    if type(submission) is not Submission:
        raise TypeError('Submission context required')
    token = current_submission.set(submission)
    try:
        yield
    finally:
        current_submission.reset(token)


def context():
    return current_submission.get() or explicit_submission(source='direct_explicit')


def child(parent, action):
    return replace(parent, action_ref=parent.action_ref + '.' + str(action))


def migrate(db):
    db.execute(DDL)
    db.execute('CREATE TABLE IF NOT EXISTS business_submission ('
               'submission_ref TEXT PRIMARY KEY NOT NULL, owner_session_id TEXT NOT NULL, turn_ref TEXT NOT NULL,'
               'source_request_id TEXT NOT NULL, UNIQUE(owner_session_id,turn_ref))')


def conversation_submission(database, session_id, turn_ref, request_id):
    with connect_database(database) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO business_submission(submission_ref,owner_session_id,turn_ref,source_request_id) '
                   'VALUES (?,?,?,?) ON CONFLICT(owner_session_id,turn_ref) DO NOTHING',
                   (str(uuid4()), session_id, turn_ref, request_id))
        reference, source = db.execute('SELECT submission_ref,source_request_id FROM business_submission '
                                      'WHERE owner_session_id=? AND turn_ref=?', (session_id,turn_ref)).fetchone()
    return reference, 'user_request:' + source


def _row(db, operation_id):
    cursor = db.execute('SELECT * FROM business_operation WHERE operation_id=?', (operation_id,))
    row = cursor.fetchone()
    return None if row is None else dict(zip([c[0] for c in cursor.description], row))


def lookup(db, submission, kind, payload):
    fingerprint = sha256(encode(payload).encode('utf-8')).hexdigest()
    cursor = db.execute('SELECT operation_id FROM business_operation WHERE submission_ref=? AND action_ref=?',
                        (submission.submission_ref, submission.action_ref))
    found = cursor.fetchone()
    if found is None:
        return None
    row = _row(db, found[0])
    if row['owner_session_id'] != submission.owner_session_id:
        raise DataError('OPERATION_OWNER_MISMATCH', '业务提交不属于当前会话')
    if row['kind'] != kind or row['payload_sha256'] != fingerprint:
        raise DataError('IDEMPOTENCY_CONFLICT', '同一业务提交的参数发生变化，请作为新的明确提交执行')
    return row


def begin(db, submission, kind, payload, *, run_id=None):
    """Called under the business service's short BEGIN IMMEDIATE transaction."""
    old = lookup(db, submission, kind, payload)
    if old is not None:
        return old, False
    identifier, timestamp = str(uuid4()), now()
    db.execute('INSERT INTO business_operation '
               '(operation_id,submission_ref,action_ref,owner_session_id,authorization_source,kind,payload_sha256,status,run_id,created_at,updated_at) '
               "VALUES (?,?,?,?,?,?,?,'registered',?,?,?) ON CONFLICT(submission_ref,action_ref) DO NOTHING",
               (identifier, submission.submission_ref, submission.action_ref, submission.owner_session_id,
                submission.authorization_source, kind, sha256(encode(payload).encode()).hexdigest(), run_id, timestamp, timestamp))
    return lookup(db, submission, kind, payload), True


def finish(db, operation_id, status, receipt):
    if status not in {'succeeded', 'failed'}:
        raise ValueError('terminal receipt required')
    row = _row(db, operation_id)
    if row['status'] in {'succeeded','failed'}:
        if row['status'] != status or row['receipt_json'] != encode(receipt):
            raise DataError('OPERATION_TERMINAL', '业务终态已经确定')
        return
    db.execute('UPDATE business_operation SET status=?,receipt_json=?,updated_at=? WHERE operation_id=?',
               (status, encode(receipt), now(), operation_id))


def claim(database, operation_id, executor_id):
    with connect_database(database) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("UPDATE business_operation SET status='running',executor_id=?,updated_at=? "
                         "WHERE operation_id=? AND status='registered'", (executor_id, now(), operation_id))
        return row.rowcount == 1


def uncertain(database, operation_id):
    with connect_database(database) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE business_operation SET status='needs_reconciliation',updated_at=? "
                   "WHERE operation_id=? AND status NOT IN ('succeeded','failed')", (now(), operation_id))


def recover_interrupted(database):
    """A new engine may inspect old application-run records, never resume compute."""
    with connect_database(database) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE business_operation SET status='needs_reconciliation',updated_at=? WHERE status IN ('registered','running')",
                   (now(),))


def receipt(row):
    if row['receipt_json'] is None:
        raise DataError('OPERATION_IN_PROGRESS', '同一业务提交已受理，请查询原操作进度，不自动重做')
    return json.loads(row['receipt_json'])


def get(database, operation_id, owner):
    with connect_database(database) as db:
        row = _row(db, operation_id)
    if row is None or row['owner_session_id'] != owner:
        raise DataError('OPERATION_NOT_FOUND', '业务操作不存在或不属于当前会话')
    return {k: row[k] for k in ('operation_id','kind','status','run_id','created_at','updated_at')} | {
        'receipt': json.loads(row['receipt_json']) if row['receipt_json'] else None}
