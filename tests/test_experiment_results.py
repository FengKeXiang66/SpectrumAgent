"""Session-owned result display and offline exports reuse verified artifacts."""
import base64
from io import BytesIO
import json
from threading import Event
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from test_experiment_tasks import application, workspace, prepared, wait_task
from spectrumagent.agent.state import AgentStore
from spectrumagent.data import DataError
from spectrumagent.experiments.results import ExperimentResults, FILES, PLOTS
from spectrumagent.experiments.service import ExperimentModel


def test_result_plots_and_offline_exports_match_saved_artifacts(application, tmp_path, monkeypatch):
    dialogue, session = prepared(application, tmp_path)
    task = dialogue.tasks.submit(session, '确认执行', 'turn')
    row = wait_task(dialogue.tasks, session, task['task_id'])
    assert row['status'] == 'succeeded', row
    record = dialogue.service.get(row['experiment_id'])
    folder = dialogue.service.folder(row['experiment_id'])
    original = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}

    def cannot_train(*args):
        raise AssertionError('Reading or exporting results must not retrain')
    monkeypatch.setattr(ExperimentModel, 'fit', cannot_train)
    root = f'/api/v1/agent/sessions/{session}/experiments/{task["task_id"]}'
    identity = application.state.testing_identity
    headers = {'Authorization': 'Bearer ' + identity.token}
    with TestClient(application) as client:
        assert client.get(root + '/result').status_code == 401
        response = client.get(root + '/result', headers=headers)
        assert response.status_code == 200, response.text
        summary = response.json()
        assert summary['experiment_id'] == record['experiment_id']
        assert summary['metrics'] == record['metrics']
        assert summary['classes'] == record['config']['classes']
        assert summary['processed_axis'] == 'wavelength_nm'
        assert 'paths' not in json.dumps(summary)
        for name in PLOTS:
            response = client.get(root + '/plots/' + name, headers=headers)
            assert response.status_code == 200, response.text
            assert base64.b64decode(response.json()['png_base64']) == original[name]
        report = client.get(root + '/export/report', headers=headers)
        assert report.status_code == 200
        assert report.headers['content-type'] == 'application/octet-stream'
        html = report.content.decode('utf-8')
        assert html.count('src="data:image/png;base64,') == 4
        for name in PLOTS:
            assert f'src="{name}"' not in html
            assert base64.b64encode(original[name]).decode('ascii') in html
        bundle = client.get(root + '/export/bundle', headers=headers)
        assert bundle.status_code == 200
        with ZipFile(BytesIO(bundle.content)) as archive:
            assert set(archive.namelist()) == {'report.html', 'result.json', *FILES}
            assert archive.read('report.html') == report.content
            assert json.loads(archive.read('result.json')) == record
            for name in FILES:
                assert archive.read(name) == original[name]
        other = AgentStore(dialogue.database).create_session()['id']
        foreign = root.replace(session, other)
        for suffix in ('/result', '/plots/test_input.png', '/export/report'):
            assert client.get(foreign + suffix, headers=headers).status_code == 404
        for suffix in ('/plots/model.joblib', '/export/model'):
            assert client.get(root + suffix, headers=headers).status_code != 200
    assert {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()} == original

    # Changes to saved metrics, curves or report must never be presented/exported.
    results = ExperimentResults(dialogue)
    for name, read in (
        ('metrics.json', lambda: results.summary(session, task['task_id'])),
        ('test_input.png', lambda: results.plot(session, task['task_id'], 'test_input.png')),
        ('report.html', lambda: results.export(session, task['task_id'], 'report')),
    ):
        (folder / name).write_bytes(b'changed')
        with pytest.raises(DataError) as caught:
            read()
        assert caught.value.code == 'EXPERIMENT_ARTIFACT_CHANGED'
        (folder / name).write_bytes(original[name])


def test_result_is_unavailable_until_task_succeeds(application, tmp_path, monkeypatch):
    dialogue, session = prepared(application, tmp_path)
    entered, release = Event(), Event()
    original = ExperimentModel.fit
    def held_fit(self, X, y):
        entered.set()
        assert release.wait(10)
        return original(self, X, y)
    monkeypatch.setattr(ExperimentModel, 'fit', held_fit)
    try:
        task = dialogue.tasks.submit(session, '确认执行', 'turn')
        assert entered.wait(5)
        with pytest.raises(DataError) as caught:
            ExperimentResults(dialogue).summary(session, task['task_id'])
        assert caught.value.code == 'EXPERIMENT_RESULT_NOT_READY'
        assert caught.value.status_code == 409
    finally:
        release.set()
    assert wait_task(dialogue.tasks, session, task['task_id'])['status'] == 'succeeded'
