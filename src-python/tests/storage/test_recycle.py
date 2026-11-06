"""Real SQLite/FK/file lifecycle tests for permanent dataset deletion.

Deletion is human-confirmed, removes every related business row and every owned
product directory, and never touches the original ENVI source files. A short
``deletion_pending`` journal drives startup cleanup after an interrupted erase.
"""
from datetime import timedelta
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import asyncio
import hashlib
import json
import sqlite3
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4
from weakref import WeakKeyDictionary

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
from spectrumagent.storage.recycle import TABLES, encode, relative
from cubes import cube


@contextmanager
def error_code(code):
    with pytest.raises(DataError) as raised:
        yield raised
    assert raised.value.code == code


def files(root):
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def owned(c):
    """Every directory the impact list promises to erase."""
    return [f'annotations/{c.cube}/v1', f'exports/{c.cube}',
            f'preprocessed/{c.cube}/{c.ids["preprocess"]}',
            f'models/{c.ids["training"]}', f'inferences/{c.ids["inference"]}']


def test_configured_output_delete_mapping_is_owned_and_preserves_source(case, tmp_path):
    c = case
    output = tmp_path/'delete-output'
    with connect_database(c.paths.database) as db:
        db.execute('CREATE TABLE project_path_settings (project_id TEXT PRIMARY KEY,source_path TEXT NOT NULL,output_root TEXT NOT NULL,updated_at TEXT NOT NULL)')
        db.execute("INSERT INTO project_path_settings VALUES (?,'',?,'fixture')",(c.project,str(output)))
        db.execute('UPDATE preprocess_artifact SET relative_path=? WHERE run_id=?',
                   (f'{c.project}/{c.cube}/{c.ids["preprocess"]}/report.json',c.ids['preprocess']))
    c.paths.create_directories(activate_output=True)
    directory = output/c.project/c.cube/c.ids['preprocess']
    storage.mkdir(directory,parents=True)
    storage.resolve_write(directory/'report.json',kind='TEST_ARTIFACT').write_bytes(b'owned report')
    source_before = files(c.source)
    mapped = f'preprocessed/{c.project}/{c.cube}/{c.ids["preprocess"]}'
    assert c.store._owned(mapped,c.cube) == directory
    with error_code('INVALID_DELETE_PATH'):
        c.store._owned(f'preprocessed/{uuid4()}/{c.cube}/{c.ids["preprocess"]}',c.cube)
    with error_code('INVALID_DELETE_PATH'):
        c.store._owned(mapped,str(uuid4()))
    preview = c.store.preview(c.cube)
    item = next(item for item in preview['directories'] if item['path']==mapped)
    assert item['bytes'] == len(b'owned report')
    result = c.store.delete(c.cube,confirm=True,preview_token=preview['preview_token'])
    assert result['pending_directories'] == [] and not directory.exists()
    assert files(c.source) == source_before and not pending(c)


@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'source'
    header, _, _ = cube(source)
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
                           source=source, header=header, ids=ids, original=original, assets=assets,
                           project=project)


def deleted(c):
    preview = c.store.preview(c.cube)
    return c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])


def audit(c, action):
    with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
        return db.execute('SELECT cube_id,summary_json FROM deletion_audit WHERE action=?', (action,)).fetchall()


def pending(c):
    with connect_database(c.paths.database) as db:
        return db.execute('SELECT path FROM deletion_pending ORDER BY seq').fetchall()


def test_permanent_delete_removes_rows_files_and_keeps_sources(case):
    c = case
    source_before, projects_before = files(c.source), files(c.paths.root / 'projects')
    preview = c.store.preview(c.cube)
    assert [preview[k] for k in ('annotation_versions', 'preprocess_runs', 'training_runs', 'inference_runs')] == [1, 1, 1, 1]
    assert preview['total_bytes'] > 0
    assert {item['path'] for item in preview['directories']} == set(owned(c))
    result = c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
    assert result['permanent'] is True and result['pending_directories'] == []
    assert result['deleted_at'] and result['deletion_id']
    assert 'expires_at' not in result  # No 30-day retention window.
    for directory in owned(c):
        assert not (c.paths.root / directory).exists(), directory
    assert not (c.paths.root / f'annotations/{c.cube}/v1/annotation.json').is_file()
    assert not (c.paths.root / f'exports/{c.cube}/manifest.json').is_file()
    assert (c.paths.root / f'annotations/{c.cube}/unreferenced/keep.json').is_file()
    assert files(c.paths.root / 'projects') == projects_before
    assert list(c.paths.trash.iterdir()) == [] and c.paths.trash.is_dir()
    with connect_database(c.paths.database) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for table in TABLES:
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0, table
        assert pending(c) == []
        context = db.execute("SELECT context_json FROM agent_session WHERE id='fixture-session'").fetchone()[0]
        assert c.cube not in context and c.ids['version'] not in context
        assert json.loads(context)['keep'] == 'other'
        for table, original in c.assets.items():
            assert db.execute(f'SELECT * FROM {table}').fetchall() == original
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not names.intersection({'recycle_bin', 'recycle_item', 'recycle_health'})
    assert files(c.source) == source_before and c.header.is_file()
    for action in (lambda: storage.resolve_write(c.header, kind='D_SOURCE_WRITE').write_text('must be denied', 'utf-8'),
                   lambda: storage.unlink(c.header)):
        with error_code('WRITE_TO_SOURCE_DENIED'):
            action()
    assert audit(c, 'DELETE')
    with sqlite3.connect(c.registry.storage_guard.audit_database) as db:
        assert db.execute("SELECT COUNT(*) FROM write_audit WHERE action='DELETE' AND decision='ALLOW'").fetchone()[0] >= len(owned(c))
    with error_code('DATASET_NOT_FOUND'):
        c.registry.get(c.cube)


@pytest.mark.parametrize('mode', ['false', 'tampered', 'expired', 'changed'])
def test_preview_binding(case, mode):
    c = case
    before, source_before = files(c.paths.root / 'exports'), files(c.source)
    token = c.store.preview(c.cube)['preview_token']
    confirm = mode != 'false'
    if mode == 'tampered':
        token += 'x'
    if mode == 'expired':
        now = c.store.clock()
        c.store.clock = lambda: now + timedelta(minutes=6)
    if mode == 'changed':
        (c.paths.exports / c.cube / 'sample.json').write_text('changed')
    with pytest.raises(DataError):
        c.store.delete(c.cube, confirm=confirm, preview_token=token)
    assert c.registry.get(c.cube)
    assert pending(c) == []
    assert all((c.paths.root / directory).is_dir() for directory in owned(c))
    assert files(c.source) == source_before
    if mode == 'changed':
        assert files(c.paths.root / 'exports') != before


def test_confirmation_and_token_are_mandatory(case):
    c = case
    token = c.store.preview(c.cube)['preview_token']
    with error_code('DELETE_CONFIRMATION_REQUIRED'):
        c.store.delete(c.cube, confirm=False, preview_token=token)
    with error_code('DELETE_PREVIEW_EXPIRED'):
        c.store.delete(c.cube, confirm=True, preview_token='forged')
    assert c.registry.get(c.cube) and pending(c) == []


def test_multi_cube_fails_closed(case):
    c = case
    with connect_database(c.paths.database) as db:
        db.execute('UPDATE training_run SET cube_ids=?', (json.dumps([c.cube, str(uuid4())]),))
    with error_code('MULTI_CUBE_RUN'):
        c.store.preview(c.cube)
    assert c.registry.get(c.cube) and pending(c) == []


def test_reimport_after_delete_is_plain_first_import(case):
    c = case
    deleted(c)
    fresh = str(c.registry.import_path(str(c.header), raw=True).datasets[0].id)
    assert fresh != c.cube
    confirmed = str(c.registry.import_path(str(c.header), raw=True, confirm_new=True).datasets[0].id)
    assert confirmed == fresh  # An existing active row is returned, not a new id.
    with connect_database(c.paths.database) as db:
        for table in ('annotation_version', 'annotation_draft', 'preprocess_run', 'sample_target'):
            assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE cube_id=?', (fresh,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM training_run').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM deletion_pending').fetchone()[0] == 0


def test_reimport_confirmed_race(case, monkeypatch):
    c = case
    deleted(c)
    other = DatasetRegistry(c.paths.database)
    barrier = Barrier(2)
    for registry in (c.registry, other):
        original = registry._import_preflight
        def synchronized(*args, _original=original):
            decision = _original(*args)
            barrier.wait(timeout=10)
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
    result = c.registry.import_path(str(c.source), raw=True)
    assert result.summary.model_dump() == {'total': 2, 'imported': 2, 'existing': 0}
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM deletion_pending').fetchone()[0] == 0


def test_reimport_key_includes_raw(case):
    c = case
    deleted(c)
    reflected = c.registry.import_path(str(c.header), raw=False)
    raw = c.registry.import_path(str(c.header), raw=True)
    assert reflected.summary.imported == 1 and raw.summary.imported == 1
    assert str(reflected.datasets[0].id) != str(raw.datasets[0].id)


def test_legacy_recycle_tables_and_trash_are_purged_on_startup(case, monkeypatch):
    c = case
    with connect_database(c.paths.database) as db:
        db.execute('CREATE TABLE recycle_bin (deletion_id TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE recycle_item (deletion_id TEXT)')
        db.execute('CREATE TABLE recycle_health (deletion_id TEXT)')
        db.execute("INSERT INTO recycle_bin VALUES ('legacy')")
    legacy_folder = c.paths.trash / 'legacy-batch'
    legacy_folder.mkdir(parents=True)
    (legacy_folder / 'annotation.json').write_text('{}', encoding='utf-8')
    (c.paths.trash / 'stray.txt').write_text('stray', encoding='utf-8')
    from spectrumagent.storage import recycle as recycle_module
    monkeypatch.setattr(recycle_module, '_coordinators', WeakKeyDictionary())
    fresh = DatasetRegistry(c.paths.database)
    assert fresh.recycle.coordinator.ready
    with connect_database(c.paths.database) as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not names.intersection({'recycle_bin', 'recycle_item', 'recycle_health'})
    assert list(c.paths.trash.iterdir()) == [] and c.paths.trash.is_dir()
    assert audit(c, 'LEGACY_RECYCLE_PURGED')
    assert c.header.is_file()


def test_pending_directories_are_finished_on_startup(case, monkeypatch):
    c = case
    original, failing = storage.rmtree, {'on': True}
    def injected(path):
        if failing['on'] and path.name == c.ids['training']:
            raise OSError('injected erase failure')
        return original(path)
    monkeypatch.setattr(storage, 'rmtree', injected)
    result = deleted(c)
    assert result['pending_directories'] == [f'models/{c.ids["training"]}']
    assert (c.paths.root / f'models/{c.ids["training"]}/model.json').is_file()
    assert not (c.paths.root / f'exports/{c.cube}').exists()
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM deletion_pending').fetchone()[0] == 1
    assert audit(c, 'DELETE_PENDING')
    failing['on'] = False
    assert c.store.finish_pending() == 0
    assert all(not (c.paths.root / directory).exists() for directory in owned(c))
    assert pending(c) == []
    assert audit(c, 'DELETE_CLEANUP_DONE')


def test_busy_and_startup_gate(case):
    c = case
    preview = c.store.preview(c.cube)
    with c.store.coordinator.job():
        with error_code('DATASET_BUSY'):
            c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
    c.store.coordinator.ready = False
    for operation in (lambda: c.registry.get(c.cube), lambda: c.registry.import_path(str(c.header)),
                      lambda: c.store.preview(c.cube)):
        with error_code('DELETION_CLEANUP_REQUIRED'):
            operation()
    assert c.store.finish_pending() == 0
    assert c.registry.get(c.cube)
    assert c.registry.storage_guard.events.index('self_check') < c.registry.storage_guard.events.index('deletion_cleanup_started')


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
        assert client.get('/api/v1/recycle').status_code == 404
        assert client.post(f'/api/v1/recycle/{uuid4()}/restore', json={'confirm': True}).status_code == 404
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
                     {'confirm': True, 'preview_token': preview['preview_token'], 'expires_at': 'forged'},
                     {'confirm': True, 'preview_token': preview['preview_token'], 'extra': 1}):
            assert client.post(root, json=body).status_code == 400
        assert client.post(root, json={'confirm': False, 'preview_token': preview['preview_token']}).status_code == 409
        result = client.post(root, json={'confirm': True, 'preview_token': preview['preview_token']})
        assert result.status_code == 200, result.text
        assert result.json()['permanent'] is True and result.json()['pending_directories'] == []
        assert client.get('/api/v1/datasets/catalog').json()['total'] == 0
        # A deleted path is a plain first import again, with a brand new id.
        again = client.post('/api/v1/datasets/import', json={'path': str(header), 'raw': True})
        assert again.status_code == 200, again.text
        assert again.json()['datasets'][0]['id'] != identifier
        header.unlink()  # External source loss; the engine must report it, not hide the row.
        catalog = client.get('/api/v1/datasets/catalog').json()['datasets'][0]
        assert catalog['available'] is False
        assert client.get(f'/api/v1/datasets/{catalog["id"]}/preview?band=0').status_code == 400


@pytest.mark.parametrize('path', ['/absolute', '../escape', 'exports\\cube', 'C:/escape', 'exports/../projects', './exports'])
def test_mapping_paths_refused(path):
    with error_code('INVALID_DELETE_PATH'):
        relative(path)
