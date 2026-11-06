"""Resolve, authorize and audit filesystem mutations before performing them.

Audit SQLite is deliberately independent of the business writer. Its fixed
location is root/db/write-audit.sqlite3; audit INSERT never calls this guard.
"""
from collections import deque
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from threading import RLock
from uuid import uuid4
import warnings

from spectrumagent.data import DataError


BUFFER_LIMIT = 1024
_guards = {}
_current = None
_registration_lock = RLock()

DDL = """
CREATE TABLE IF NOT EXISTS write_audit (
 id TEXT PRIMARY KEY NOT NULL, ts TEXT NOT NULL, action TEXT NOT NULL,
 target_path TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('ALLOW','DENY')),
 reason TEXT NOT NULL, deletion_id TEXT NOT NULL, actor TEXT NOT NULL,
 flushed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deletion_audit (
 deletion_id TEXT NOT NULL, action TEXT NOT NULL, cube_id TEXT NOT NULL,
 summary_json TEXT NOT NULL, confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS storage_source (path TEXT PRIMARY KEY NOT NULL);
CREATE TRIGGER IF NOT EXISTS write_audit_no_update BEFORE UPDATE ON write_audit
 BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUDIT'); END;
CREATE TRIGGER IF NOT EXISTS write_audit_no_delete BEFORE DELETE ON write_audit
 BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUDIT'); END;
CREATE TRIGGER IF NOT EXISTS write_audit_no_replace BEFORE INSERT ON write_audit
 WHEN EXISTS(SELECT 1 FROM write_audit WHERE id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUDIT'); END;
CREATE TRIGGER IF NOT EXISTS deletion_audit_no_update BEFORE UPDATE ON deletion_audit
 BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUDIT'); END;
CREATE TRIGGER IF NOT EXISTS deletion_audit_no_delete BEFORE DELETE ON deletion_audit
 BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_AUDIT'); END;
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class WriteGuard:
    def __init__(self, root, *, output_root=None, source_roots=(), temp_root=None,
                 buffer_limit=BUFFER_LIMIT):
        if type(buffer_limit) is not int or buffer_limit < 1:
            raise ValueError('audit buffer must have a positive bound')
        self.root = Path(root).resolve()
        self.output_root = Path(output_root).resolve() if output_root is not None else None
        self.output_root_available = False
        self.output_projects = ()
        self.output_settings_loaded = False
        self._output_root_failed = False  # Latch failure until a new process binds its settings.
        self.temp_root = Path(temp_root or tempfile.gettempdir()).resolve()
        self.sources = {Path(path).resolve() for path in source_roots}
        self.audit_database = self.root / 'db' / 'write-audit.sqlite3'
        self.buffer = deque(maxlen=buffer_limit)
        self.overflow_count = 0
        self._reported_overflow = 0
        self.database_ready = False
        self.ready = False
        self.lock = RLock()
        self.events = []
        self._audit_connection = None
        self.inventory_ready = False

    @property
    def roots(self):
        return tuple(path for path in (self.root, self.output_root, self.temp_root) if path is not None)

    @contextmanager
    def _audit_connect(self):
        # Private fixed-path channel. Never connect_database/resolve_write:
        # business transactions must not lock their own audit INSERT out.
        with self.lock:
            target = self.audit_database.resolve()
            if not target.is_relative_to(self.root) or any(target.is_relative_to(source) for source in self.sources):
                self.database_ready = self.ready = False
                raise DataError('WRITE_TO_SOURCE_DENIED', '审计固定路径越界，已拒绝写任务')
            if self._audit_connection is None:
                self._audit_connection = sqlite3.connect(target, timeout=5, check_same_thread=False)
            with self._audit_connection as db:
                yield db

    def close(self):
        with self.lock:
            if self._audit_connection is not None:
                self._audit_connection.close()
                self._audit_connection = None
            self.database_ready = self.ready = False

    def _insert(self, rows, *, flushed=False):
        with self._audit_connect() as db:
            db.executemany('INSERT INTO write_audit '
                           '(id,ts,action,target_path,decision,reason,deletion_id,actor,flushed_at) '
                           'VALUES (?,?,?,?,?,?,?,?,?)',
                           [(*row, utc_now() if flushed else '') for row in rows])

    def _audit(self, action, target, decision, reason='', deletion_id=''):
        # Every NOT NULL value is supplied explicitly: uuid, server UTC, caller
        # action/path, ALLOW/DENY, error-or-empty, batch-or-empty, fixed actor.
        row = (str(uuid4()), utc_now(), str(action), str(target), decision,
               str(reason), str(deletion_id), 'local')
        with self.lock:
            if self.database_ready:
                try:
                    self._insert([row])
                    return
                except (sqlite3.Error, DataError):
                    self.database_ready = self.ready = False
                    row = (*row[:4], 'DENY', 'WRITE_AUDIT_UNAVAILABLE', *row[6:])
            if len(self.buffer) == self.buffer.maxlen:
                self.overflow_count += 1
                # No paths/filenames are sent to application logs. The warning
                # is independent of the guarded daily-file handler.
                warnings.warn('AUDIT_BUFFER_OVERFLOW', RuntimeWarning, stacklevel=2)
            self.buffer.append(row)

    def attach_database(self):
        with self.lock:
            with self._audit_connect() as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.executescript(DDL)
            pending = list(self.buffer)
            if pending:
                self._insert(pending, flushed=True)
                self.buffer.clear()
            self.database_ready = True
            if self.overflow_count > self._reported_overflow:
                self._audit('AUDIT_BUFFER_OVERFLOW', self.audit_database, 'DENY',
                            f'EVICTED_RECORDS:{self.overflow_count - self._reported_overflow}')
                if self.database_ready:
                    self._reported_overflow = self.overflow_count

    def _check_source_overlap(self):
        if any(source.is_relative_to(root) or root.is_relative_to(source)
               for source in self.sources for root in self.roots):
            raise DataError('STORAGE_SELF_CHECK_FAILED', '数据源目录与可写根重叠')

    def self_check(self):
        self.ready = False
        self.events.append('self_check')
        try:
            self._check_source_overlap()
            if not (self.root / 'trash').is_dir():
                raise OSError('trash missing')
            for root in self.roots:
                if root == self.output_root and self._output_root_failed:
                    continue
                try:
                    if not root.is_dir():
                        raise OSError('writable root missing')
                    probe = root / ('.write-guard-' + uuid4().hex)
                    # Only these internal probes use startup; source checks still apply.
                    self._resolve(probe, 'SELF_CHECK_WRITE', startup=True)
                    try:
                        with probe.open('xb') as stream:
                            stream.write(b'write-guard')
                    finally:
                        self._resolve(probe, 'SELF_CHECK_DELETE', startup=True, deleting=True)
                        probe.unlink(missing_ok=True)
                except OSError:
                    if root != self.output_root:
                        raise
                    self.output_root_available = False
                    self._output_root_failed = True
                    self._audit('OUTPUT_ROOT_UNAVAILABLE', root, 'DENY', 'OUTPUT_ROOT_UNAVAILABLE')
                    continue
                if root == self.output_root:
                    self.output_root_available = True
            self.attach_database()
            self._audit('SELF_CHECK', self.audit_database, 'ALLOW')
            if not self.database_ready or self.buffer:
                raise OSError('audit unavailable')
        except Exception as error:
            self.ready = False
            logging.getLogger(__name__).error('STORAGE_SELF_CHECK_FAILED')
            if isinstance(error, DataError):
                raise
            raise DataError('STORAGE_SELF_CHECK_FAILED', '存储自检失败，已拒绝写任务') from error
        self.ready = True
        self.events.append('business_ready')

    def _resolve(self, path, action, *, startup=False, deleting=False):
        try:
            target = Path(path).resolve()
            reason = ''
            if not any(target.is_relative_to(root) for root in self.roots):
                reason = 'WRITE_TO_SOURCE_DENIED'
            if any(target.is_relative_to(source) or (deleting and source.is_relative_to(target))
                   for source in self.sources):
                reason = 'WRITE_TO_SOURCE_DENIED'
            if deleting and target in self.roots:
                reason = 'WRITE_TO_SOURCE_DENIED'
            if not startup and self.output_root is not None and target.is_relative_to(self.output_root) and not self.output_root_available:
                reason = reason or 'OUTPUT_ROOT_UNAVAILABLE'
            if not startup and not self.ready:
                reason = reason or 'STORAGE_SELF_CHECK_FAILED'
        except (OSError, ValueError, RuntimeError) as error:
            self._audit(action, str(path), 'DENY', 'WRITE_TO_SOURCE_DENIED')
            raise DataError('WRITE_TO_SOURCE_DENIED', '目标路径不允许写入') from error
        self._audit(action, target, 'DENY' if reason else 'ALLOW', reason)
        if reason:
            if reason == 'OUTPUT_ROOT_UNAVAILABLE':
                raise DataError(reason, '输出根不可用，写入已暂停')
            raise DataError(reason, '目标路径不允许写入' if reason == 'WRITE_TO_SOURCE_DENIED' else '存储未通过自检，已拒绝写任务')
        if not self.ready and not startup:
            raise DataError('STORAGE_SELF_CHECK_FAILED', '审计不可用，已拒绝写任务')
        return target

    def resolve_write(self, path, *, kind):
        return self._resolve(path, kind)

    def resolve_delete(self, path):
        return self._resolve(path, 'DELETE', deleting=True)

    def add_sources(self, paths):
        candidates = {Path(path).resolve() for path in paths}
        with self.lock:
            previous = self.sources.copy()
            self.sources.update(candidates)
            try:
                self._check_source_overlap()
            except DataError:
                self.sources = previous
                self._audit('REGISTER_SOURCE', self.root, 'DENY', 'STORAGE_SELF_CHECK_FAILED')
                raise
            self.resolve_write(self.audit_database, kind='SOURCE_REGISTER')
            with self._audit_connect() as db:
                db.executemany('INSERT OR IGNORE INTO storage_source(path) VALUES (?)',
                               [(str(path),) for path in candidates])

    def deletion_event(self, deletion_id, action, cube_id, summary, *, confirmed_by='local'):
        with self.lock, self._audit_connect() as db:
            db.execute('INSERT INTO deletion_audit '
                       '(deletion_id,action,cube_id,summary_json,confirmed_by,created_at) VALUES (?,?,?,?,?,?)',
                       (str(deletion_id), str(action), str(cube_id),
                        json.dumps(summary, ensure_ascii=False, allow_nan=False), str(confirmed_by), utc_now()))


def _existing_sources(guard, database):
    sources = set()
    for path in (guard.audit_database, Path(database)):
        target = path.resolve()
        if not target.is_relative_to(guard.root) or any(target.is_relative_to(source) for source in guard.sources):
            guard._audit('SOURCE_INVENTORY', target, 'DENY', 'WRITE_TO_SOURCE_DENIED')
            raise DataError('WRITE_TO_SOURCE_DENIED', '存储数据库路径越界，已拒绝写任务')
    if guard.audit_database.is_file():
        with closing(sqlite3.connect(guard.audit_database.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='storage_source'").fetchone():
                sources.update(Path(row[0]).resolve() for row in db.execute('SELECT path FROM storage_source'))
    if Path(database).is_file():
        with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='dataset_registry'").fetchone():
                for (payload,) in db.execute('SELECT payload FROM dataset_registry'):
                    dataset = json.loads(payload)
                    sources.update(Path(dataset[name]).resolve().parent for name in ('header_path', 'data_path'))
    return sources


def _prepare(paths, *, output_root=None, source_roots=(), temp_root=None):
    global _current
    key = Path(paths.root).resolve()
    with _registration_lock:
        guard = _guards.get(key)
        if guard is None:
            guard = WriteGuard(key, output_root=output_root, source_roots=source_roots, temp_root=temp_root)
            _guards[key] = guard
        else:
            with guard.lock:
                if output_root is not None and guard.output_root != Path(output_root).resolve():
                    guard.ready = False
                    guard.output_root = Path(output_root).resolve()
                    guard.output_root_available = False
                if temp_root is not None and guard.temp_root != Path(temp_root).resolve():
                    guard.ready = False
                    guard.temp_root = Path(temp_root).resolve()
                if source_roots:
                    guard.ready = False
                    guard.sources.update(Path(path).resolve() for path in source_roots)
        _current = guard
        if not guard.inventory_ready:
            guard.sources.update(_existing_sources(guard, paths.database))
            guard.inventory_ready = True
    return guard


def validate_bootstrap(paths):
    # Read-only preflight prevents even bootstrap mkdir into a known source.
    guard = _prepare(paths)
    try:
        guard._check_source_overlap()
    except DataError:
        guard.ready = False
        guard._audit('BOOTSTRAP', guard.root, 'DENY', 'STORAGE_SELF_CHECK_FAILED')
        raise


def initialize(paths, *, output_root=None, source_roots=(), temp_root=None):
    """Called by create_directories after its explicit bootstrap mkdir phase."""
    guard = _prepare(paths, output_root=output_root, source_roots=source_roots, temp_root=temp_root)
    guard.events.append('directories_created')
    guard.self_check()
    return guard


def bootstrap_output_root(paths):
    """Bind persisted settings once per process, using the existing guarded DB channel."""
    from backend.database import connect_database
    from spectrumagent.api.project_paths import normalize_path, validate_output_root
    guard = for_database(paths.database)
    with guard.lock:
        if guard.output_settings_loaded:
            return None
        with connect_database(paths.database) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='project_path_settings'").fetchone()
            rows = db.execute("SELECT project_id,output_root FROM project_path_settings WHERE output_root<>'' ORDER BY project_id").fetchall() if exists else []
        normalized = [(project, validate_output_root(paths, normalize_path(value))) for project, value in rows]
        roots = {value for _, value in normalized}
        if len(roots) > 1:
            error = DataError('OUTPUT_ROOT_CONFLICT', '多个项目的输出根不一致')
            error.status_code = 409
            raise error
        guard.output_settings_loaded = True
        if not roots:
            return None
        output = roots.pop()
        guard.output_projects = tuple(project for project, _ in normalized)
        guard.ready = guard.database_ready = False  # Startup transition; audit is buffered until self_check flushes it.
        guard.output_root_available = False
        guard._output_root_failed = False
        # Explicit bootstrap exception, matching AppPaths' trash creation.
        # Never resolve_write: the new root is not yet in the write whitelist.
        try:
            if not output.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                guard._audit('OUTPUT_ROOT_CREATE', output, 'ALLOW')
        except OSError:
            guard._output_root_failed = True
            guard._audit('OUTPUT_ROOT_UNAVAILABLE', output, 'DENY', 'OUTPUT_ROOT_UNAVAILABLE')
        return output


def for_database(database):
    from backend.paths import AppPaths
    database = Path(database).resolve()
    root = database.parent.parent if database.parent.name == 'db' else database.parent
    key = root.resolve()
    guard = _guards.get(key)
    if guard is None:
        AppPaths(root).create_directories()
        guard = _guards[key]
    return guard


def _guard_for(path):
    try:
        target = Path(path).resolve()
    except (OSError, ValueError, RuntimeError):
        if _current is not None:
            return _current  # Let _resolve record the invalid-path DENY.
        raise DataError('STORAGE_SELF_CHECK_FAILED', '存储未初始化，已拒绝写任务')
    with _registration_lock:
        matches = [(len(root.parts), guard) for guard in _guards.values()
                   for root in (guard.root, guard.output_root) if root is not None and target.is_relative_to(root)]
        guard = max(matches, key=lambda item: item[0])[1] if matches else _current
    if guard is None:
        raise DataError('STORAGE_SELF_CHECK_FAILED', '存储未初始化，已拒绝写任务')
    return guard


def resolve_write(path, *, kind):
    return _guard_for(path).resolve_write(path, kind=kind)


def resolve_delete(path):
    return _guard_for(path).resolve_delete(path)


def mkdir(path, *, parents=False, exist_ok=False):
    return resolve_write(path, kind='MKDIR').mkdir(parents=parents, exist_ok=exist_ok)


def unlink(path, *, missing_ok=False):
    return resolve_delete(path).unlink(missing_ok=missing_ok)


def rmtree(path):
    return shutil.rmtree(resolve_delete(path))


def replace(source, destination):
    source = resolve_delete(source)
    destination = resolve_write(destination, kind='RENAME_DESTINATION')
    return os.replace(source, destination)


@contextmanager
def temporary_directory(*, prefix='', dir=None):
    parent = Path(dir or tempfile.gettempdir())
    path = parent / (prefix + uuid4().hex)
    mkdir(path)
    try:
        yield str(path)
    finally:
        rmtree(path)
