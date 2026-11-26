"""Cross-session persistence, interrupted runs and frozen fitted model reuse."""
import copy
import hashlib
import json
import shutil
import tempfile

from fastapi.testclient import TestClient
import numpy as np
import pytest

from test_experiment_conversation import ScriptedModel, machine_for, tool, wait_task
from test_experiment_tasks import prepared
from test_experiments import config_for
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app
from spectrumagent.agent.state import AgentStore
from spectrumagent.data import DataError
from spectrumagent.experiments.schema import ExperimentConfig
from spectrumagent.experiments.service import ExperimentModel, write_json
from spectrumagent.storage import guard


@pytest.fixture
def archived_app(tmp_path, monkeypatch):
    temporary = tmp_path / 'temporary'
    temporary.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(temporary))
    monkeypatch.setattr(guard, '_guards', {})
    monkeypatch.setattr(guard, '_current', None)
    monkeypatch.setenv('SPECTRUMAGENT_PERMANENT_ROOT', str(tmp_path / 'permanent'))
    paths = AppPaths(tmp_path / 'boot-a')
    paths.create_directories()
    app = create_app(paths, EngineIdentity())
    yield app
    for instance in guard._guards.values():
        instance.close()


def restart(app, tmp_path):
    # Simulate the shell deleting its old session and a fresh backend process.
    paths = app.state.experiments.paths
    assert paths.root.resolve().is_relative_to(tmp_path.resolve())
    assert not paths.experiment_archive.resolve().is_relative_to(paths.root.resolve())
    for instance in guard._guards.values():
        instance.close()
    guard._guards.clear()
    guard._current = None
    shutil.rmtree(paths.root)
    fresh = AppPaths(tmp_path / 'boot-b')
    fresh.create_directories()
    identity = EngineIdentity()
    app = create_app(fresh, identity)
    app.state.testing_identity = identity
    return app


def test_archive_survives_session_cleanup_and_reuses_original_model(archived_app, tmp_path, monkeypatch):
    app = archived_app
    dialogue, session = prepared(app, tmp_path)
    task = dialogue.tasks.submit(session, '确认执行', 'turn')
    task = wait_task(dialogue.tasks, session, task['task_id'])
    assert task['status'] == 'succeeded'
    identifier = task['experiment_id']
    original = dialogue.service.get(identifier)
    folder = dialogue.service.folder(identifier)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    with np.load(folder / 'test_prepared.npz') as data, np.load(folder / 'test_predictions.npz') as predictions:
        X, waves, expected = data['X'].copy(), data['wavelengths_nm'].copy(), predictions['prediction'].copy()
    # Viewing and loading the fitted model must work even when inputs are gone.
    for role in ('train', 'test'):
        source = tmp_path / (role + '.npz')
        assert source.parent == tmp_path
        source.unlink()
    def cannot_fit(*args):
        raise AssertionError('Archive queries and reuse must never fit a model')
    monkeypatch.setattr(ExperimentModel, 'fit', cannot_fit)
    fresh = restart(app, tmp_path)
    service = fresh.state.experiments
    assert service.get(identifier) == original
    np.testing.assert_array_equal(service.archive.load_model(identifier).predict(X, waves), expected)
    owner = AgentStore(service.paths.database).create_session()['id']
    base = f'/api/v1/agent/sessions/{owner}'
    with TestClient(fresh) as client:
        assert client.get(base + '/experiment-history').status_code == 401
        client.headers['Authorization'] = 'Bearer ' + fresh.state.testing_identity.token
        assert client.get(base + '/experiments/' + task['task_id']).status_code == 404
        page = client.get(base + '/experiment-history').json()
        assert page['total'] == 1 and page['items'][0]['experiment_id'] == identifier
        assert page['items'][0]['model_id'] == original['model_id'] == identifier
        assert client.get(base + '/experiment-history?limit=0').status_code == 400
        assert client.get(base + '/experiment-history?offset=99').json()['items'] == []
        summary = client.get(base + f'/experiment-history/{identifier}/result')
        assert summary.status_code == 200, summary.text
        assert summary.json()['metrics'] == original['metrics']
        assert summary.json()['model']['sha256'] == original['model_sha256']
        assert summary.json()['model']['preprocessing'] == original['config']['preprocessing']
        assert client.get(base + f'/experiment-history/{identifier}/plots/test_input.png').status_code == 200
        html = client.get(base + f'/experiment-history/{identifier}/export/report')
        assert html.status_code == 200 and html.content.count(b'data:image/png;base64,') == 4
        selected = client.post(base + '/experiment-history/selection', json={'experiment_id': identifier})
        assert selected.status_code == 200, selected.text
        assert selected.json()['archived_experiment_id'] == identifier
    model = ScriptedModel()
    events = list(machine_for(fresh, owner, model).message(content='查询实验结果'))
    assert events[-1][1]['task_result'] == 'succeeded' and not model.requests
    assert '持久归档' in events[-1][1]['content']
    import sklearn
    with monkeypatch.context() as versions:
        versions.setattr(sklearn, '__version__', 'incompatible')
        with pytest.raises(DataError) as caught:
            service.archive.load_model(identifier)
        assert caught.value.code == 'EXPERIMENT_MODEL_ENVIRONMENT_CHANGED'
    # A new conversation can resolve "上次" without reconstructing any old task.
    another = AgentStore(service.paths.database).create_session()['id']
    events = list(machine_for(fresh, another, ScriptedModel()).message(content='查看上次实验'))
    assert any(event == 'step' and data['result_summary'].get('archived_experiment_id') == identifier for event, data in events)
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()} == hashes
    with pytest.raises(DataError) as caught:
        guard.resolve_write(service.paths.credential_root / 'credentials' / 'test', kind='TEST')
    assert caught.value.code == 'WRITE_TO_SOURCE_DENIED'
    # A damaged joblib is rejected before deserialization.
    (folder / 'model.joblib').write_bytes(b'changed')
    with pytest.raises(DataError) as caught:
        service.archive.load_model(identifier)
    assert caught.value.code == 'EXPERIMENT_ARTIFACT_CHANGED'


def test_running_archive_becomes_interrupted_without_claiming_model_ready(archived_app, tmp_path):
    service = archived_app.state.experiments
    from uuid import uuid4
    identifier = str(uuid4())
    folder = service.folder(identifier)
    guard.mkdir(folder)
    write_json(folder / 'config.json', config_for(tmp_path))
    write_json(folder / 'status.json', {'experiment_id': identifier, 'status': 'running', 'phase': 'training',
                                      'started_at': '2026-11-20T00:00:00+00:00'})
    partial = folder / 'partial-output.txt'
    guard.resolve_write(partial, kind='TEST').write_text('partial', encoding='utf-8')
    fresh = restart(archived_app, tmp_path)
    recovered = fresh.state.experiments
    assert recovered.get(identifier)['status'] == 'interrupted'
    assert recovered.get(identifier)['phase'] == 'training'
    assert partial.read_text('utf-8') == 'partial'
    row = recovered.archive.list()['items'][0]
    assert row['model_id'] is None and row['status'] == 'interrupted'
    with pytest.raises(DataError) as caught:
        recovered.archive.load_model(identifier)
    assert caught.value.code == 'EXPERIMENT_MODEL_NOT_READY'


def test_history_ambiguity_and_comparison_keep_evaluation_boundaries(archived_app, tmp_path, monkeypatch):
    app = archived_app
    service = app.state.experiments
    body = config_for(tmp_path)
    first = service.run(ExperimentConfig.model_validate(body))
    changed = copy.deepcopy(body)
    changed['preprocessing'] = [{'op': 'center'}]
    second = service.run(ExperimentConfig.model_validate(changed))
    same = service.archive.compare(first['experiment_id'], second['experiment_id'])
    assert same['comparable'] and all(same['checks'].values())
    changed['test_usage'] = 'development_regression'
    third = service.run(ExperimentConfig.model_validate(changed))
    different = service.archive.compare(second['experiment_id'], third['experiment_id'])
    assert not different['comparable'] and not different['checks']['test_usage']
    owner = AgentStore(service.paths.database).create_session()['id']
    model = ScriptedModel()
    events = list(machine_for(app, owner, model).message(content='查询实验结果'))
    assert events[-1][0] == 'clarify' and '共3条' in events[-1][1]['question']
    assert app.state.agent_tools.experiment_dialogue.selected(owner) is None
    assert not model.requests
    model = ScriptedModel(tool('experiments.history_compare', {'first_id': second['experiment_id'], 'second_id': third['experiment_id']}))
    events = list(machine_for(app, owner, model).message(content='比较这两次实验的测试指标'))
    assert events[-1][1]['task_result'] == 'succeeded', events
    assert '仅并列展示' in events[-1][1]['content']
    assert len(model.requests) == 1
    chosen = second['experiment_id']
    model = ScriptedModel(tool('experiments.history_list', {}),
                          tool('experiments.history_select', {'experiment_id': chosen}))
    events = list(machine_for(app, owner, model).message(content='查找第二个历史实验并打开'))
    assert events[-1][1]['task_result'] == 'succeeded', events
    assert app.state.agent_tools.experiment_dialogue.selected(owner) == chosen
    assert len(model.requests) == 2
    # Historical records from both old format (no model_id) and new format stay readable.
    path = service.folder(first['experiment_id']) / 'result.json'
    legacy = json.loads(path.read_text('utf-8'))
    legacy.pop('model_id')
    write_json(path, legacy)
    assert service.archive.model_metadata(first['experiment_id'])['model_id'] == first['experiment_id']
