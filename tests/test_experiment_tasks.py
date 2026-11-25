"""Background admission, real phase boundaries, ownership and cancellation."""
import time
from threading import Event

import pytest
from test_experiment_conversation import application, workspace, patch_for, wait_task
from spectrumagent.agent.state import AgentStore
from spectrumagent.agent.tools.experiments import DraftUpdate
from spectrumagent.experiments.service import ExperimentModel
from spectrumagent.data import DataError
from spectrumagent.experiments.schema import ExperimentConfig


def prepared(application, tmp_path):
    body, patch = patch_for(tmp_path)
    dialogue = application.state.agent_tools.experiment_dialogue
    session = AgentStore(dialogue.database).create_session()['id']
    dialogue.capture(session, '训练测试 "' + body['train']['paths'][0] + '" "' + body['test']['paths'][0] + '"')
    dialogue.update(session, DraftUpdate.model_validate(patch))
    dialogue.presented(session, 'review')
    return dialogue, session


def test_submit_returns_before_fit_and_cancel_stops_before_testing(application, tmp_path, monkeypatch):
    dialogue, session = prepared(application, tmp_path)
    entered, release = Event(), Event()
    original = ExperimentModel.fit
    fits = []
    def held_fit(self, X, y):
        fits.append(True)
        entered.set()
        assert release.wait(10)
        return original(self, X, y)
    monkeypatch.setattr(ExperimentModel, 'fit', held_fit)
    try:
        started = time.monotonic()
        task = dialogue.tasks.submit(session, '确认执行', 'turn')
        assert time.monotonic() - started < 2
        assert entered.wait(5)
        assert dialogue.tasks.view(session, task['task_id'])['phase'] == 'training'
        repeated = dialogue.tasks.submit(session, '确认执行', 'second-turn')
        assert repeated['task_id'] == task['task_id'] and len(fits) == 1
        with pytest.raises(DataError) as caught:
            dialogue.tasks.cancel('another-session', task['task_id'])
        assert caught.value.code == 'EXPERIMENT_TASK_NOT_FOUND'
        with pytest.raises(DataError):
            dialogue.update(session, DraftUpdate(expected_revision=1, name='changed'))
        pending = dialogue.tasks.cancel(session, task['task_id'])
        assert pending['cancel_requested'] and pending['status'] == 'running'
    finally:
        release.set()
    result = wait_task(dialogue.tasks, session, task['task_id'])
    assert result['status'] == 'cancelled'
    assert result['completed_phases'] == ['checking', 'preparing']
    assert dialogue.result(session)['status'] == 'cancelled'
    assert not list(application.state.experiments.root.rglob('test_predictions.npz'))


def test_background_failure_identifies_phase_without_reporting_success(application, tmp_path, monkeypatch):
    dialogue, session = prepared(application, tmp_path)
    def failed_fit(*args):
        raise DataError('EXPERIMENT_LV_INVALID', '潜变量配置不合法')
    monkeypatch.setattr(ExperimentModel, 'fit', failed_fit)
    task = dialogue.tasks.submit(session, '确认执行', 'turn')
    row = wait_task(dialogue.tasks, session, task['task_id'])
    assert row['status'] == 'failed' and row['failed_phase'] == 'training'
    assert row['error'] == 'EXPERIMENT_LV_INVALID'
    assert row['completed_phases'] == ['checking', 'preparing']
    assert row['train_accuracy'] is None


def test_cancel_at_initial_boundary_leaves_queryable_status(application, tmp_path):
    from test_experiments import config_for
    service = application.state.experiments
    def cancel(phase):
        raise DataError('EXPERIMENT_CANCELLED', '已取消')
    with pytest.raises(DataError) as caught:
        service.run(ExperimentConfig.model_validate(config_for(tmp_path)), progress=cancel)
    result = service.get(caught.value.payload.context['experiment_id'])
    assert result['status'] == 'cancelled'
def test_task_id_and_results_survive_backend_reopening(application, tmp_path):
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from backend.identity import EngineIdentity
    from spectrumagent.app import create_app
    from spectrumagent.agent.state import AgentStore

    dialogue, owner = prepared(application, tmp_path)
    task = dialogue.tasks.submit(owner, '确认执行', 'restart-test-submit')
    done = wait_task(dialogue.tasks, owner, task['task_id'])
    assert done['status'] == 'succeeded'
    other = AgentStore(dialogue.database).create_session()['id']
    interrupted_id = str(uuid4())
    interrupted = {**dialogue.tasks.rows[task['task_id']], 'task_id':interrupted_id, 'session_id':other,
                   'status':'running', 'phase':'preparing', 'finished_at':None, 'experiment_id':None}
    dialogue.tasks._persist(interrupted)
    identity = EngineIdentity()
    fresh = create_app(dialogue.service.paths, identity)
    prefix = '/api/v1/agent/sessions'
    with TestClient(fresh) as client:
        client.headers['Authorization'] = 'Bearer ' + identity.token
        receipt = prefix + f'/{owner}/experiments/{task["task_id"]}'
        assert client.get(receipt).json()['status'] == 'succeeded'
        assert client.get(receipt+'/result').json()['experiment_id'] == done['experiment_id']
        broken = client.get(prefix + f'/{other}/experiments/{interrupted_id}').json()
        assert broken['status'] == 'interrupted' and broken['failed_phase'] == 'preparing'
