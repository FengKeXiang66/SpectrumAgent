"""Cross-project bypasses, project-bound conversations and persistent step gates."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from test_experiment_conversation import application, workspace, machine_for, ScriptedModel
from backend.database import connect_database
from spectrumagent import projects
from spectrumagent.agent.scope import ScopedToolRegistry
from spectrumagent.agent.state import AgentStore
from spectrumagent.agent import step_plan
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.data import DataError
from spectrumagent.preprocess.current import CurrentWorkspace
from test_data_intake import source
from test_workspace_training import imported
from test_experiments import config_for
from spectrumagent.experiments.schema import ExperimentConfig


@pytest.fixture
def divided(application, tmp_path):
    app = application
    database = app.state.experiments.paths.database
    management = projects.Projects(database)
    a = management.list()['current_project_id']
    b = management.create('蛋项目')['id']
    result = {}
    for project in (a, b):
        folder = tmp_path / project
        folder.mkdir()
        images, _ = source(folder, 2)
        with projects.bind(project):
            cubes = [str(row.id) for row in app.state.dataset_registry.import_path(str(images)).datasets]
            sid = app.state.agent_sessions.create(project_id=project)['id']
            recipe = app.state.preprocess_runner.recipes.create('p-'+project, '配方'+project, None, {'steps': []})
            LabelStore(database).ensure_names(project, ['PE'])
        result[project] = dict(cubes=cubes, sid=sid, recipe=recipe, images=images)
    return app, management, a, b, result


def test_lists_counts_labels_and_catalog_ordinals_are_project_local(divided):
    app, _, a, b, rows = divided
    for project in (a, b):
        with projects.bind(project):
            registry = app.state.dataset_registry
            assert registry.catalog()['total'] == 2
            assert set(registry.display_names()) == set(rows[project]['cubes'])
            current = CurrentWorkspace(app.state.annotation_sessions, app.state.preprocess_runner).state()
            assert {r['cube_id'] for r in current['members']} == set(rows[project]['cubes'])
            assert rows[project]['recipe']['id'] in {r['id'] for r in current['recipes']}
            foreign = b if project == a else a
            assert rows[foreign]['recipe']['id'] not in {r['id'] for r in current['recipes']}
            tools = ScopedToolRegistry(app.state.agent_tools, app.state.agent_sessions, rows[project]['sid'])
            assert tools.invoke('datasets.resolve', {'query': 'D1'})['cube_id'] == rows[project]['cubes'][0]
            assert tools.invoke('workspace.current', {})['sample_count'] == 2
            assert app.state.agent_sessions.detail(rows[project]['sid'])['total_members'] == 2
            assert [r['id'] for r in app.state.agent_sessions.list()['sessions']] == [rows[project]['sid']]


def test_direct_uuid_bypasses_and_import_conflicts_fail_before_side_effects(divided):
    app, _, a, b, rows = divided
    with projects.bind(a):
        tools = ScopedToolRegistry(app.state.agent_tools, app.state.agent_sessions, rows[a]['sid'])
        for operation in [
            lambda: tools.invoke('datasets.resolve', {'query': rows[b]['cubes'][0]}),
            lambda: tools.invoke('datasets.describe', {'dataset_id': rows[b]['cubes'][0]}),
            lambda: tools.invoke('workspace.preprocess', {'cube_ids': rows[a]['cubes'], 'recipe_id': rows[b]['recipe']['id']}),
            lambda: app.state.dataset_registry.get(rows[b]['cubes'][0]),
            lambda: app.state.annotation_sessions.working(rows[b]['cubes'][0]),
            lambda: app.state.preprocess_runner.recipes.get(rows[b]['recipe']['id']),
            lambda: app.state.dataset_registry.import_path(str(rows[b]['images'])),
            lambda: app.state.agent_sessions.select(rows[a]['sid'], rows[b]['cubes'][0]),
        ]:
            with pytest.raises(DataError) as failure:
                operation()
            assert failure.value.code == 'RESOURCE_NOT_FOUND'
        with connect_database(app.state.experiments.paths.database) as db:
            assert db.execute('SELECT count(*) FROM preprocess_run').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM dataset_registry').fetchone()[0] == 4


def test_http_native_and_session_requests_use_different_trusted_bindings(divided):
    app, management, a, b, rows = divided
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer '+app.state.testing_identity.token
        assert client.put(f'/api/v1/agent/projects/{b}/current').status_code == 200
        assert management.list()['current_project_id'] == b
        assert client.get('/api/v1/preprocess/current').json()['members'][0]['cube_id'] in rows[b]['cubes']
        response = client.get(f"/api/v1/datasets/{rows[a]['cubes'][0]}")
        assert response.status_code == 404
        assert 'project_id' not in response.json().get('context', {})
        # Existing chat A stays bound to A even though the desktop is on B.
        response = client.patch(f"/api/v1/agent/sessions/{rows[a]['sid']}/selection", json={'cube_id':rows[b]['cubes'][0]})
        assert response.status_code == 404
        detail = client.get(f"/api/v1/agent/sessions/{rows[a]['sid']}").json()
        assert detail['project_id'] == a and detail['total_members'] == 2
        created = client.post('/api/v1/agent/sessions', json={'project_id':b}).json()
        assert created['project_id'] == b
        preview = client.get('/api/v1/agent/projects/migration-preview').json()
        assert preview['status'] == 'preview_only' and len(preview['datasets']) == 4
        assert {r['project_id'] for r in preview['datasets']} == {a,b}


def test_foreign_registered_model_and_training_ids_are_rejected(divided):
    app, _, a, b, rows = divided
    database = app.state.experiments.paths.database
    run, model, schema = (str(uuid4()) for _ in range(3))
    with connect_database(database) as db:
        db.execute("INSERT INTO label_schema(id,project_id,name,tree_path,field_type,created_at) VALUES(?,?,'量','量','continuous','now')", (schema,b))
        db.execute("INSERT INTO training_run(id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,cv_folds,seed,status,created_at,split_strategy,target_schema_id) VALUES(?,?, '[]','[]','regression','量','kfold',2,17,'succeeded','now','ks',?)",
                   (run,json.dumps(rows[b]['cubes']),schema))
        db.execute("INSERT INTO model_registry(id,run_id,name,version,target_schema_id,data_fingerprint,applicability,calibration,created_at) VALUES(?,?,'B',1,?,'hash','{}','{}','now')", (model,run,schema))
    with projects.bind(a):
        tools = ScopedToolRegistry(app.state.agent_tools, app.state.agent_sessions, rows[a]['sid'])
        for operation in [lambda: tools.invoke('modeling.infer', {'model_id':model,'cube_id':rows[a]['cubes'][0]}),
                          lambda: app.state.model_registry.register(run),
                          lambda: app.state.training_runs.get(run),
                          lambda: app.state.model_registry.set_stage(model, 'production')]:
            with pytest.raises(DataError, match='资源不存在'):
                operation()
        assert not app.state.model_registry.list()
        assert not app.state.training_runs.list()
    with connect_database(database) as db:
        assert db.execute('SELECT count(*) FROM inference_run').fetchone()[0] == 0
        assert db.execute('SELECT stage FROM model_registry WHERE id=?', (model,)).fetchone()[0] == 'experiment'


def test_chat_entry_and_step_plan_do_not_leak_future_actions_or_defaults(application, tmp_path):
    owner, dialogue, _ = imported(application, tmp_path, 4)
    database = application.state.experiments.paths.database
    model = ScriptedModel()
    plan = '''请按顺序执行，每完成一步先报告实际状态，然后停下等我确认。不要跳步，不要使用默认值。
【第1步】用当前已导入数据新建分类方案。报告数据数量、标签和当前是否有训练/测试划分。
【第2步】将第2、4张设为测试，其余用于训练。
【第3步】只写入草稿，预处理为原谱，无。不训练。
【第4步】发起寻优，实物评分，一图一物，折数3，潜变量1-2。'''
    events = list(machine_for(application, owner, model).message(content=plan))
    assert events[-1][0] == 'done', events
    assert not model.requests
    document = dialogue._read(owner)['document']
    assert len(document['workspace_selection']) == 4 and 'test' not in document
    assert not document['model'] and 'preprocessing' not in document
    assert not dialogue.study.latest(owner)
    record = step_plan.read(database,owner)
    assert record['step'] == 0 and record['waiting']
    from spectrumagent.agent.data_intake import workspace_training_requested
    assert not workspace_training_requested('不要用当前已导入数据新建分类方案')
    assert not workspace_training_requested('如何用已导入数据新建分类方案？')
    events = list(machine_for(application, owner, model).message(content='确认，继续'))
    assert step_plan.read(database,owner)['step'] == 1
    assert len(dialogue._read(owner)['document']['test']['members']) == 2
    assert not dialogue.study.latest(owner)
    assert step_plan.read(database,owner)['waiting']
    with pytest.raises(DataError, match='不能跳步'):
        step_plan.prepare(database,owner,'进入第4步')
    with pytest.raises(DataError, match='超出当前'):
        step_plan.validate_operation(database,owner,'study')


def test_archive_ownership_and_worker_capture_survive_desktop_switch(divided, tmp_path):
    app, management, a, b, _ = divided
    service = app.state.experiments
    config = ExperimentConfig.model_validate(config_for(tmp_path))
    with projects.bind(b):
        operation = projects.worker(lambda: service.run(config))
    management.select(a)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(operation).result(timeout=30)
    identifier = result['experiment_id']
    assert not service.archive.list()['items']
    with pytest.raises(DataError):
        service.folder(identifier)
    with projects.bind(b):
        assert service.get(identifier)['experiment_id'] == identifier
        assert service.archive.list()['total'] == 1


def test_historical_selection_cannot_be_replayed_after_resource_reassignment(divided):
    app, _, a, b, rows = divided
    database = app.state.experiments.paths.database
    with projects.bind(a):
        tools = ScopedToolRegistry(app.state.agent_tools, app.state.agent_sessions, rows[a]['sid'])
        cube = rows[a]['cubes'][0]
        with connect_database(database) as db:
            db.execute('UPDATE dataset_registry SET project_id=? WHERE id=?', (b,cube))
        with pytest.raises(DataError):
            tools._check('workspace.save_annotation', {'cube_id':cube})
        store = AgentStore(database)
        store.new_round(rows[a]['sid'],'旧计划',[{'id':'old','name':'workspace.save_annotation','arguments':{'cube_id':cube}}],status='plan_check')
        pending = app.state.agent_sessions.pending_view(store.pending(rows[a]['sid']))
        assert pending['blocked'] and '重新建立' in pending['reason']
        with pytest.raises(DataError) as blocked:
            machine_for(app,rows[a]['sid'],ScriptedModel()).message(plan_id=pending['plan_id'],action='approve')
        assert blocked.value.code == 'PROJECT_RECONFIRM_REQUIRED'
    with connect_database(database) as db:
        with pytest.raises(sqlite3.IntegrityError, match='SESSION_PROJECT_IMMUTABLE'):
            db.execute('UPDATE agent_session SET project_id=? WHERE id=?', (b,rows[a]['sid']))


def test_legacy_metadata_migration_has_a_consistent_backup_and_preserves_identity(workspace):
    database = workspace.root/'db'/'legacy.sqlite3'
    project, sid = str(uuid4()), str(uuid4())
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,created_at TEXT)')
        db.execute("INSERT INTO project VALUES(?,'默认项目','now')", (project,))
        db.execute('CREATE TABLE agent_session(id TEXT PRIMARY KEY,title TEXT,created_at TEXT,updated_at TEXT)')
        db.execute("INSERT INTO agent_session VALUES(?,'旧会话','now','now')", (sid,))
    backup = projects.backup_before_migration(database)
    assert backup.is_file()
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT id,title FROM agent_session').fetchone() == (sid,'旧会话')
        assert 'project_id' not in {r[1] for r in db.execute('PRAGMA table_info(agent_session)')}
    with connect_database(database) as db:
        projects.initialize(db)
        projects.initialize(db)
        assert db.execute('SELECT id,project_id FROM agent_session').fetchone() == (sid,project)
        assert any(r[2]=='project' and r[3]=='project_id' for r in db.execute('PRAGMA foreign_key_list(agent_session)'))
    assert projects.backup_before_migration(database) is None


def test_label_creation_is_project_local_and_reuses_names_across_concurrent_calls(divided):
    app, _, a, b, _ = divided
    database = app.state.experiments.paths.database
    with projects.bind(a):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result() for job in [pool.submit(projects.worker(lambda: LabelStore(database).ensure_names(a,['PET']))),
                                               pool.submit(projects.worker(lambda: LabelStore(database).ensure_names(a,['pet'])))]]
        assert results[0][0]['id'] == results[1][0]['id']
        with pytest.raises(DataError):
            LabelStore(database).ensure_names(b,['PET'])
        second = app.state.agent_sessions.create(project_id=a)['id']
        tools = ScopedToolRegistry(app.state.agent_tools, app.state.agent_sessions, second)
        assert tools.invoke('datasets.list', {})['dataset_count'] == 2


def test_shared_source_references_cannot_be_replayed_in_another_project(divided):
    from spectrumagent.agent.tools.operations import ReferenceBook
    app, _, a, b, rows = divided
    database = app.state.experiments.paths.database
    book = ReferenceBook(database)
    with projects.bind(b):
        reference = book.issue('C', rows[b]['images'])
    with projects.bind(a), pytest.raises(DataError):
        book.source(reference)
    with projects.bind(b):
        assert book.source(reference) == rows[b]['images']


def test_deselected_project_recipe_is_not_adopted_by_default_on_restart(divided):
    app, _, a, b, rows = divided
    store = app.state.preprocess_runner.recipes
    with projects.bind(b):
        store.deselect_project(b, rows[b]['recipe']['id'])
    with connect_database(app.state.experiments.paths.database) as db:
        projects.initialize(db)
    with projects.bind(a):
        assert rows[b]['recipe']['id'] not in {r['id'] for r in store.list()}


def test_palette_and_aliases_never_borrow_a_foreign_project_label(divided):
    from spectrumagent.annotation.palette import project_colors
    from spectrumagent.annotation.aliases import resolve
    app, _, a, b, rows = divided
    database = app.state.experiments.paths.database
    for project,color in ((a,'#112233'),(b,'#aabbcc')):
        with projects.bind(project):
            row = LabelStore(database).ensure_names(project,['PE'])[0]
            LabelStore(database).update(row['id'],color_hex=color)
    with projects.bind(a):
        # A raw external header path must not import B's label configuration.
        header = next(rows[b]['images'].glob('*.hdr'))
        assert project_colors(database,{1:'PE'},[header]) == {1:'#112233'}
        with pytest.raises(DataError):
            resolve(database,b,'PE')


def test_single_image_queue_captures_project_context_for_each_operation(divided):
    app, _, a, b, _ = divided
    database = app.state.experiments.paths.database
    queue = app.state.agent_sessions.annotation_tasks
    def identity():
        with connect_database(database) as db:
            return projects.current(db)
    for project in (a,b,a):
        with projects.bind(project):
            assert queue.run_sync(identity) == project
