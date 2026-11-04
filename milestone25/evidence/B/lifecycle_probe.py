"""Reproduce B lifecycle evidence with a fresh synthetic ledger, never user data."""
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python'), str(ROOT / 'src-python/tests/fixtures')]

from fastapi.testclient import TestClient
from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage
from spectrumagent.storage.recycle import TABLES

spec = importlib.util.spec_from_file_location('recycle_fixtures', ROOT / 'src-python/tests/storage/test_recycle.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)
base = ROOT / '.runtime/task25' / ('b-lifecycle-' + uuid4().hex[:10])
base.mkdir(parents=True)
c = fixture_module.case.__wrapped__(base / 'fixture')


def source_inventory():
    return [{'path': p.relative_to(c.source).as_posix(), 'bytes': p.stat().st_size,
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'mtime_ns': p.stat().st_mtime_ns}
            for p in sorted(c.source.rglob('*')) if p.is_file()]


def counts():
    with connect_database(c.paths.database) as db:
        return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in TABLES}


before = source_inventory()
phases = {'before': before}
preview = c.store.preview(c.cube)
deleted = c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
phases['after_delete'] = source_inventory()
deleted_counts = counts()
assert all(value == 0 for value in deleted_counts.values())
assert (c.paths.trash / deleted['deletion_id']).is_dir()
restored = c.store.restore(deleted['deletion_id'], confirm=True)
phases['after_restore'] = source_inventory()
restored_counts = counts()
assert restored['cube_id'] == c.cube
with connect_database(c.paths.database) as db:
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    for table in TABLES:
        assert db.execute(f'SELECT * FROM {table}').fetchall() == c.original[table]
second = c.store.preview(c.cube)
second_deleted = c.store.delete(c.cube, confirm=True, preview_token=second['preview_token'])
assert c.store.purge_expired() == []
future = c.store.clock() + timedelta(days=31)
c.store.clock = lambda: future
purged = c.store.purge_expired()
assert purged == [second_deleted['deletion_id']]
phases['after_purge'] = source_inventory()
assert all(inventory == before for inventory in phases.values())

denied = []
for action in (lambda: storage.resolve_write(c.header, kind='SOURCE_WRITE_PROBE'),
               lambda: storage.resolve_delete(c.header)):
    try:
        action()
    except DataError as error:
        assert error.code == 'WRITE_TO_SOURCE_DENIED'
        denied.append(error.code)
    else:
        raise AssertionError('source mutation was authorized')
assert source_inventory() == before

identity = EngineIdentity()
app = create_app(c.paths, identity)
gate = {}
with TestClient(app) as client:
    client.headers['Authorization'] = 'Bearer ' + identity.token
    listed = client.get('/api/v1/recycle')
    assert listed.status_code == 200
    assert listed.headers['X-SpectrumAgent-Boot-Id'] == identity.boot_id
    assert listed.headers['X-SpectrumAgent-Pid'] == str(identity.pid)
    app.state.recycle.coordinator.ready = False
    try:
        for operation, path, body in [
            ('import', '/api/v1/datasets/import', {'path': str(c.header), 'raw': True, 'confirm_new': True}),
            ('annotation', f'/api/v1/datasets/{c.cube}/annotations/save', {}),
            ('training', '/api/v1/models/runs/preflight', {}),
            ('delete', f'/api/v1/datasets/{c.cube}/delete', {'confirm': True, 'preview_token': 'blocked'}),
        ]:
            response = client.post(path, json=body)
            assert response.status_code == 503, (operation, response.text)
            assert response.json()['error'] == 'RECYCLE_RECONCILIATION_REQUIRED'
            assert response.headers['X-SpectrumAgent-Boot-Id'] == identity.boot_id
            assert response.headers['X-SpectrumAgent-Pid'] == str(identity.pid)
            gate[operation] = {'status': response.status_code, 'error': response.json()['error']}
    finally:
        app.state.recycle.coordinator.ready = True

with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
    actions = dict(db.execute('SELECT action,COUNT(*) FROM deletion_audit GROUP BY action'))
    source_denials = db.execute("SELECT action,decision,reason FROM write_audit WHERE decision='DENY' "
                               "AND reason='WRITE_TO_SOURCE_DENIED'").fetchall()
assert actions['DELETE'] == 2 and actions['RESTORE'] == 1 and actions['PURGE'] == 1
assert len(source_denials) == 2
print(json.dumps({'mode': 'fresh synthetic ENVI + real SQLite/FK + guarded filesystem + authenticated TestClient',
                  'runtime_root': str(base), 'cube_id': c.cube, 'impact': {k: v for k, v in preview.items()
                  if k not in ('preview_token', 'expires_at')}, 'source_phases': phases,
                  'source_unchanged': True, 'active_counts_after_delete': deleted_counts,
                  'active_counts_after_restore': restored_counts, 'restored_id_unchanged': restored['cube_id'] == c.cube,
                  'purged': purged, 'deletion_audit': actions, 'source_denials': source_denials,
                  'startup_gate': gate}, ensure_ascii=False, indent=2))
for guard in storage._guards.values():
    guard.close()
