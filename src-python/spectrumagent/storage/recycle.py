"""Permanent, human-confirmed dataset deletion with a durable cleanup journal.

Historical naming note: the module path, class name and ``registry.recycle``
attribute deliberately keep the word "recycle" so that the A-D contract paths
and the 15-file production-write baseline stay stable. There is no recycle bin
anymore: business rows are deleted, owned product directories are removed via
the single guarded rmtree exit, and original ENVI source files are never
touched. A short-lived ``deletion_pending`` journal only records directories
whose removal must be retried after a crash; it holds no row copies and has no
retention window.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import logging
from pathlib import PurePosixPath
import secrets
from threading import RLock
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary

from backend.database import connect_database
from spectrumagent.data import DataError
from . import guard as storage


DDL = """
CREATE TABLE IF NOT EXISTS deletion_pending (
 deletion_id TEXT NOT NULL, seq INTEGER NOT NULL, dataset_id TEXT NOT NULL,
 path TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(deletion_id,seq)
);
"""
LEGACY_TABLES = ('recycle_bin', 'recycle_item', 'recycle_health')
# The task-card order is authoritative. Project assets and audit tables are absent.
TABLES = ('inference_artifact', 'inference_run', 'model_registry', 'metric',
          'training_fold', 'model_artifact', 'training_run', 'sample_target',
          'preprocess_artifact', 'preprocess_run', 'training_mat', 'annotation',
          'sample_spectrum', 'annotation_version', 'annotation_draft', 'dataset_registry')
PREVIEW_SECONDS = 300
log = logging.getLogger(__name__)
_coordinators = WeakKeyDictionary()
_coordinator_lock = RLock()
_REMOVED = object()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def failure(code, detail, status=409):
    error = DataError(code, detail)
    error.status_code = status
    return error


def relative(value):
    if not isinstance(value, str):
        raise failure('INVALID_DELETE_PATH', '删除路径必须为相对 POSIX 路径')
    path = PurePosixPath(value)
    if (not value or value != path.as_posix() or path.is_absolute()
            or '..' in path.parts or '\\' in value or ':' in value or '\0' in value
            or path.as_posix() == '.'):
        raise failure('INVALID_DELETE_PATH', '删除路径必须为相对 POSIX 路径')
    return path


def scrub(value, identifiers, *, root=True):
    """Remove only deleted references from mutable session memory, never audit rows."""
    if isinstance(value, str):
        return _REMOVED if any(identifier in value for identifier in identifiers) else value
    if isinstance(value, list):
        return [clean for item in value if (clean := scrub(item, identifiers, root=False)) is not _REMOVED]
    if isinstance(value, dict):
        if not root and any(isinstance(value.get(key), str) and value[key] in identifiers
                            for key in ('id', 'cube_id', 'dataset_id')):
            return _REMOVED
        return {key: clean for key, item in value.items()
                if not any(identifier in key for identifier in identifiers)
                and (clean := scrub(item, identifiers, root=False)) is not _REMOVED}
    return value


class Coordinator:
    def __init__(self):
        self.lock = RLock()
        self.ready = False
        self.maintenance = False
        self.active = 0

    def check(self, cube_id=None, key=None):
        with self.lock:
            if not self.ready or self.maintenance:
                raise failure('DELETION_CLEANUP_REQUIRED', '删除清理未完成或正在执行，已拒绝写任务', 503)

    @contextmanager
    def job(self):
        with self.lock:
            self.check()
            self.active += 1
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1

    @contextmanager
    def exclusive(self, *, startup=False):
        with self.lock:
            if self.maintenance or self.active:
                raise failure('DATASET_BUSY', '有任务执行中，请结束后重试删除操作')
            if not startup:
                self.check()
            self.maintenance = True
            if startup:
                self.ready = False
        try:
            yield
        finally:
            with self.lock:
                self.maintenance = False


class RecycleStore:
    def __init__(self, registry, paths, *, clock=None):
        self.registry, self.paths, self.database = registry, paths, registry.database
        self.guard = registry.storage_guard
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.secret = secrets.token_bytes(32)
        with _coordinator_lock:
            self.coordinator = _coordinators.setdefault(self.guard, Coordinator())
        with connect_database(self.database) as db:
            for statement in DDL.split(';'):
                if statement.strip():
                    db.execute(statement)
        if not self.coordinator.ready:
            self.finish_pending()

    def _rows(self, db, table, where='', parameters=()):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return []
        cursor = db.execute(f'SELECT * FROM {table}' + (f' WHERE {where}' if where else '') + ' ORDER BY rowid', parameters)
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor]

    def _selected(self, db, cube):
        selected = {table: [] for table in TABLES}
        def by_ids(table, column, ids, *, extra='', parameters=()):
            # JSON1 avoids an unbounded SQL placeholder list for long version histories.
            clause = f'{column} IN (SELECT value FROM json_each(?))'
            return self._rows(db, table, (extra + ' OR ' if extra else '') + clause,
                              (*parameters, encode(sorted(ids))))
        selected['dataset_registry'] = self._rows(db, 'dataset_registry', 'id=?', (cube,))
        if not selected['dataset_registry']:
            raise failure('DATASET_NOT_FOUND', '数据集不存在', 404)
        selected['annotation_version'] = self._rows(db, 'annotation_version', 'cube_id=?', (cube,))
        versions = {r['id'] for r in selected['annotation_version']}
        selected['preprocess_run'] = by_ids('preprocess_run', 'annotation_version_id', versions,
                                             extra='cube_id=?', parameters=(cube,))
        preprocess = {r['id'] for r in selected['preprocess_run']}
        clauses, parameters = [], []
        for column, identifiers in (('cube_ids', {cube}), ('annotation_version_ids', versions),
                                    ('preprocess_run_ids', preprocess)):
            clauses.append(f"NOT json_valid({column}) OR EXISTS (SELECT 1 FROM json_each("
                           f"CASE WHEN json_valid({column}) THEN {column} ELSE '[]' END) "
                           'WHERE value IN (SELECT value FROM json_each(?)))')
            parameters.append(encode(sorted(identifiers)))
        for row in self._rows(db, 'training_run', ' OR '.join(clauses), parameters):
            try:
                cubes = json.loads(row['cube_ids'])
                refs = json.loads(row['annotation_version_ids'])
                runs = json.loads(row['preprocess_run_ids'])
                if any(not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                       for values in (cubes, refs, runs)):
                    raise ValueError('invalid references')
            except (ValueError, TypeError) as error:
                raise failure('INVALID_RUN_REFERENCES', '训练台账引用不合法，拒绝删除') from error
            if cube in cubes or versions.intersection(refs) or preprocess.intersection(runs):
                if set(cubes) != {cube}:
                    raise failure('MULTI_CUBE_RUN', '训练 run 关联多个数据集，拒绝单独删除；请先处理关联实验')
                selected['training_run'].append(row)
        training = {r['id'] for r in selected['training_run']}
        selected['model_registry'] = by_ids('model_registry', 'run_id', training)
        models = {r['id'] for r in selected['model_registry']}
        selected['inference_run'] = self._rows(db, 'inference_run',
            'cube_id=? OR model_id IN (SELECT value FROM json_each(?)) '
            'OR annotation_version_id IN (SELECT value FROM json_each(?)) '
            'OR preprocess_run_id IN (SELECT value FROM json_each(?))',
            (cube, encode(sorted(models)), encode(sorted(versions)), encode(sorted(preprocess))))
        for table in ('preprocess_run', 'inference_run'):
            if any(r['cube_id'] != cube for r in selected[table]):
                raise failure('CROSS_CUBE_DEPENDENCY', '有关联其他数据集的实验引用，拒绝单独删除')
        for table in ('preprocess_run', 'training_run', 'inference_run'):
            if any(r['status'] in ('pending', 'running') for r in selected[table]):
                raise failure('DATASET_BUSY', '关联 run 尚未结束，拒绝删除')
        inference = {r['id'] for r in selected['inference_run']}
        for table, runs in (('inference_artifact', inference), ('metric', training),
                            ('training_fold', training), ('model_artifact', training),
                            ('preprocess_artifact', preprocess)):
            selected[table] = by_ids(table, 'run_id', runs)
        for table in ('annotation', 'sample_spectrum'):
            selected[table] = by_ids(table, 'version_id', versions, extra='cube_id=?', parameters=(cube,))
        selected['training_mat'] = by_ids('training_mat', 'annotation_version_id', versions,
                                           extra='cube_id=?', parameters=(cube,))
        for table in ('annotation', 'sample_spectrum', 'training_mat'):
            if any(r['cube_id'] != cube for r in selected[table]):
                raise failure('CROSS_CUBE_DEPENDENCY', '有关联其他数据集的标注引用，拒绝单独删除')
        for table in ('sample_target', 'annotation_draft'):
            selected[table] = self._rows(db, table, 'cube_id=?', (cube,))
        return selected

    def _owned(self, source, cube):
        path = relative(source)
        parts = path.parts
        valid = ((len(parts) >= 3 and parts[0] == 'annotations' and parts[1] == cube)
                 or (len(parts) == 2 and parts[0] == 'exports' and parts[1] == cube)
                 or (len(parts) == 3 and parts[0] == 'preprocessed' and parts[1] == cube)
                 or (len(parts) == 2 and parts[0] in ('models', 'inferences')
                     and str(UUID(parts[1])) == parts[1]))
        if not valid:
            raise failure('INVALID_DELETE_PATH', '删除映射不属于该数据集的产物目录')
        target = self.paths.root.joinpath(*parts)
        if not target.resolve().is_relative_to(self.paths.root.resolve().joinpath(parts[0])):
            raise failure('INVALID_DELETE_PATH', '产物目录越界')
        return target

    def _inventory(self, roots, *, base=None):
        base = base or self.paths.root
        entries = []
        for source in roots:
            folder = base.joinpath(*relative(source).parts)
            if not folder.is_dir() or folder.is_symlink():
                raise failure('DELETE_INVENTORY_INCOMPLETE', '产物目录缺失或包含非法链接')
            for path in [folder, *sorted(folder.rglob('*'))]:
                if path.is_symlink() or path.is_junction():
                    raise failure('INVALID_DELETE_PATH', '产物目录包含链接，永久删除前须人工处理')
                name = path.relative_to(base).as_posix()
                if path.is_dir():
                    entries.append({'path': name, 'kind': 'directory'})
                elif path.is_file():
                    stat = path.stat()
                    entries.append({'path': name, 'kind': 'file', 'bytes': stat.st_size,
                                    'mtime_ns': stat.st_mtime_ns})
                else:
                    raise failure('INVALID_DELETE_PATH', '产物目录包含不支持的文件项')
        return sorted(entries, key=lambda e: e['path'])

    def _plan(self, cube):
        with connect_database(self.database) as db:
            db.execute('BEGIN')
            selected = self._selected(db, cube)
        roots = set()
        for row in selected['annotation_version']:
            ref = relative(row['snapshot_ref'])
            source = self.paths.snapshots.joinpath(*ref.parts).relative_to(self.paths.root).as_posix()
            self._owned(source, cube)
            if not self.paths.root.joinpath(*relative(source).parts).is_dir():
                raise failure('DELETE_INVENTORY_INCOMPLETE', '已登记标注快照目录缺失，拒绝删除')
            roots.add(source)
        for source in [f'exports/{cube}',
                       *(f'preprocessed/{cube}/{r["id"]}' for r in selected['preprocess_run']),
                       *(f'models/{r["id"]}' for r in selected['training_run']),
                       *(f'inferences/{r["id"]}' for r in selected['inference_run'])]:
            if self._owned(source, cube).exists():
                roots.add(source)
        roots = sorted(roots)
        # Overlapping snapshot refs could otherwise remove the same file twice.
        if any(a != b and relative(b).is_relative_to(relative(a)) for a in roots for b in roots):
            raise failure('INVALID_SNAPSHOT_REF', '标注快照目录重叠，拒绝删除')
        entries = self._inventory(roots)
        rows = [{'table_name': table, 'row': row} for table in TABLES for row in selected[table]]
        return {'cube_id': cube, 'rows': rows, 'roots': roots, 'entries': entries}

    def _summary(self, plan):
        counts = {table: sum(item['table_name'] == table for item in plan['rows']) for table in TABLES}
        directories = [{'path': source, 'bytes': sum(e.get('bytes', 0) for e in plan['entries']
                        if relative(e['path']).is_relative_to(relative(source)))} for source in plan['roots']]
        return {'cube_id': plan['cube_id'], 'annotation_versions': counts['annotation_version'],
                'preprocess_runs': counts['preprocess_run'], 'training_runs': counts['training_run'],
                'inference_runs': counts['inference_run'], 'directories': directories,
                'total_bytes': sum(e.get('bytes', 0) for e in plan['entries'])}

    def preview(self, cube_id):
        cube = str(UUID(str(cube_id)))
        self.coordinator.check(cube)
        with self.registry.lock:
            plan = self._plan(cube)
        expires = self.clock() + timedelta(seconds=PREVIEW_SECONDS)
        payload = encode({'cube_id': cube, 'sha256': digest(plan), 'expires': expires.timestamp()}).encode()
        token = base64.urlsafe_b64encode(payload).decode() + '.' + hmac.new(self.secret, payload, 'sha256').hexdigest()
        return {**self._summary(plan), 'preview_token': token, 'expires_at': expires.isoformat()}

    def _token(self, token, cube):
        try:
            if not isinstance(token, str) or len(token) > 2048:
                raise ValueError('invalid token')
            raw, signature = token.split('.')
            payload = base64.b64decode(raw, altchars=b'-_', validate=True)
            if not hmac.compare_digest(signature, hmac.new(self.secret, payload, 'sha256').hexdigest()):
                raise ValueError('invalid signature')
            value = json.loads(payload)
            if value['cube_id'] != cube or value['expires'] <= self.clock().timestamp():
                raise ValueError('expired token')
            return value['sha256']
        except (ValueError, KeyError, TypeError) as error:
            raise failure('DELETE_PREVIEW_EXPIRED', '删除预览已失效，请重新查看影响清单并确认') from error

    def _erase(self, source, cube):
        target = self._owned(source, cube)
        if target.exists():
            storage.rmtree(target)
        return target

    def delete(self, cube_id, *, confirm, preview_token):
        """Delete rows first, then owned product directories through the guard.

        The row transaction commits before any file is removed. A crash in the
        file phase leaves only orphan product directories, never live rows that
        point at missing files; ``deletion_pending`` drives the startup retry.
        """
        cube = str(UUID(str(cube_id)))
        self.coordinator.check(cube)
        if confirm is not True:
            raise failure('DELETE_CONFIRMATION_REQUIRED', '请在界面确认影响清单后永久删除')
        expected = self._token(preview_token, cube)
        deletion, created = str(uuid4()), self.clock()
        with self.coordinator.exclusive(), self.registry.lock:
            plan = self._plan(cube)
            if not hmac.compare_digest(expected, digest(plan)):
                raise failure('DELETE_PREVIEW_CHANGED', '影响清单已改变，请重新预览并确认')
            summary = self._summary(plan)
            try:
                with connect_database(self.database, timeout=10) as db:
                    db.execute('BEGIN IMMEDIATE')
                    current = self._selected(db, cube)
                    if plan['rows'] != [{'table_name': t, 'row': r} for t in TABLES for r in current[t]]:
                        raise failure('DELETE_PREVIEW_CHANGED', '数据库影响清单已改变，请重新确认')
                    db.executemany('INSERT INTO deletion_pending VALUES (?,?,?,?,?)',
                                   [(deletion, seq, cube, source, created.isoformat())
                                    for seq, source in enumerate(plan['roots'])])
                    for item in plan['rows']:
                        table, values = item['table_name'], item['row']
                        key = 'cube_id' if table == 'annotation_draft' else 'id'
                        db.execute(f'DELETE FROM {table} WHERE {key}=?', (values[key],))
                    identifiers = {cube, *(r['id'] for table in ('annotation_version', 'preprocess_run',
                                   'training_run', 'inference_run') for r in current[table])}
                    for session, context in db.execute('SELECT id,context_json FROM agent_session').fetchall():
                        value = json.loads(context)
                        clean = scrub(value, identifiers)
                        if clean != value:
                            db.execute('UPDATE agent_session SET context_json=? WHERE id=?', (encode(clean), session))
            except BaseException as error:
                self.guard.deletion_event(deletion, 'DELETE_ABORTED', cube, {'reason': type(error).__name__})
                raise
            pending = []
            for seq, source in enumerate(plan['roots']):
                try:
                    self._erase(source, cube)
                except (DataError, OSError, ValueError) as error:
                    pending.append(source)
                    self.guard.deletion_event(deletion, 'DELETE_PENDING', cube,
                                              {'path': source, 'reason': str(error)})
                    log.warning('DELETE_PENDING deletion_id=%s path=%s', deletion, source)
                    continue
                with connect_database(self.database) as db:
                    db.execute('DELETE FROM deletion_pending WHERE deletion_id=? AND seq=?', (deletion, seq))
            self.guard.deletion_event(deletion, 'DELETE', cube,
                                      {**summary, 'permanent': True, 'pending_directories': pending})
        return {'deletion_id': deletion, 'deleted_at': created.isoformat(),
                'permanent': True, 'pending_directories': pending, **summary}

    def _purge_legacy(self):
        """One-time removal of the retired 30-day recycle bin tables and trash content."""
        with connect_database(self.database) as db:
            existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            legacy = [table for table in LEGACY_TABLES if table in existing]
        trash = self.paths.trash
        entries = sorted(trash.iterdir()) if trash.is_dir() else []
        if not legacy and not entries:
            return False
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            for table in legacy:
                db.execute(f'DROP TABLE {table}')
        quarantined = 0
        for entry in entries:
            if entry.is_symlink() or entry.is_junction():
                quarantined += 1
                continue
            if entry.is_dir():
                storage.rmtree(entry)
            else:
                storage.unlink(entry)
        self.guard.deletion_event('LEGACY', 'LEGACY_RECYCLE_PURGED', '',
                                  {'tables': legacy, 'trash_entries': len(entries),
                                   'quarantined_links': quarantined})
        return True

    def finish_pending(self):
        """Startup cleanup: retire legacy bins, then finish interrupted deletions."""
        with self.coordinator.exclusive(startup=True), self.registry.lock:
            self.guard.events.append('deletion_cleanup_started')
            self._purge_legacy()
            with connect_database(self.database) as db:
                pending = self._rows(db, 'deletion_pending')
            remaining = 0
            for item in pending:
                try:
                    self._erase(item['path'], item['dataset_id'])
                except (DataError, OSError, ValueError) as error:
                    remaining += 1
                    self.guard.deletion_event(item['deletion_id'], 'DELETE_CLEANUP_PENDING',
                                              item['dataset_id'], {'path': item['path'], 'reason': str(error)})
                    log.warning('DELETE_CLEANUP_PENDING path=%s', item['path'])
                    continue
                with connect_database(self.database) as db:
                    db.execute('DELETE FROM deletion_pending WHERE deletion_id=? AND seq=?',
                               (item['deletion_id'], item['seq']))
                self.guard.deletion_event(item['deletion_id'], 'DELETE_CLEANUP_DONE',
                                          item['dataset_id'], {'path': item['path']})
            self.coordinator.ready = True
            self.guard.events.append('deletion_business_ready')
            return remaining
