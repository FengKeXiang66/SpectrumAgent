"""Transactional dataset recycling with guarded moves and startup reconciliation."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import logging
from pathlib import PurePosixPath
import secrets
import sqlite3
from threading import RLock
from uuid import UUID, uuid4
from weakref import WeakKeyDictionary

from backend.database import connect_database
from spectrumagent.data import DataError
from . import guard as storage


DDL = """
CREATE TABLE IF NOT EXISTS recycle_bin (
 deletion_id TEXT PRIMARY KEY, cube_id TEXT NOT NULL, header_key TEXT NOT NULL,
 raw INTEGER NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
 reason TEXT, restored_at TEXT, purged_at TEXT, manifest_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recycle_item (
 deletion_id TEXT NOT NULL, seq INTEGER NOT NULL, table_name TEXT NOT NULL,
 row_json TEXT NOT NULL, file_src TEXT, file_dst TEXT,
 PRIMARY KEY(deletion_id,seq)
);
CREATE TABLE IF NOT EXISTS recycle_health (
 deletion_id TEXT PRIMARY KEY, cube_id TEXT NOT NULL, status TEXT NOT NULL
);
"""
# The task-card order is authoritative. Project assets and audit tables are absent.
TABLES = ('inference_artifact', 'inference_run', 'model_registry', 'metric',
          'training_fold', 'model_artifact', 'training_run', 'sample_target',
          'preprocess_artifact', 'preprocess_run', 'training_mat', 'annotation',
          'sample_spectrum', 'annotation_version', 'annotation_draft', 'dataset_registry')
FILE_ITEM = '@file'
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
        raise failure('INVALID_RECYCLE_PATH', '回收站路径必须为相对 POSIX 路径')
    path = PurePosixPath(value)
    if (not value or value != path.as_posix() or path.is_absolute()
            or '..' in path.parts or '\\' in value or ':' in value or '\0' in value
            or path.as_posix() == '.'):
        raise failure('INVALID_RECYCLE_PATH', '回收站路径必须为相对 POSIX 路径')
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
        self.blocked = set()
        self.blocked_keys = set()

    def check(self, cube_id=None, key=None):
        with self.lock:
            if not self.ready or self.maintenance or str(cube_id) in self.blocked or key in self.blocked_keys:
                raise failure('RECYCLE_RECONCILIATION_REQUIRED', '回收站正在对账或存在待人工处置的产物，已拒绝写任务', 503)

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
                raise failure('DATASET_BUSY', '有任务执行中，请结束后重试回收站操作')
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
            self.reconcile()
            self.purge_expired()

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
            raise failure('INVALID_RECYCLE_PATH', '回收站映射不属于该数据集的产物目录')
        target = self.paths.root.joinpath(*parts)
        if not target.resolve().is_relative_to(self.paths.root.resolve().joinpath(parts[0])):
            raise failure('INVALID_RECYCLE_PATH', '产物目录越界')
        return target

    def _inventory(self, roots, *, base=None):
        base = base or self.paths.root
        entries = []
        for source in roots:
            folder = base.joinpath(*relative(source).parts)
            if not folder.is_dir() or folder.is_symlink():
                raise failure('RECYCLE_INCOMPLETE', '产物目录缺失或包含非法链接')
            for path in [folder, *sorted(folder.rglob('*'))]:
                if path.is_symlink() or path.is_junction():
                    raise failure('INVALID_RECYCLE_PATH', '产物目录包含链接，拒绝移动')
                name = path.relative_to(base).as_posix()
                if path.is_dir():
                    entries.append({'path': name, 'kind': 'directory'})
                elif path.is_file():
                    stat = path.stat()
                    entries.append({'path': name, 'kind': 'file', 'bytes': stat.st_size,
                                    'mtime_ns': stat.st_mtime_ns})
                else:
                    raise failure('INVALID_RECYCLE_PATH', '产物目录包含不支持的文件项')
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
                raise failure('RECYCLE_INCOMPLETE', '已登记标注快照目录缺失，拒绝删除')
            roots.add(source)
        for source in [f'exports/{cube}',
                       *(f'preprocessed/{cube}/{r["id"]}' for r in selected['preprocess_run']),
                       *(f'models/{r["id"]}' for r in selected['training_run']),
                       *(f'inferences/{r["id"]}' for r in selected['inference_run'])]:
            if self._owned(source, cube).exists():
                roots.add(source)
        roots = sorted(roots)
        # Overlapping snapshot refs could otherwise move the same file twice.
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

    def _items(self, db, deletion):
        cursor = db.execute('SELECT seq,table_name,row_json,file_src,file_dst FROM recycle_item '
                            'WHERE deletion_id=? ORDER BY seq', (deletion,))
        return [dict(zip(('seq', 'table_name', 'row_json', 'file_src', 'file_dst'), r)) for r in cursor]

    def _move(self, source, destination):
        if destination.exists():
            raise failure('RECYCLE_FILE_CONFLICT', '产物目标位置已有文件，拒绝覆盖')
        storage.mkdir(destination.parent, parents=True, exist_ok=True)
        storage.replace(source, destination)

    def _clean_empty(self, folder):
        if folder.exists():
            if any(p.is_file() and p != folder / 'manifest.json' for p in folder.rglob('*')):
                raise failure('RECYCLE_INCOMPLETE', '回收目录仍含未移回的产物，拒绝清理')
            storage.rmtree(folder)

    def delete(self, cube_id, *, confirm, preview_token):
        cube = str(UUID(str(cube_id)))
        self.coordinator.check(cube)
        if confirm is not True:
            raise failure('DELETE_CONFIRMATION_REQUIRED', '请在界面确认影响清单后删除')
        expected = self._token(preview_token, cube)
        deletion, moved = str(uuid4()), []
        folder = self.paths.trash / deletion
        with self.coordinator.exclusive(), self.registry.lock:
            # Inventory metadata and its hash are prepared before the short write
            # transaction. Recycling never rereads multi-GB array contents.
            plan = self._plan(cube)
            if not hmac.compare_digest(expected, digest(plan)):
                raise failure('DELETE_PREVIEW_CHANGED', '影响清单已改变，请重新预览并确认')
            created = self.clock()
            row = next(item['row'] for item in plan['rows'] if item['table_name'] == 'dataset_registry')
            items = [{'table_name': item['table_name'], 'row_json': encode(item['row']),
                      'file_src': None, 'file_dst': None} for item in plan['rows']]
            items.extend({'table_name': FILE_ITEM, 'row_json': '{}', 'file_src': source,
                          'file_dst': f'trash/{deletion}/{source}'} for source in plan['roots'])
            manifest = {'deletion_id': deletion, 'cube_id': cube, 'items': items, 'entries': plan['entries']}
            try:
                with connect_database(self.database, timeout=10) as db:
                    db.execute('BEGIN IMMEDIATE')
                    current = self._selected(db, cube)
                    if plan['rows'] != [{'table_name': t, 'row': r} for t in TABLES for r in current[t]]:
                        raise failure('DELETE_PREVIEW_CHANGED', '数据库影响清单已改变，请重新确认')
                    db.execute('INSERT INTO recycle_bin VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (deletion, cube, row['header_key'], row['raw'], created.isoformat(),
                                (created + timedelta(days=30)).isoformat(), None, None, None, digest(manifest)))
                    db.executemany('INSERT INTO recycle_item VALUES (?,?,?,?,?,?)',
                                   [(deletion, seq, item['table_name'], item['row_json'], item['file_src'], item['file_dst'])
                                    for seq, item in enumerate(items)])
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
                    storage.mkdir(folder, parents=True)
                    storage.resolve_write(folder / 'manifest.json', kind='RECYCLE_MANIFEST').write_text(encode(manifest), 'utf-8')
                    for source in plan['roots']:
                        src, dst = self._owned(source, cube), folder.joinpath(*relative(source).parts)
                        self._move(src, dst)
                        moved.append((src, dst))
            except BaseException:
                try:
                    for src, dst in reversed(moved):
                        self._move(dst, src)
                    self._clean_empty(folder)
                except BaseException:
                    self.coordinator.ready = False
                    log.warning('RECYCLE_ROLLBACK_REQUIRED deletion_id=%s', deletion)
                    raise
                self.guard.deletion_event(deletion, 'DELETE_ROLLBACK', cube, {'reason': 'TRANSACTION_FAILED'})
                raise
        summary = self._summary(plan)
        self.guard.deletion_event(deletion, 'DELETE', cube, summary)
        return {'deletion_id': deletion, 'expires_at': (created + timedelta(days=30)).isoformat(), **summary}

    def _batch(self, db, deletion):
        cursor = db.execute('SELECT * FROM recycle_bin WHERE deletion_id=?', (deletion,))
        row = cursor.fetchone()
        if row is None:
            raise failure('RECYCLE_NOT_FOUND', '回收站条目不存在', 404)
        return dict(zip((c[0] for c in cursor.description), row))

    def _manifest(self, deletion, batch, items):
        folder = self.paths.trash / deletion
        try:
            manifest = json.loads((folder / 'manifest.json').read_text('utf-8'))
            if manifest['deletion_id'] != deletion or manifest['cube_id'] != batch['cube_id']:
                raise ValueError('identity mismatch')
            if digest(manifest) != batch['manifest_sha256']:
                raise ValueError('manifest mismatch')
            if manifest['items'] != [{k: v for k, v in item.items() if k != 'seq'} for item in items]:
                raise ValueError('row mapping mismatch')
            roots = self._mapping(deletion, batch['cube_id'], items)
            if self._inventory([src for src, _ in roots], base=folder) != manifest['entries']:
                raise ValueError('inventory mismatch')
            expected = {'manifest.json', *(e['path'] for e in manifest['entries'])}
            for entry in manifest['entries']:
                expected.update(parent.as_posix() for parent in relative(entry['path']).parents
                                if parent.as_posix() != '.')
            if any(p.relative_to(folder).as_posix() not in expected for p in folder.rglob('*')):
                raise ValueError('unmapped item')
            return manifest
        except (OSError, ValueError, KeyError, TypeError, DataError) as error:
            raise failure('RECYCLE_INCOMPLETE', '回收站目录或清单不完整，须人工处置，禁止恢复与到期清理') from error

    def _mapping(self, deletion, cube, items):
        mapping = []
        for item in items:
            if item['table_name'] == FILE_ITEM:
                source = relative(item['file_src']).as_posix()
                self._owned(source, cube)
                destination = relative(item['file_dst']).as_posix()
                if destination != f'trash/{deletion}/{source}':
                    raise failure('INVALID_RECYCLE_PATH', '回收站映射目标越界')
                mapping.append((source, destination))
            elif item['table_name'] not in TABLES or item['file_src'] is not None or item['file_dst'] is not None:
                raise failure('INVALID_RECYCLE_MANIFEST', '回收站包含非法业务表或文件映射')
        return mapping

    def _mark(self, deletion, cube, status):
        with connect_database(self.database) as db:
            db.execute('INSERT INTO recycle_health VALUES (?,?,?) ON CONFLICT(deletion_id) '
                       'DO UPDATE SET cube_id=excluded.cube_id,status=excluded.status', (deletion, cube, status))
            for key, raw in db.execute('SELECT header_key,raw FROM dataset_registry WHERE id=? '
                                      'UNION SELECT header_key,raw FROM recycle_bin WHERE cube_id=?', (cube, cube)):
                self.coordinator.blocked_keys.add((key, raw))
        self.coordinator.blocked.add(cube)
        log.warning('%s deletion_id=%s', status, deletion)

    def restore(self, deletion_id, *, confirm):
        deletion = str(UUID(str(deletion_id)))
        if confirm is not True:
            raise failure('RESTORE_CONFIRMATION_REQUIRED', '请在界面确认恢复')
        moved = []
        with self.coordinator.exclusive(), self.registry.lock:
            with connect_database(self.database) as db:
                batch, items = self._batch(db, deletion), self._items(db, deletion)
                if batch['restored_at'] or batch['purged_at']:
                    raise failure('RECYCLE_NOT_ACTIVE', '回收站条目已处理')
                if datetime.fromisoformat(batch['expires_at']) <= self.clock():
                    raise failure('RECYCLE_EXPIRED', '回收站条目已满 30 天，不能恢复')
                if db.execute('SELECT 1 FROM recycle_health WHERE deletion_id=?', (deletion,)).fetchone():
                    raise failure('RECYCLE_INCOMPLETE', '回收站条目须人工处置，禁止恢复')
                conflict = db.execute('SELECT 1 FROM dataset_registry WHERE header_key=? AND raw=?',
                                      (batch['header_key'], batch['raw'])).fetchone()
            if conflict:
                self.guard.deletion_event(deletion, 'RESTORE_DENIED', batch['cube_id'], {'reason': 'ACTIVE_PATH_CONFLICT'})
                raise failure('RESTORE_CONFLICT', '同路径已有活跃数据集；想恢复旧的，须先把新的也删进回收站，或等 30 天到期')
            try:
                self._manifest(deletion, batch, items)
            except DataError:
                self._mark(deletion, batch['cube_id'], 'INCOMPLETE')
                raise
            mapping = self._mapping(deletion, batch['cube_id'], items)
            try:
                with connect_database(self.database, timeout=10) as db:
                    db.execute('BEGIN IMMEDIATE')
                    for item in reversed(items):
                        table = item['table_name']
                        if table == FILE_ITEM:
                            continue
                        row = json.loads(item['row_json'])
                        columns = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                        if not isinstance(row, dict) or set(row) != columns:
                            raise failure('INVALID_RECYCLE_MANIFEST', '回收站行结构与当前表不符，拒绝恢复')
                        names = list(row)
                        db.execute(f'INSERT INTO {table} ({",".join(names)}) VALUES ({",".join("?" for _ in names)})',
                                   [row[name] for name in names])
                    for source, destination in reversed(mapping):
                        src = self.paths.root.joinpath(*relative(destination).parts)
                        dst = self._owned(source, batch['cube_id'])
                        self._move(src, dst)
                        moved.append((src, dst))
                    db.execute('UPDATE recycle_bin SET restored_at=? WHERE deletion_id=?',
                               (self.clock().isoformat(), deletion))
            except BaseException as error:
                try:
                    for src, dst in reversed(moved):
                        self._move(dst, src)
                except BaseException:
                    self.coordinator.ready = False
                    log.warning('RECYCLE_ROLLBACK_REQUIRED deletion_id=%s', deletion)
                    raise
                self.guard.deletion_event(deletion, 'RESTORE_ROLLBACK', batch['cube_id'], {'reason': 'TRANSACTION_FAILED'})
                if isinstance(error, sqlite3.IntegrityError):
                    raise failure('RESTORE_CONFLICT', '历史行与当前活跃数据存在约束冲突，恢复已整体回滚') from error
                raise
            self._clean_empty(self.paths.trash / deletion)
        self.guard.deletion_event(deletion, 'RESTORE', batch['cube_id'], {})
        return {'deletion_id': deletion, 'cube_id': batch['cube_id'], 'restored': True}

    def list(self):
        with self.registry.lock:
            return self._list()

    def _list(self):
        with connect_database(self.database) as db:
            rows = self._rows(db, 'recycle_bin')
            health = {r['deletion_id']: r['status'] for r in self._rows(db, 'recycle_health')}
            result = []
            for row in rows:
                if row['restored_at'] or row['purged_at']:
                    continue
                items = self._items(db, row['deletion_id'])
                payload = next((json.loads(i['row_json']) for i in items if i['table_name'] == 'dataset_registry'), None)
                from spectrumagent.api.registry import safe_name
                dataset = json.loads(payload['payload']) if payload else {}
                folder = self.paths.trash / row['deletion_id']
                size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()) if folder.is_dir() else 0
                result.append({'deletion_id': row['deletion_id'], 'cube_id': row['cube_id'],
                               'display_name': safe_name(dataset.get('name')), 'source_path': dataset.get('header_path', ''),
                               'created_at': row['created_at'], 'expires_at': row['expires_at'], 'total_bytes': size,
                               'status': health.get(row['deletion_id'], 'READY')})
        # Quarantined orphans still consume disk even though they are not restorable entries.
        occupied = sum(p.stat().st_size for p in self.paths.trash.rglob('*') if p.is_file())
        return {'items': result, 'count': len(result), 'total_bytes': occupied}

    def purge_expired(self):
        try:
            with self.coordinator.exclusive(), self.registry.lock:
                with connect_database(self.database) as db:
                    if any(r['status'] in ('pending', 'running') for t in ('preprocess_run', 'training_run', 'inference_run')
                           for r in self._rows(db, t)):
                        return []
                    batches = [r for r in self._rows(db, 'recycle_bin') if not r['restored_at'] and not r['purged_at']
                               and datetime.fromisoformat(r['expires_at']) <= self.clock()]
                purged = []
                for batch in batches:
                    deletion = batch['deletion_id']
                    with connect_database(self.database) as db:
                        if db.execute('SELECT 1 FROM recycle_health WHERE deletion_id=?', (deletion,)).fetchone():
                            continue
                        items = self._items(db, deletion)
                    try:
                        self._manifest(deletion, batch, items)
                    except DataError:
                        self._mark(deletion, batch['cube_id'], 'INCOMPLETE')
                        continue
                    with connect_database(self.database) as db:
                        db.execute('BEGIN IMMEDIATE')
                        storage.rmtree(self.paths.trash / deletion)
                        db.execute('DELETE FROM recycle_item WHERE deletion_id=?', (deletion,))
                        db.execute('DELETE FROM recycle_bin WHERE deletion_id=?', (deletion,))
                    self.guard.deletion_event(deletion, 'PURGE', batch['cube_id'], {})
                    purged.append(deletion)
                return purged
        except DataError as error:
            if error.code == 'DATASET_BUSY':
                return []
            raise

    def reconcile(self):
        with self.coordinator.exclusive(startup=True), self.registry.lock:
            self.guard.events.append('recycle_reconcile_started')
            with connect_database(self.database) as db:
                batches = {r['deletion_id']: r for r in self._rows(db, 'recycle_bin')}
            for folder in sorted(self.paths.trash.iterdir()):
                if folder.name == '_orphan' or not folder.is_dir():
                    continue
                deletion = folder.name
                try:
                    if str(UUID(deletion)) != deletion:
                        raise ValueError('non-canonical UUID')
                except ValueError:
                    deletion = str(uuid4())
                batch = batches.get(folder.name)
                with connect_database(self.database) as db:
                    items = self._items(db, folder.name)
                if batch and not batch['restored_at'] and not batch['purged_at']:
                    try:
                        self._manifest(folder.name, batch, items)
                    except DataError:
                        self._mark(folder.name, batch['cube_id'], 'INCOMPLETE')
                    continue
                try:
                    manifest = json.loads((folder / 'manifest.json').read_text('utf-8'))
                    cube = str(UUID(manifest['cube_id']))
                except (OSError, ValueError, KeyError, TypeError):
                    cube = batch['cube_id'] if batch else ''
                mappings = self._mapping(folder.name, cube, items) if items else []
                if mappings and cube:
                    for source, destination in reversed(mappings):
                        src, dst = self.paths.root.joinpath(*relative(destination).parts), self._owned(source, cube)
                        if src.exists():
                            self._move(src, dst)
                        elif not dst.exists():
                            raise failure('RECYCLE_INCOMPLETE', '孤立批次映射两端都缺失，已停止启动')
                    self._clean_empty(folder)
                    self.guard.deletion_event(deletion, 'ORPHAN_ROLLBACK', cube, {})
                else:
                    destination = self.paths.trash / '_orphan' / str(uuid4())
                    self._move(folder, destination)
                    self._mark(deletion, cube, 'ORPHAN_QUARANTINE')
                    self.guard.deletion_event(deletion, 'ORPHAN_QUARANTINE', cube, {})
            for deletion, batch in batches.items():
                if not batch['restored_at'] and not batch['purged_at'] and not (self.paths.trash / deletion).is_dir():
                    self._mark(deletion, batch['cube_id'], 'INCOMPLETE')
            with connect_database(self.database) as db:
                health = self._rows(db, 'recycle_health')
                self.coordinator.blocked = {r['cube_id'] for r in health if r['cube_id']}
                rows = self._rows(db, 'dataset_registry') + list(batches.values())
                self.coordinator.blocked_keys = {(r['header_key'], r['raw']) for r in rows
                                                 if r.get('cube_id', r.get('id')) in self.coordinator.blocked}
            self.coordinator.ready = True
            self.guard.events.append('recycle_business_ready')
