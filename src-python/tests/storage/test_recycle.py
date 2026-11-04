"""Real SQLite/FK/file lifecycle tests, including a killed child process."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.api.recycle import RecycleJobsMiddleware
from spectrumagent.app import create_app
from spectrumagent.data import DataError
from spectrumagent.preprocess.recipes import RecipeStore
from spectrumagent.storage import guard as storage
from spectrumagent.storage.recycle import FILE_ITEM, TABLES, encode, relative
from cubes import cube


@contextmanager
def error_code(code):
    with pytest.raises(DataError) as raised:
        yield raised
    assert raised.value.code == code


def files(root):
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'source'
    header, _, _ = cube(source)
    # Leave room for trash/<uuid>/exports/<cube>/<version>/training_mat.mat on
    # Windows hosts without long-path support; sources remain a separate sibling.
    paths = AppPaths(tmp_path.parent / ('rc-' + uuid4().hex[:8]))
    registry = DatasetRegistry(paths.database)
    identifier = str(registry.import_path(str(header), raw=True).datasets[0].id)
    RecipeStore(paths.database)
    ids = {key: str(uuid4()) for key in ('version', 'preprocess', 'training', 'model', 'inference')}
    version, preprocess, training, model, inference = (ids[key] for key in ids)
    with connect_database(paths.database) as db:
        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (identifier,)).fetchone()[0]
        label, schema = db.execute("SELECT id,schema_id FROM label WHERE code='PE'").fetchone()
        recipe = db.execute('SELECT id FROM preprocess_recipe_version').fetchone()[0]
        db.execute('INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) '
                   "VALUES (?,?,1,?,6,4,'{}','fixture')", (version, identifier, f'{identifier}/v1'))
        db.execute('INSERT INTO annotation (id,cube_id,version_id,granularity,label_id,pixel_count,created_at) '
                   "VALUES (?,?,?,'sample',?,4,'fixture')", (str(uuid4()), identifier, version, label))
        db.execute('INSERT INTO sample_spectrum (id,cube_id,version_id,label_id,sample_code,n_pixels,mean_ref,std_ref,created_at) '
                   "VALUES (?,?,?,?,'fixture',4,'mean','std','fixture')", (str(uuid4()), identifier, version, label))
        db.execute("INSERT INTO annotation_draft VALUES (?,2,'{}',1,1,'fixture')", (identifier,))
        db.execute('INSERT INTO training_mat VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (str(uuid4()), identifier, version, f'{identifier}/{version}/training_mat.mat', 'hash', 4, 4, 2, 'hash', 'fixture'))
        db.execute('INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,input_fingerprint,status,created_at) '
                   "VALUES (?,?,?,?,'passthrough','hash','succeeded','fixture')", (preprocess, identifier, version, recipe))
        db.execute("INSERT INTO preprocess_artifact VALUES (?,?,'report',?,'hash','fixture')",
                   (str(uuid4()), preprocess, f'{identifier}/{preprocess}/report.json'))
        db.execute('INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,cv_folds,seed,status,created_at) '
                   "VALUES (?,?,?,?,'classification','label','random',2,17,'succeeded','fixture')",
                   (training, json.dumps([identifier]), json.dumps([version]), json.dumps([preprocess])))
        db.execute("INSERT INTO training_fold VALUES (?,?,0,2,2,'[0]','[0]')", (str(uuid4()), training))
        db.execute("INSERT INTO metric VALUES (?,?,0,'sample','oa',0.9,'fixture')", (str(uuid4()), training))
        db.execute("INSERT INTO model_artifact VALUES (?,?,'model',?,'hash','fixture')",
                   (str(uuid4()), training, f'models/{training}/model.json'))
        db.execute('INSERT INTO model_registry (id,run_id,name,version,target_schema_id,data_fingerprint,applicability,calibration,created_at) '
                   "VALUES (?,?,'fixture',1,?,'hash','{}','{}','fixture')", (model, training, schema))
        db.execute("INSERT INTO sample_target VALUES (?,?,?,?,1.5,'import','fixture')",
                   (str(uuid4()), project, identifier, schema))
        db.execute('INSERT INTO inference_run (id,model_id,cube_id,preprocess_run_id,annotation_version_id,status,created_at) '
                   "VALUES (?,?,?,?,?,'succeeded','fixture')", (inference, model, identifier, preprocess, version))
        db.execute("INSERT INTO inference_artifact VALUES (?,?,'map',?,'hash','fixture')",
                   (str(uuid4()), inference, f'inferences/{inference}/map.png'))
        db.execute("INSERT INTO skill_version (id,version_no,name,system_prompt,tools_json,examples_json,status,created_at) "
                   "VALUES ('fixture-skill',99,'fixture','fixture','[]','[]','draft','fixture')")
        context = {'selected_cube_id': identifier, 'annotation_version_id': version, 'keep': 'other',
                   'catalogs': {'dataset': {'items': [{'id': identifier}, {'id': 'other'}]}}}
        db.execute("INSERT INTO agent_session (id,skill_version_id,created_at,updated_at,context_json) "
                   "VALUES ('fixture-session','fixture-skill','fixture','fixture',?)", (encode(context),))
        original = {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in TABLES}
        assets = {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in
                  ('project', 'label_schema', 'label', 'preprocess_recipe', 'preprocess_recipe_version', 'project_recipe')}
    for name in (f'annotations/{identifier}/v1/annotation.json', f'annotations/{identifier}/v1/label_index.json',
                 f'annotations/{identifier}/v1/label_map.npz', f'annotations/{identifier}/v1/spectra.npz',
                 f'exports/{identifier}/sample.json', f'exports/{identifier}/sample.meta.json',
                 f'exports/{identifier}/manifest.json', f'exports/{identifier}/{version}/training_mat.mat',
                 f'preprocessed/{identifier}/{preprocess}/report.json', f'models/{training}/model.json',
                 f'inferences/{inference}/map.png', f'projects/{project}/projection.json',
                 f'annotations/{identifier}/unreferenced/keep.json'):
        path = paths.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    return SimpleNamespace(paths=paths, registry=registry, store=registry.recycle, cube=identifier,
                           source=source, header=header, ids=ids, original=original, assets=assets)


def deleted(c):
    preview = c.store.preview(c.cube)
    return c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])


def audit(c, action):
    with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
        return db.execute('SELECT cube_id,summary_json FROM deletion_audit WHERE action=?', (action,)).fetchall()


def test_full_delete_restore(case):
    c = case
    source_before = files(c.source)
    product_before = files(c.paths.root / 'annotations')
    projects_before = files(c.paths.root / 'projects')
    preview = c.store.preview(c.cube)
    assert [preview[k] for k in ('annotation_versions', 'preprocess_runs', 'training_runs', 'inference_runs')] == [1, 1, 1, 1]
    assert preview['total_bytes'] > 0
    result = c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
    deletion = result['deletion_id']
    assert (datetime.fromisoformat(result['expires_at']) - c.store.clock()).days == 29
    with connect_database(c.paths.database) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for table in TABLES:
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0, table
        context = db.execute("SELECT context_json FROM agent_session WHERE id='fixture-session'").fetchone()[0]
        assert c.cube not in context and c.ids['version'] not in context
        assert json.loads(context)['keep'] == 'other'
        for table, original in c.assets.items():
            assert db.execute(f'SELECT * FROM {table}').fetchall() == original
        items = c.store._items(db, deletion)
        assert {i['table_name'] for i in items} == {*TABLES, FILE_ITEM}
        for item in items:
            if item['file_src']:
                assert relative(item['file_src']) and relative(item['file_dst'])
    assert (c.paths.root / f'annotations/{c.cube}/unreferenced/keep.json').is_file()
    assert not (c.paths.snapshots / c.cube / 'v1').exists()
    assert (c.paths.trash / deletion / f'annotations/{c.cube}/v1/annotation.json').is_file()
    assert list(c.paths.root.glob('projects/*/projection.json'))
    c.store.reconcile()  # A valid batch must survive a real startup inventory/hash check.
    assert c.store.list()['items'][0]['status'] == 'READY'
    assert c.store.restore(deletion, confirm=True)['cube_id'] == c.cube
    with connect_database(c.paths.database) as db:
        for table in TABLES:
            assert db.execute(f'SELECT * FROM {table}').fetchall() == c.original[table], table
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert files(c.source) == source_before
    assert files(c.paths.root / 'projects') == projects_before
    assert files(c.paths.root / 'annotations') == product_before
    assert not (c.paths.trash / deletion).exists()
    assert c.store.list()['count'] == 0
    assert audit(c, 'DELETE') and audit(c, 'RESTORE')


def test_reimport_and_conflict(case):
    c = case
    deletion = deleted(c)['deletion_id']
    with error_code('REIMPORT_CONFIRMATION_REQUIRED') as raised:
        c.registry.import_path(str(c.header), raw=True)
    assert raised.value.status_code == 409
    fresh = str(c.registry.import_path(str(c.header), raw=True, confirm_new=True).datasets[0].id)
    assert fresh != c.cube
    with connect_database(c.paths.database) as db:
        for table in ('annotation_version', 'annotation_draft', 'preprocess_run', 'sample_target'):
            assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE cube_id=?', (fresh,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM training_run').fetchone()[0] == 0
    with error_code('RESTORE_CONFLICT'):
        c.store.restore(deletion, confirm=True)
    assert audit(c, 'RESTORE_DENIED')
    preview = c.store.preview(fresh)
    c.store.delete(fresh, confirm=True, preview_token=preview['preview_token'])
    assert c.store.restore(deletion, confirm=True)['cube_id'] == c.cube


@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('recycled', [False, True])
@pytest.mark.parametrize('confirmed', [False, True])
def test_reimport_quadrants(case, active, recycled, confirmed):
    c = case
    header, expected_id = c.header, c.cube
    if recycled:
        deleted(c)
        if active:
            expected_id = str(c.registry.import_path(str(header), raw=True, confirm_new=True).datasets[0].id)
    elif not active:
        header = cube(c.source / 'first-import')[0]
        expected_id = None
    if not active and recycled and not confirmed:
        with error_code('REIMPORT_CONFIRMATION_REQUIRED') as raised:
            c.registry.import_path(str(header), raw=True)
        assert raised.value.status_code == 409
        assert all(text in str(raised.value) for text in ('新建 id', '从头标注', '30 天', '双份'))
        return
    result = c.registry.import_path(str(header), raw=True, confirm_new=confirmed)
    record = result.datasets[0]
    assert record.existing is active
    assert result.summary.model_dump() == {'total': 1, 'imported': int(not active), 'existing': int(active)}
    if active:
        assert str(record.id) == expected_id
    else:
        assert str(record.id) != c.cube


def test_reimport_confirmed_race(case, monkeypatch):
    c = case
    deleted(c)
    other = DatasetRegistry(c.paths.database)
    barrier = Barrier(2)
    for registry in (c.registry, other):
        original = registry._import_preflight
        def synchronized(*args, _original=original):
            decision = _original(*args)
            barrier.wait(timeout=10)  # Both real read transactions have already ended.
            return decision
        monkeypatch.setattr(registry, '_import_preflight', synchronized)
    def import_one(registry):
        try:
            return registry.import_path(str(c.header), raw=True, confirm_new=True)
        except DataError as error:
            return error
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(import_one, (c.registry, other)))
    successes = [r for r in results if not isinstance(r, DataError)]
    failures = [r for r in results if isinstance(r, DataError)]
    assert len(successes) == len(failures) == 1
    assert successes[0].summary.imported == 1 and successes[0].datasets[0].existing is False
    assert failures[0].code == 'REIMPORT_ACTIVE_EXISTS' and failures[0].status_code == 409
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 1


def test_reimport_unique_is_structured(case, monkeypatch):
    c = case
    deleted(c)
    from spectrumagent.api import registry as registry_module
    original = registry_module.connect_database
    class Connection:
        def __init__(self, db):
            self.db = db
        def execute(self, statement, *args):
            if statement.startswith('INSERT INTO dataset_registry'):
                raise sqlite3.IntegrityError('UNIQUE constraint failed: dataset_registry.header_key, dataset_registry.raw')
            return self.db.execute(statement, *args)
    @contextmanager
    def connection(*args, **kwargs):
        with original(*args, **kwargs) as db:
            yield Connection(db)
    monkeypatch.setattr(registry_module, 'connect_database', connection)
    with error_code('REIMPORT_ACTIVE_EXISTS') as raised:
        c.registry.import_path(str(c.header), raw=True, confirm_new=True)
    assert raised.value.status_code == 409
    with original(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 0


def test_reimport_batch_is_atomic(case):
    c = case
    deleted(c)
    cube(c.source / 'new')
    with error_code('REIMPORT_CONFIRMATION_REQUIRED'):
        c.registry.import_path(str(c.source), raw=True)
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM recycle_bin').fetchone()[0] == 1
    result = c.registry.import_path(str(c.source), raw=True, confirm_new=True)
    assert result.summary.model_dump() == {'total': 2, 'imported': 2, 'existing': 0}


def test_reimport_key_includes_raw(case):
    c = case
    deleted(c)  # Only the raw=True key is recycled.
    reflected = c.registry.import_path(str(c.header), raw=False)
    assert reflected.summary.imported == 1 and reflected.datasets[0].existing is False
    with error_code('REIMPORT_CONFIRMATION_REQUIRED'):
        c.registry.import_path(str(c.header), raw=True)


def test_expiry_and_audit(case):
    c = case
    before = files(c.source)
    deletion = deleted(c)['deletion_id']
    assert c.store.purge_expired() == []
    future = c.store.clock() + timedelta(days=31)
    c.store.clock = lambda: future
    assert c.store.purge_expired() == [deletion]
    assert not (c.paths.trash / deletion).exists()
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM recycle_bin').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM recycle_item').fetchone()[0] == 0
    assert audit(c, 'PURGE')
    with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
        for sql in ('DELETE FROM deletion_audit', "UPDATE deletion_audit SET action='forged'"):
            with pytest.raises(sqlite3.IntegrityError, match='APPEND_ONLY_AUDIT'):
                db.execute(sql)
    assert files(c.source) == before


@pytest.mark.parametrize('mode', ['false', 'tampered', 'expired', 'changed'])
def test_preview_binding(case, mode):
    c = case
    before = files(c.source)
    token = c.store.preview(c.cube)['preview_token']
    confirm = mode != 'false'
    if mode == 'tampered':
        token += 'x'
    if mode == 'expired':
        future = c.store.clock() + timedelta(minutes=6)
        c.store.clock = lambda: future
    if mode == 'changed':
        (c.paths.exports / c.cube / 'sample.json').write_text('changed')
    with pytest.raises(DataError):
        c.store.delete(c.cube, confirm=confirm, preview_token=token)
    assert c.registry.get(c.cube)
    assert c.store.list()['count'] == 0
    assert files(c.source) == before


def test_move_failure_rolls_back(case, monkeypatch):
    c = case
    before = files(c.paths.root / 'annotations')
    original = storage.replace
    count = 0
    def fail_second(src, dst):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('injected move failure')
        return original(src, dst)
    monkeypatch.setattr(storage, 'replace', fail_second)
    with pytest.raises(OSError, match='injected'):
        deleted(c)
    with connect_database(c.paths.database) as db:
        for table in TABLES:
            assert db.execute(f'SELECT * FROM {table}').fetchall() == c.original[table]
    assert files(c.paths.root / 'annotations') == before
    assert c.store.list()['count'] == 0
    assert not list(c.paths.trash.iterdir())
    assert audit(c, 'DELETE_ROLLBACK')


def test_commit_failure_rolls_back(case, monkeypatch):
    c = case
    from spectrumagent.storage import recycle
    original_connect, original_move = recycle.connect_database, c.store._move
    connections = []
    @contextmanager
    def connection(*args, **kwargs):
        with original_connect(*args, **kwargs) as db:
            connections.append(db)
            try:
                yield db
            finally:
                connections.pop()
    injected = False
    def move(src, dst):
        nonlocal injected
        original_move(src, dst)
        if not injected:
            injected = True
            db = connections[-1]
            db.execute('PRAGMA defer_foreign_keys=ON')
            db.execute("INSERT INTO inference_artifact VALUES ('injected','missing-parent','map','map.png','hash','fixture')")
    monkeypatch.setattr(recycle, 'connect_database', connection)
    monkeypatch.setattr(c.store, '_move', move)
    before = files(c.paths.root / 'annotations')
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        deleted(c)
    with original_connect(c.paths.database) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for table in TABLES:
            assert db.execute(f'SELECT * FROM {table}').fetchall() == c.original[table]
        assert db.execute('SELECT COUNT(*) FROM recycle_bin').fetchone()[0] == 0
    assert files(c.paths.root / 'annotations') == before
    assert not list(c.paths.trash.iterdir())


def test_restore_move_failure(case, monkeypatch):
    c = case
    deletion = deleted(c)['deletion_id']
    before = files(c.paths.trash / deletion)
    original = c.store._move
    calls = 0
    def move(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('restore move injection')
        original(src, dst)
    monkeypatch.setattr(c.store, '_move', move)
    with pytest.raises(OSError, match='restore move injection'):
        c.store.restore(deletion, confirm=True)
    assert files(c.paths.trash / deletion) == before
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 0
        assert db.execute('SELECT restored_at FROM recycle_bin').fetchone()[0] is None
    assert audit(c, 'RESTORE_ROLLBACK')


def test_purge_waits_for_long_run(case):
    c = case
    deletion = deleted(c)['deletion_id']
    future = c.store.clock() + timedelta(days=31)
    c.store.clock = lambda: future
    with connect_database(c.paths.database) as db:
        db.execute('INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,cv_folds,seed,status,created_at) '
                   "VALUES ('busy','[]','[]','[]','classification','label','random',2,17,'running','fixture')")
    assert c.store.purge_expired() == []
    assert (c.paths.trash / deletion).exists()
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE training_run SET status='failed' WHERE id='busy'")
    assert c.store.purge_expired() == [deletion]


def test_multi_cube_fails_closed(case):
    c = case
    with connect_database(c.paths.database) as db:
        db.execute('UPDATE training_run SET cube_ids=?', (json.dumps([c.cube, str(uuid4())]),))
    with error_code('MULTI_CUBE_RUN'):
        c.store.preview(c.cube)
    assert c.registry.get(c.cube)
    assert c.store.list()['count'] == 0


@pytest.mark.parametrize('damage', ['missing', 'manifest', 'file'])
def test_incomplete_fail_closed(case, damage):
    c = case
    deletion = deleted(c)['deletion_id']
    folder = c.paths.trash / deletion
    if damage == 'missing':
        storage.rmtree(folder)
    elif damage == 'manifest':
        (folder / 'manifest.json').write_text('{}')
    else:
        next(p for p in folder.rglob('*') if p.name == 'annotation.json').write_bytes(b'corrupt')
    c.store.reconcile()
    assert c.store.list()['items'][0]['status'] == 'INCOMPLETE'
    with error_code('RECYCLE_INCOMPLETE'):
        c.store.restore(deletion, confirm=True)
    future = c.store.clock() + timedelta(days=31)
    c.store.clock = lambda: future
    assert c.store.purge_expired() == []


def test_orphan_mapping_rollback(case):
    c = case
    deletion = deleted(c)['deletion_id']
    with connect_database(c.paths.database) as db:
        db.execute('DELETE FROM recycle_bin WHERE deletion_id=?', (deletion,))
        # Simulate recovery of the business rows while the mapping journal survives.
        for table in reversed(TABLES):
            columns = [r[1] for r in db.execute(f'PRAGMA table_info({table})')]
            for row in c.original[table]:
                db.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})', row)
    c.store.reconcile()
    assert (c.paths.snapshots / c.cube / 'v1/annotation.json').is_file()
    assert not (c.paths.trash / deletion).exists()
    assert audit(c, 'ORPHAN_ROLLBACK')


def test_killed_move_is_quarantined(case):
    c = case
    source_before = files(c.source)
    before = {name: files(c.paths.root / name) for name in ('annotations', 'exports', 'preprocessed', 'models', 'inferences')}
    child = r'''
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src-python'))
tempfile.tempdir = sys.argv[3]
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.storage import guard as storage
r = DatasetRegistry(Path(sys.argv[1]))
p = r.recycle.preview(sys.argv[2])
original = storage.replace
def killed(src, dst):
    original(src, dst)
    storage.resolve_write(Path(sys.argv[4]), kind='FAULT_SIGNAL').write_text('moved', 'utf-8')
    while True:
        time.sleep(.01)
storage.replace = killed
r.recycle.delete(sys.argv[2], confirm=True, preview_token=p['preview_token'])
'''
    marker = c.paths.run / 'crash-moved'
    process = subprocess.Popen([sys.executable, '-c', child, str(c.paths.database), c.cube,
                                tempfile.gettempdir(), str(marker)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        deadline = monotonic() + 30
        while not marker.exists() and process.poll() is None and monotonic() < deadline:
            sleep(.01)
        assert marker.exists(), 'child did not reach the uncommitted move window'
        process.kill()  # Terminate the real process: no finally/atexit/SQLite commit.
        _, stderr = process.communicate(timeout=10)
        assert process.returncode != 0, stderr
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
    # SQLite rolls back uncommitted rows; no durable mapping means quarantine.
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM recycle_bin').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM recycle_item').fetchone()[0] == 0
        for table in TABLES:
            assert db.execute(f'SELECT * FROM {table}').fetchall() == c.original[table]
    c.store.reconcile()
    orphans = list((c.paths.trash / '_orphan').iterdir())
    assert len(orphans) == 1
    for root, entries in before.items():
        for path, expected in entries.items():
            actual = c.paths.root / root / path
            if not actual.exists():
                actual = orphans[0] / root / path
            assert (hashlib.sha256(actual.read_bytes()).hexdigest(), actual.stat().st_mtime_ns) == expected
    assert audit(c, 'ORPHAN_QUARANTINE')
    assert c.store.list()['total_bytes'] > 0
    assert files(c.source) == source_before
    with error_code('RECYCLE_RECONCILIATION_REQUIRED'):
        c.registry.get(c.cube)
    with error_code('RECYCLE_RECONCILIATION_REQUIRED'):
        c.registry.import_path(str(c.header), raw=True, confirm_new=True)


def test_busy_and_startup_gate(case):
    c = case
    preview = c.store.preview(c.cube)
    with c.store.coordinator.job():
        with error_code('DATASET_BUSY'):
            c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
        assert c.store.purge_expired() == []
    c.store.coordinator.ready = False
    for operation in (lambda: c.registry.get(c.cube), lambda: c.registry.import_path(str(c.header)),
                      lambda: c.store.preview(c.cube)):
        with error_code('RECYCLE_RECONCILIATION_REQUIRED'):
            operation()
    c.store.reconcile()
    assert c.registry.get(c.cube)
    assert c.registry.storage_guard.events.index('self_check') < c.registry.storage_guard.events.index('recycle_reconcile_started')


def test_stream_lease_until_body_end(case):
    c = case
    sent = []
    async def inner(scope, receive, send):
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        assert c.store.coordinator.active == 1
        await send({'type': 'http.response.body', 'body': b'event: started\n', 'more_body': True})
        with error_code('DATASET_BUSY'):
            with c.store.coordinator.exclusive():
                pytest.fail('deletion must stay blocked during streaming computation')
        await send({'type': 'http.response.body', 'body': b'event: done\n'})
    async def send(message):
        sent.append(message)
    middleware = RecycleJobsMiddleware(inner, coordinator=c.store.coordinator, token='fixture-token')
    asyncio.run(middleware({'type': 'http', 'path': '/api/v1/agent/sessions/id/messages',
                            'headers': [(b'authorization', b'Bearer fixture-token')]}, None, send))
    assert len(sent) == 3 and c.store.coordinator.active == 0


def test_http_contract_and_catalog(tmp_path):
    source = tmp_path / 'source'
    header, data, _ = cube(source)
    paths = AppPaths(tmp_path.parent / ('rc-' + uuid4().hex[:8]))
    identity = EngineIdentity()
    app = create_app(paths, identity)
    with TestClient(app) as client:
        assert client.get('/api/v1/recycle').status_code == 401
        client.headers['Authorization'] = 'Bearer ' + identity.token
        imported = client.post('/api/v1/datasets/import', json={'path': str(header), 'raw': True}).json()
        identifier = imported['datasets'][0]['id']
        response = client.get('/api/v1/datasets/catalog?limit=1&offset=0')
        assert response.status_code == 200, response.text
        page = response.json()
        assert page['total'] == 1 and len(page['datasets']) == 1
        summary = page['datasets'][0]
        assert set(summary) == {'id', 'display_name', 'shape', 'wavelength_range', 'raw', 'source_path', 'available'}
        assert summary['available'] and summary['wavelength_range'] == [1, 4]
        assert 'wavelengths' not in response.text and 'metadata' not in response.text
        assert client.get('/api/v1/datasets/catalog?offset=1').json()['datasets'] == []
        assert client.get('/api/v1/datasets/catalog?limit=201').status_code == 400
        root = f'/api/v1/datasets/{identifier}/delete'
        preview = client.get(root + '/preview').json()
        for body in ({'confirm': True}, {'confirm': 1, 'preview_token': preview['preview_token']},
                     {'confirm': True, 'preview_token': preview['preview_token'], 'expires_at': 'forged'}):
            assert client.post(root, json=body).status_code == 400
        assert client.post(root, json={'confirm': False, 'preview_token': preview['preview_token']}).status_code == 409
        result = client.post(root, json={'confirm': True, 'preview_token': preview['preview_token']})
        assert result.status_code == 200, result.text
        assert client.get('/api/v1/recycle').json()['count'] == 1
        assert client.get('/api/v1/datasets/catalog').json()['total'] == 0
        assert client.post('/api/v1/datasets/import', json={'path': str(header), 'raw': True}).status_code == 409
        restore = '/api/v1/recycle/' + result.json()['deletion_id'] + '/restore'
        assert client.post(restore, json={'confirm': True, 'extra': 1}).status_code == 400
        restored = client.post(restore, json={'confirm': True})
        assert restored.status_code == 200, restored.text
        header.unlink()  # External source loss; the engine must report it, not hide the row.
        summary = client.get('/api/v1/datasets/catalog').json()['datasets'][0]
        assert summary['id'] == identifier and summary['available'] is False
        assert client.get(f'/api/v1/datasets/{identifier}/preview?band=0').status_code == 400


@pytest.mark.parametrize('path', ['/absolute', '../escape', 'exports\\cube', 'C:/escape', 'exports/../projects', './exports'])
def test_mapping_paths_refused(path):
    with error_code('INVALID_RECYCLE_PATH'):
        relative(path)
