"""Project removal is reversible, scoped and cannot interrupt active work."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from test_experiment_conversation import application, workspace
from test_project_scopes import divided
from backend.database import connect_database
from spectrumagent import projects
from spectrumagent.agent.state import AgentStore
from spectrumagent.data import DataError


def remove(service, identifier, **kwargs):
    preview = service.deletion_preview(identifier)
    return service.delete(identifier, preview['name'], preview['confirmation_token'], **kwargs)


def test_delete_restore_preserves_resources_and_blocks_old_identifiers(divided, tmp_path):
    app, service, a, b, rows = divided
    database = app.state.experiments.paths.database
    service.select(b)
    source = next(rows[b]['images'].glob('*.hdr'))
    original = source.read_bytes()
    result = remove(service, b)
    assert result == {'project_id': b, 'deleted': True, 'current_project_id': a}
    page = service.list()
    assert [p['id'] for p in page['projects']] == [a]
    assert page['deleted_projects'][0]['id'] == b
    assert page['deleted_projects'][0]['dataset_count'] == 2
    with projects.bind(b):
        for call in [lambda: app.state.dataset_registry.get(rows[b]['cubes'][0]),
                     lambda: AgentStore(database).session(rows[b]['sid'])]:
            with pytest.raises(DataError, match='资源不存在'):
                call()
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer '+app.state.testing_identity.token
        assert client.get(f"/api/v1/agent/sessions/{rows[b]['sid']}").status_code == 404
        assert client.put(f'/api/v1/agent/projects/{b}/current').status_code == 404
        assert client.post('/api/v1/agent/sessions', json={'project_id': b}).status_code == 404
    with connect_database(database) as db:
        assert db.execute('SELECT COUNT(*) FROM dataset_registry').fetchone()[0] == 4
        projects.initialize(db)
    assert service.list()['current_project_id'] == a
    assert source.read_bytes() == original
    assert service.restore(b)['id'] == b
    assert service.list()['current_project_id'] == a  # Restore never silently switches projects.
    assert not service.list()['deleted_projects']
    service.select(b)
    with projects.bind(b):
        assert app.state.agent_sessions.detail(rows[b]['sid'])['total_members'] == 2
        assert rows[b]['recipe']['id'] in {r['id'] for r in app.state.preprocess_runner.recipes.list()}


def test_delete_last_project_and_stale_review_are_rejected(divided):
    app, service, a, b, _ = divided
    preview = service.deletion_preview(b)
    with pytest.raises(DataError) as failure:
        service.delete(b, 'wrong name', preview['confirmation_token'])
    assert failure.value.code == 'PROJECT_DELETE_REVIEW_CHANGED'
    with projects.bind(b):
        from spectrumagent.annotation.labels import LabelStore
        LabelStore(app.state.experiments.paths.database).ensure_names(b, ['新类别'])
    with pytest.raises(DataError) as failure:
        service.delete(b, preview['name'], preview['confirmation_token'])
    assert failure.value.code == 'PROJECT_DELETE_REVIEW_CHANGED'
    remove(service, b)
    with pytest.raises(DataError) as failure:
        remove(service, a)
    assert failure.value.code == 'LAST_PROJECT'


@pytest.mark.parametrize('kind', ['request', 'experiment', 'desktop_training', 'memory_queue'])
def test_active_work_blocks_removal(divided, kind):
    app, service, _, b, rows = divided
    database = app.state.experiments.paths.database
    with connect_database(database) as db:
        if kind == 'request':
            db.execute('''INSERT INTO agent_session_request(session_id,request_id,payload_hash,input_kind,boot_id,status,created_at)
                VALUES(?,?,'hash','content','boot','running','now')''', (rows[b]['sid'], str(uuid4())))
        elif kind == 'experiment':
            db.execute("INSERT INTO experiment_task VALUES(?,?,1,'queued','{}')", (str(uuid4()), rows[b]['sid']))
        elif kind == 'desktop_training':
            from spectrumagent.modeling.training_state import DDL
            db.executescript(DDL)
            db.execute('INSERT INTO training_job VALUES(?,?,?,?,?,?,?,?)', (str(uuid4()), 'boot', 'desktop', 'key',
                json.dumps({'cube_ids': rows[b]['cubes']}), '{}', '{"status":"queued"}', 'now'))
    with pytest.raises(DataError) as failure:
        remove(service, b, is_busy=lambda *_: kind == 'memory_queue')
    assert failure.value.code == 'PROJECT_BUSY'
    assert not service.list()['deleted_projects']


def test_delete_http_checks_annotation_queue_and_returns_restorable_receipt(divided):
    app, service, a, b, rows = divided
    task_id = str(uuid4())
    queue = app.state.agent_sessions.annotation_tasks
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer '+app.state.testing_identity.token
        preview = client.get(f'/api/v1/agent/projects/{b}/deletion-preview').json()
        body = {'confirm_name': preview['name'], 'confirmation_token': preview['confirmation_token']}
        queue.receipts[task_id] = {'owner_session_id': rows[b]['sid'], 'task_status': 'queued'}
        assert client.post(f'/api/v1/agent/projects/{b}/trash', json=body).json()['error'] == 'PROJECT_BUSY'
        queue.receipts.pop(task_id)
        # A different project's queue cannot block this project.
        queue.receipts[task_id] = {'owner_session_id': rows[a]['sid'], 'task_status': 'queued'}
        response = client.post(f'/api/v1/agent/projects/{b}/trash', json=body)
        queue.receipts.pop(task_id)
        assert response.status_code == 200 and response.json()['deleted']
        assert client.post(f'/api/v1/agent/projects/{b}/restore').json()['id'] == b
        invalid = client.post(f'/api/v1/agent/projects/{b}/trash', json={**body, 'confirmation_token': 'bad'})
        assert invalid.status_code == 400 and invalid.json()['error'] == 'INVALID_REQUEST'


def test_two_concurrent_deletions_leave_one_live_project(divided):
    _, service, a, b, _ = divided
    def attempt(identifier):
        try:
            return remove(service, identifier)['deleted']
        except DataError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [a, b]))
    assert sorted(map(str, results)) == ['LAST_PROJECT', 'True']
    assert len(service.list()['projects']) == 1


def test_native_request_activity_and_project_deletion_are_mutually_exclusive(divided):
    app, service, a, b, _ = divided
    database = app.state.experiments.paths.database
    service.select(b)
    @app.get('/api/v1/test-project-activity')
    def native_operation():
        return remove(service, b)
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer '+app.state.testing_identity.token
        response = client.get('/api/v1/test-project-activity')
        assert response.status_code == 409 and response.json()['error'] == 'PROJECT_BUSY'
    with projects.project_change(database, b):
        with pytest.raises(DataError):
            with projects.activity(database, b):
                pytest.fail('A new operation cannot enter during project deletion')
        # An unrelated project remains usable.
        with projects.activity(database, a):
            pass
    assert remove(service, b)['deleted']
