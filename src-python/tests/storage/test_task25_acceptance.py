"""D acceptance: real HTTP/SQLite/files, exhaustive reference scans and process restart.

Counterexamples deliberately seed undeclared references and immutable audit rows.
Only fresh pytest fixtures are mutated; production sources are never used.
"""
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from time import monotonic, sleep

from fastapi.testclient import TestClient
import pytest

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage
from spectrumagent.storage.recycle import TABLES


ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'src-python/spectrumagent/app.py').is_file())
spec = importlib.util.spec_from_file_location('task25_acceptance_fixture', ROOT / 'src-python/tests/storage/test_recycle.py')
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)
AUDIT_TABLES = ('llm_call', 'agent_round', 'agent_step', 'agent_plan_action')
INTENTIONAL_ARCHIVES = {*AUDIT_TABLES, 'recycle_bin', 'recycle_item', 'recycle_health'}
REFERENCE_PARENT = {'cube_id': 'dataset_registry', 'version_id': 'annotation_version',
                    'annotation_version_id': 'annotation_version', 'preprocess_run_id': 'preprocess_run',
                    'model_id': 'model_registry', 'cube_ids': 'dataset_registry',
                    'annotation_version_ids': 'annotation_version', 'preprocess_run_ids': 'preprocess_run'}


@pytest.fixture
def ledger(tmp_path):
    return fixture_module.case.__wrapped__(tmp_path)


def inventory(root):
    result = []
    for path in [root, *sorted(root.rglob('*'))]:
        stat = path.stat()
        result.append({'path': path.relative_to(root).as_posix(), 'type': 'file' if path.is_file() else 'directory',
                       'bytes': stat.st_size if path.is_file() else None, 'mtime_ns': stat.st_mtime_ns,
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None})
    return result


def table_rows(db, names):
    return {name: db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name in names}


def has_reference(value, removed):
    if isinstance(value, str):
        return any(identifier in value for identifier in removed)
    if isinstance(value, dict):
        return any(has_reference(key, removed) or has_reference(item, removed) for key, item in value.items())
    if isinstance(value, list):
        return any(has_reference(item, removed) for item in value)
    return False


def scan_business(db, removed=()):
    """Discover every current business table, not just the recycle TABLES list."""
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    parents = {name: {row[0] for row in db.execute(f'SELECT id FROM "{name}"')}
               for name in {*REFERENCE_PARENT.values(), 'training_run', 'inference_run'}}
    run_ids = parents['preprocess_run'] | parents['training_run'] | parents['inference_run']
    report = {'rows': {}, 'checked_reference_values': 0, 'findings': [], 'excluded_archives': sorted(INTENTIONAL_ARCHIVES),
              'foreign_key_check': db.execute('PRAGMA foreign_key_check').fetchall()}
    removed = set(removed)
    for table in tables:
        if table in INTENTIONAL_ARCHIVES:
            continue
        cursor = db.execute(f'SELECT * FROM "{table}"')
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        report['rows'][table] = len(rows)
        for row in rows:
            for column, value in zip(columns, row):
                if value is None:
                    continue
                if table == 'agent_session' and column == 'context_json':
                    if has_reference(json.loads(value), removed):
                        report['findings'].append([table, column, 'deleted reference in mutable context'])
                elif column == 'id' and value in removed:
                    report['findings'].append([table, column, 'deleted object remains active'])
                elif column in REFERENCE_PARENT or column == 'run_id':
                    targets = run_ids if column == 'run_id' else parents[REFERENCE_PARENT[column]]
                    try:
                        values = json.loads(value) if column.endswith('_ids') else [value]
                    except (TypeError, ValueError):
                        values = None
                    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
                        report['findings'].append([table, column, 'malformed reference list'])
                        continue
                    for item in values:
                        report['checked_reference_values'] += 1
                        if item in removed or item not in targets:
                            report['findings'].append([table, column, item])
    return report


def assert_clean(report):
    assert report['foreign_key_check'] == [], report
    assert report['findings'] == [], report


def seed_audit_history(c):
    with connect_database(c.paths.database) as db:
        db.execute("INSERT INTO agent_round (id,session_id,seq,user_message,calls_json,status,created_at,turn_id,assistant_content) "
                   "VALUES ('d-round','fixture-session',1,?,?,'done','fixture','d-turn','fixture')",
                   (f'历史数据 {c.cube}', json.dumps([{'name': 'datasets.describe', 'arguments': {'dataset_id': c.cube}}])))
        db.execute("INSERT INTO agent_step (id,session_id,round_id,seq,tool,arguments_json,result_digest,result_summary,status,latency_ms,created_at,tool_call_id) "
                   "VALUES ('d-step','fixture-session','d-round',1,'datasets.describe',?,'hash',?,'ok',1,'fixture','d-call')",
                   (json.dumps({'dataset_id': c.cube}), json.dumps({'cube_id': c.cube})))
        db.execute("INSERT INTO agent_plan_action VALUES ('d-action','fixture-session','d-round','reject',NULL,?,'fixture')", (c.cube,))
        db.execute("INSERT INTO llm_call (id,session_id,model,prompt_sha256,tool_names,prompt_tokens,completion_tokens,total_tokens,latency_ms,status,error,created_at,http_status,error_stage) "
                   "VALUES ('d-llm','fixture-session','synthetic',?,'[]',NULL,NULL,NULL,1,'ok',NULL,'fixture',200,NULL)",
                   (hashlib.sha256(c.cube.encode()).hexdigest(),))
        context = json.loads(db.execute("SELECT context_json FROM agent_session WHERE id='fixture-session'").fetchone()[0])
        context['nested_runs'] = [c.ids[name] for name in ('preprocess', 'training', 'inference')]
        db.execute("UPDATE agent_session SET context_json=? WHERE id='fixture-session'", (json.dumps(context),))
        return table_rows(db, AUDIT_TABLES)


def test_http_lifecycle_preserves_sources_audits_assets_and_has_no_business_orphans(ledger):
    """Red on lost rows/files, dangling JSON refs, changed audits, source writes or early purge."""
    c, identity = ledger, EngineIdentity()
    app = create_app(c.paths, identity)
    store, source_before = app.state.recycle, inventory(c.source)
    removed = {c.cube, *c.ids.values()}
    audits_before = seed_audit_history(c)
    protected_tables = (*c.assets, 'skill_version', 'project_path_settings')
    scans, phases, denied = {}, {'before': source_before}, []
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer ' + identity.token
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            assert response.status_code == 200, (path, response.text)
            assert response.headers['X-SpectrumAgent-Boot-Id'] == identity.boot_id
            assert response.headers['X-SpectrumAgent-Pid'] == str(identity.pid)
            return response.json()
        project = request('GET', '/api/v1/projects')[0]['id']
        settings_path = f'/api/v1/settings/projects/{project}/paths'
        settings = request('PUT', settings_path, json={'source_path': str(c.source), 'output_root': r'\\unreachable-d-fixture\future-output'})
        assert settings['output_enabled'] is False and settings['data_root'] == str(c.paths.root)
        with connect_database(c.paths.database) as db:
            protected = table_rows(db, protected_tables)
            scans['before'] = scan_business(db)
        assert_clean(scans['before'])
        for action in (lambda: storage.resolve_write(c.header, kind='D_SOURCE_WRITE').write_text('must be denied', 'utf-8'),
                       lambda: storage.unlink(c.header)):
            with pytest.raises(DataError) as error:
                action()
            assert error.value.code == 'WRITE_TO_SOURCE_DENIED'
            denied.append(error.value.code)
        assert inventory(c.source) == source_before
        delete_path = f'/api/v1/datasets/{c.cube}/delete'
        preview = request('GET', delete_path + '/preview')
        assert [preview[key] for key in ('annotation_versions', 'preprocess_runs', 'training_runs', 'inference_runs')] == [1, 1, 1, 1]
        owned = {item['path']: [entry for entry in inventory(c.paths.root / item['path']) if entry['type'] == 'file']
                 for item in preview['directories']}
        with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
            audit_prefix = table_rows(db, ('write_audit', 'deletion_audit'))
        deletion = request('POST', delete_path, json={'confirm': True, 'preview_token': preview['preview_token']})
        folder = c.paths.trash / deletion['deletion_id']
        for relative, expected in owned.items():
            assert not (c.paths.root / relative).exists()
            assert [entry for entry in inventory(folder / relative) if entry['type'] == 'file'] == expected
        assert (folder / f'annotations/{c.cube}/v1/annotation.json').is_file()
        assert (c.paths.snapshots / c.cube / 'unreferenced/keep.json').is_file()
        with connect_database(c.paths.database) as db:
            assert all(count == 0 for count in (db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES))
            scans['after_delete'] = scan_business(db, removed)
            assert table_rows(db, AUDIT_TABLES) == audits_before
            assert table_rows(db, protected_tables) == protected
            assert c.cube in str(audits_before['agent_step'])  # Audit reference is intentionally retained.
            context = db.execute("SELECT context_json FROM agent_session WHERE id='fixture-session'").fetchone()[0]
            assert not has_reference(json.loads(context), removed)
        assert_clean(scans['after_delete'])
        phases['after_delete'] = inventory(c.source)
        assert request('GET', '/api/v1/datasets/catalog')['total'] == 0
        occupied = sum(path.stat().st_size for path in c.paths.trash.rglob('*') if path.is_file())
        assert request('GET', '/api/v1/recycle')['total_bytes'] == occupied
        assert occupied > preview['total_bytes']  # The signed recovery manifest also occupies disk.
        restored = request('POST', f'/api/v1/recycle/{deletion["deletion_id"]}/restore', json={'confirm': True})
        assert restored['cube_id'] == c.cube
        with connect_database(c.paths.database) as db:
            assert table_rows(db, TABLES) == c.original
            assert table_rows(db, AUDIT_TABLES) == audits_before
            assert table_rows(db, protected_tables) == protected
            scans['after_restore'] = scan_business(db)
        assert_clean(scans['after_restore'])
        for relative, expected in owned.items():
            assert [entry for entry in inventory(c.paths.root / relative) if entry['type'] == 'file'] == expected
        phases['after_restore'] = inventory(c.source)
        assert not folder.exists()
        assert request('GET', settings_path) == settings
        preview = request('GET', delete_path + '/preview')
        second = request('POST', delete_path, json={'confirm': True, 'preview_token': preview['preview_token']})
        assert store.purge_expired() == []
        assert (c.paths.trash / second['deletion_id']).is_dir()
        future = store.clock() + timedelta(days=31)
        store.clock = lambda: future
        assert store.purge_expired() == [second['deletion_id']]
        assert not (c.paths.trash / second['deletion_id']).exists()
        with connect_database(c.paths.database) as db:
            scans['after_purge'] = scan_business(db, removed)
            assert table_rows(db, AUDIT_TABLES) == audits_before
            assert table_rows(db, protected_tables) == protected
            assert db.execute('SELECT count(*) FROM recycle_item WHERE deletion_id=?', (second['deletion_id'],)).fetchone()[0] == 0
        assert_clean(scans['after_purge'])
        phases['after_purge'] = inventory(c.source)
    assert all(value == source_before for value in phases.values())
    with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
        for table, before in audit_prefix.items():
            after = db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
            assert after[:len(before)] == before
            for sql in (f'UPDATE {table} SET action=action', f'DELETE FROM {table}'):
                with pytest.raises(sqlite3.IntegrityError, match='APPEND_ONLY_AUDIT'):
                    db.execute(sql)
                db.rollback()
        audit_actions = dict(db.execute('SELECT action,count(*) FROM deletion_audit GROUP BY action'))
        assert audit_actions['DELETE'] == 2 and audit_actions['RESTORE'] == 1 and audit_actions['PURGE'] == 1
        source_denials = db.execute("SELECT action,decision,reason FROM write_audit WHERE decision='DENY' AND target_path=?", (str(c.header.resolve()),)).fetchall()
        assert {row[0] for row in source_denials} == {'D_SOURCE_WRITE', 'DELETE'}
    assert (c.paths.root / 'projects' / project / 'projection.json').is_file()
    print('D_ACCEPTANCE_LIFECYCLE=' + json.dumps({'mode': 'authenticated TestClient + real SQLite/FK + guarded moves + server-clock expiry',
        'cube_id': c.cube, 'source_phases': phases, 'source_unchanged': True, 'scans': scans,
        'audit_actions': audit_actions, 'source_denials': source_denials, 'restore_same_id': restored['cube_id'] == c.cube,
        'protected_project_paths': True, 'immutable_audit_history_preserved': True}, ensure_ascii=False))


@pytest.mark.parametrize('column', ['cube_id', 'version_id', 'run_id', 'cube_ids'])
def test_orphan_scan_detects_undeclared_references_outside_known_recycle_tables(ledger, column):
    """Red if the acceptance scanner merely trusts FK checks or the fixed delete table list."""
    c = ledger
    with connect_database(c.paths.database) as db:
        db.execute('CREATE TABLE d_reference_probe (id TEXT PRIMARY KEY, cube_id TEXT, version_id TEXT, run_id TEXT, cube_ids TEXT)')
        value = json.dumps(['missing-object']) if column.endswith('_ids') else 'missing-object'
        db.execute(f'INSERT INTO d_reference_probe (id,{column}) VALUES (?,?)', ('probe', value))
        report = scan_business(db)
    assert report['foreign_key_check'] == []  # This defect deliberately has no declared FK.
    assert ['d_reference_probe', column, 'missing-object'] in report['findings']
    print('D_ORPHAN_COUNTEREXAMPLE=' + json.dumps({'column': column, 'sqlite_fk_check': [], 'detected': report['findings']}))


@pytest.mark.parametrize('recovery', ['unmapped_kill', 'mapped_rollback'])
def test_fresh_engine_startup_recovers_both_orphan_windows_and_gates_writes(ledger, recovery):
    """Red if a new interpreter loses products, skips reconciliation or admits blocked work."""
    c = ledger
    source_before = inventory(c.source)
    roots = ('annotations', 'exports', 'preprocessed', 'models', 'inferences', 'projects')
    products = {name: [entry for entry in inventory(c.paths.root / name) if entry['type'] == 'file'] for name in roots}
    killed_returncode = None
    if recovery == 'unmapped_kill':
        child = r'''
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src-python'))
tempfile.tempdir = sys.argv[3]
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.storage import guard as storage
registry = DatasetRegistry(Path(sys.argv[1]))
preview = registry.recycle.preview(sys.argv[2])
original = storage.replace
def pause_after_real_move(src, dst):
    original(src, dst)
    storage.resolve_write(Path(sys.argv[4]), kind='FAULT_SIGNAL').write_text('moved', 'utf-8')
    while True:
        time.sleep(.01)
storage.replace = pause_after_real_move
registry.recycle.delete(sys.argv[2], confirm=True, preview_token=preview['preview_token'])
'''
        marker = c.paths.run / 'd-moved'
        process = subprocess.Popen([sys.executable, '-c', child, str(c.paths.database), c.cube,
                                    tempfile.gettempdir(), str(marker)], cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = monotonic() + 30
            while not marker.exists() and process.poll() is None and monotonic() < deadline:
                sleep(.01)
            assert marker.exists(), 'child never reached the uncommitted real-move window'
            process.kill()  # Real process termination; no exception/finally-based compensation.
            _, stderr = process.communicate(timeout=10)
            killed_returncode = process.returncode
            assert killed_returncode != 0, stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
        with connect_database(c.paths.database) as db:
            assert db.execute('SELECT count(*) FROM recycle_bin').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM recycle_item').fetchone()[0] == 0
    else:
        # Durable mapping-journal counterexample, not a second actual-kill claim.
        deletion = fixture_module.deleted(c)['deletion_id']
        with connect_database(c.paths.database) as db:
            db.execute('DELETE FROM recycle_bin WHERE deletion_id=?', (deletion,))
            for table in reversed(TABLES):
                for row in c.original[table]:
                    db.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in row)})', row)
    with connect_database(c.paths.database) as db:
        assert table_rows(db, TABLES) == c.original
    # The parent deliberately never calls reconcile(). A fresh engine must do it.
    startup = r'''
import json, sqlite3, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src-python'))
tempfile.tempdir = sys.argv[3]
from fastapi.testclient import TestClient
from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app
from spectrumagent.data import DataError
paths, identity = AppPaths(Path(sys.argv[1])), EngineIdentity()
app = create_app(paths, identity)
registry, store = app.state.dataset_registry, app.state.recycle
assert store.coordinator.ready
events = registry.storage_guard.events
assert events.index('directories_created') < events.index('self_check') < events.index('recycle_reconcile_started') < events.index('recycle_business_ready')
gates = {}
with TestClient(app) as client:
    client.headers['Authorization'] = 'Bearer ' + identity.token
    # Explicit gate injection after construction; requests exercise actual middleware/auth.
    store.coordinator.ready = False
    try:
        for operation, path, body in [
            ('import', '/api/v1/datasets/import', {'path': sys.argv[4], 'raw': True, 'confirm_new': True}),
            ('annotation', f'/api/v1/datasets/{sys.argv[2]}/annotations/save', {}),
            ('training', '/api/v1/models/runs/preflight', {}),
            ('delete', f'/api/v1/datasets/{sys.argv[2]}/delete', {'confirm': True, 'preview_token': 'blocked'}),
        ]:
            response = client.post(path, json=body)
            assert response.status_code == 503, (operation, response.text)
            assert response.json()['error'] == 'RECYCLE_RECONCILIATION_REQUIRED'
            assert response.headers['X-SpectrumAgent-Boot-Id'] == identity.boot_id
            assert response.headers['X-SpectrumAgent-Pid'] == str(identity.pid)
            gates[operation] = {'status': response.status_code, 'error': response.json()['error']}
    finally:
        store.coordinator.ready = True
blocked = {}
if sys.argv[5] == 'unmapped_kill':
    for operation, callback in [
        ('get', lambda: registry.get(sys.argv[2])),
        ('import', lambda: registry.import_path(sys.argv[4], raw=True, confirm_new=True)),
        ('preview', lambda: store.preview(sys.argv[2])),
        ('delete', lambda: store.delete(sys.argv[2], confirm=True, preview_token='blocked')),
    ]:
        try:
            callback()
        except DataError as error:
            assert error.code == 'RECYCLE_RECONCILIATION_REQUIRED' and error.status_code == 503
            blocked[operation] = {'status': error.status_code, 'error': error.code}
        else:
            raise AssertionError(operation + ' admitted a quarantined cube')
    assert sys.argv[2] in store.coordinator.blocked and store.coordinator.blocked_keys
else:
    assert not store.coordinator.blocked
    assert str(registry.record(sys.argv[2]).id) == sys.argv[2]
with connect_database(paths.database) as db:
    health = db.execute('SELECT cube_id,status FROM recycle_health').fetchall()
with sqlite3.connect(registry.storage_guard.audit_database) as db:
    actions = dict(db.execute('SELECT action,count(*) FROM deletion_audit GROUP BY action'))
print('D_FRESH_ENGINE=' + json.dumps({'events': events, 'ready_gate_injection': gates,
    'post_quarantine_blocks': blocked, 'blocked_cubes': sorted(store.coordinator.blocked),
    'blocked_key_count': len(store.coordinator.blocked_keys), 'health': health, 'audit_actions': actions}))
registry.storage_guard.close()
'''
    restarted = subprocess.run([sys.executable, '-c', startup, str(c.paths.root), c.cube,
                                tempfile.gettempdir(), str(c.header), recovery], cwd=ROOT,
                               capture_output=True, text=True, timeout=60)
    assert restarted.returncode == 0, restarted.stdout + restarted.stderr
    result = json.loads(next(line.removeprefix('D_FRESH_ENGINE=') for line in restarted.stdout.splitlines()
                             if line.startswith('D_FRESH_ENGINE=')))
    orphan_folders = list((c.paths.trash / '_orphan').iterdir()) if (c.paths.trash / '_orphan').exists() else []
    if recovery == 'unmapped_kill':
        assert len(orphan_folders) == 1
        assert result['audit_actions']['ORPHAN_QUARANTINE'] == 1
        assert result['health'] == [[c.cube, 'ORPHAN_QUARANTINE']]
        assert result['blocked_cubes'] == [c.cube]
    else:
        assert orphan_folders == [] and not (c.paths.trash / deletion).exists()
        assert result['audit_actions']['ORPHAN_ROLLBACK'] == 1
        assert result['health'] == []
    for name, entries in products.items():
        for entry in entries:
            target = c.paths.root / name / entry['path']
            if not target.is_file():
                assert recovery == 'unmapped_kill'
                target = orphan_folders[0] / name / entry['path']
            assert target.stat().st_mtime_ns == entry['mtime_ns']
            assert hashlib.sha256(target.read_bytes()).hexdigest() == entry['sha256']
    with connect_database(c.paths.database) as db:
        assert table_rows(db, TABLES) == c.original
        assert_clean(scan_business(db))
    assert inventory(c.source) == source_before
    print('D_ACCEPTANCE_RECOVERY=' + json.dumps({'mode': recovery, 'actual_killed_process_returncode': killed_returncode,
        'fresh_interpreter': True, 'source_unchanged': True, 'all_product_files_preserved': True,
        'business_rows_unchanged': True, **result}, ensure_ascii=False))
