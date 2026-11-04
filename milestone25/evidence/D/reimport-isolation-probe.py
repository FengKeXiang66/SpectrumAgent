"""D reimport acceptance: every business ledger stays empty for the new id."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python'), str(ROOT / 'src-python/tests/fixtures')]
from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage
from spectrumagent.storage.recycle import TABLES

spec = importlib.util.spec_from_file_location('d_acceptance_helpers', ROOT / 'src-python/tests/storage/test_task25_acceptance.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
base = ROOT / '.runtime/task25' / ('d-isolation-' + uuid4().hex[:8])
base.mkdir(parents=True)
c = helpers.fixture_module.case.__wrapped__(base / 'fixture')
source_before = helpers.inventory(c.source)
preview = c.store.preview(c.cube)
deleted = c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
try:
    c.registry.import_path(str(c.header), raw=True)
except DataError as error:
    assert error.code == 'REIMPORT_CONFIRMATION_REQUIRED' and error.status_code == 409
    confirmation_error = {'status': error.status_code, 'error': error.code}
else:
    raise AssertionError('unconfirmed reimport succeeded')
fresh = c.registry.import_path(str(c.header), raw=True, confirm_new=True)
new_id = str(fresh.datasets[0].id)
assert new_id != c.cube and fresh.datasets[0].existing is False
assert fresh.summary.model_dump() == {'total': 1, 'imported': 1, 'existing': 0}
with connect_database(c.paths.database) as db:
    counts = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}
    assert counts['dataset_registry'] == 1
    assert all(counts[table] == 0 for table in TABLES if table != 'dataset_registry')
    assert db.execute('SELECT id FROM dataset_registry').fetchall() == [(new_id,)]
    helpers.assert_clean(helpers.scan_business(db))
    context = json.loads(db.execute("SELECT context_json FROM agent_session WHERE id='fixture-session'").fetchone()[0])
    assert not helpers.has_reference(context, {c.cube, *c.ids.values()})
    recycled_rows = db.execute('SELECT table_name,count(*) FROM recycle_item WHERE deletion_id=? GROUP BY table_name', (deleted['deletion_id'],)).fetchall()
assert not (c.paths.snapshots / new_id).exists()
assert not (c.paths.exports / new_id).exists()
assert not (c.paths.preprocessed / new_id).exists()
assert all(not (c.paths.root / item['path']).exists() for item in preview['directories'])
assert (c.paths.trash / deleted['deletion_id'] / 'annotations' / c.cube / 'v1/annotation.json').is_file()
repeated = []
for confirmed in (False, True):
    result = c.registry.import_path(str(c.header), raw=True, confirm_new=confirmed)
    assert str(result.datasets[0].id) == new_id and result.datasets[0].existing is True
    assert result.summary.model_dump() == {'total': 1, 'imported': 0, 'existing': 1}
    repeated.append({'confirm_new': confirmed, 'id': new_id, 'existing': True, 'summary': result.summary.model_dump()})
try:
    c.store.restore(deleted['deletion_id'], confirm=True)
except DataError as error:
    assert error.code == 'RESTORE_CONFLICT' and error.status_code == 409
    conflict = {'status': error.status_code, 'error': error.code}
else:
    raise AssertionError('restore overwrote the active dataset')
with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
    denials = db.execute("SELECT action,cube_id FROM deletion_audit WHERE action='RESTORE_DENIED'").fetchall()
assert denials == [('RESTORE_DENIED', c.cube)]
assert helpers.inventory(c.source) == source_before
print(json.dumps({'authority': 'dfa67a7', 'mode': 'fresh synthetic ENVI + full dependent ledger / real SQLite + guarded filesystem',
    'old_id': c.cube, 'new_id': new_id, 'confirmation_required': confirmation_error,
    'confirmed_summary': fresh.summary.model_dump(), 'confirmed_existing': fresh.datasets[0].existing,
    'active_ledger_counts': counts, 'old_rows_retained_in_recycle': recycled_rows,
    'active_idempotency': repeated, 'restore_conflict': conflict, 'restore_denied_audit': denials,
    'new_id_has_no_old_annotations_versions_runs': True, 'source_unchanged': True}, ensure_ascii=False, indent=2))
for guard in storage._guards.values():
    guard.close()
