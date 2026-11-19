"""Conversation integration and execution guards; no external model credentials."""
import copy
import json
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from test_experiments import workspace, config_for
from spectrumagent.app import create_app
from spectrumagent.agent.llm import ChatResult, ToolCall, _egress_blocked, _workflow_wire
from spectrumagent.agent.scope import ScopedToolRegistry
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.tools.experiments import DraftUpdate
from spectrumagent.data import DataError
from spectrumagent.experiments.conversation import ExperimentDialogue
from spectrumagent.experiments.service import ExperimentModel
from backend.identity import EngineIdentity


class ScriptedModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, messages, tools):
        self.requests.append((messages, tools))
        assert not _egress_blocked({'messages': messages, 'tools': tools})
        assert all(tool['function']['name'].startswith('experiments.') for tool in tools)
        response = self.responses.pop(0)
        return response(messages) if callable(response) else response


def tool(name, arguments):
    return ChatResult(content=None, finish_reason='tool_calls', tool_calls=[ToolCall(
        id=str(uuid4()), name=name, arguments_json=json.dumps(arguments, ensure_ascii=False))])


def patch_for(tmp_path):
    body = config_for(tmp_path)
    patch = copy.deepcopy(body)
    patch.pop('wavelengths_nm')
    for role, reference in (('train', 'S1'), ('test', 'S2')):
        patch[role].pop('paths')
        patch[role]['source_refs'] = [reference]
        patch[role].update(labels_key='y', wavelengths_key='wavelengths_nm')
    patch['classes'] = [{'label': label, 'name': name} for label, name in body['classes'].items()]
    patch.update(axis={'kind': 'archive', 'role': 'train'}, expected_revision=0)
    return body, patch


@pytest.fixture
def application(workspace):
    identity = EngineIdentity()
    app = create_app(workspace, identity)
    app.state.testing_identity = identity
    return app


def machine_for(app, session, model):
    store = AgentStore(app.state.experiments.paths.database)
    return StateMachine(store, session, model, ScopedToolRegistry(
        app.state.agent_tools, app.state.agent_sessions, session))


def test_multi_turn_partial_patch_review_execute_and_query(tmp_path, application):
    body, patch = patch_for(tmp_path)
    app = application
    store = AgentStore(app.state.experiments.paths.database)
    session = store.create_session()['id']
    partial = copy.deepcopy(patch)
    partial['preprocessing'] = [{'op': 'savgol', 'derivative': 2}]
    model = ScriptedModel(tool('experiments.draft_update', partial),
        tool('experiments.draft_update', {'expected_revision': 1,
             'preprocessing': [{'op': 'savgol', 'derivative': 2, 'window': 5, 'polyorder': 2, 'delta_nm': 5.}, {'op': 'center'}]}))
    first = list(machine_for(app, session, model).message(content='PLSDA训练与测试，训练数据“' + body['train']['paths'][0]
                 + '”，测试数据“' + body['test']['paths'][0] + '”，用SG二阶导数。'))
    assert first[-1][0] == 'clarify', first
    assert '窗口长度' in first[-1][1]['question']
    assert not list(app.state.experiments.root.glob('*'))
    sent = json.dumps(model.requests[0][0], ensure_ascii=False)
    assert str(tmp_path) not in sent and 'S1' in sent
    second = list(machine_for(app, session, model).message(content='窗口5、多项式2阶、步长5nm，再中心化。'))
    assert second[-1][0] == 'clarify', second
    assert '确认执行' in second[-1][1]['question']
    draft = app.state.agent_tools.experiment_dialogue
    assert draft._read(session)['document']['train']['source_refs'] == ['S1']
    assert draft._read(session)['document']['model']['n_components'] == 2
    # A new service instance sees the same draft and review, not a process-only dictionary.
    reloaded = ExperimentDialogue(app.state.experiments)
    assert reloaded.view(session)['can_run']
    confirmed = list(machine_for(app, session, ScriptedModel()).message(content='确认执行'))
    assert confirmed[-1][0] == 'done', confirmed
    assert confirmed[-1][1]['task_result'] == 'succeeded'
    result = draft.result(session)
    assert result['config']['classes'] == {'1': 'A', '2': 'B'}
    assert result['metrics']['test']['n'] == 18
    assert app.state.experiments.artifact(result['experiment_id'], 'report.html').is_file()
    assert any(step['tool'] == 'experiments.run' and step['tool_call_id'] is None for step in store.steps(session))
    repeated = list(machine_for(app, session, ScriptedModel()).message(content='确认执行'))
    assert repeated[-1][1]['task_result'] == 'succeeded'
    queried = list(machine_for(app, session, ScriptedModel()).message(content='查询实验结果'))
    assert queried[-1][1]['task_result'] == 'succeeded'
    assert len(list(app.state.experiments.root.iterdir())) == 1
    # Repeated delivery cannot retrain the same confirmed revision.
    again = draft.run_confirmed(session, '确认执行', str(uuid4()))
    assert again['experiment_id'] == result['experiment_id']
    assert len(list(app.state.experiments.root.iterdir())) == 1


def test_stale_review_negation_and_model_cannot_execute(tmp_path, application):
    body, patch = patch_for(tmp_path)
    store = AgentStore(application.state.experiments.paths.database)
    session = store.create_session()['id']
    draft = application.state.agent_tools.experiment_dialogue
    draft.capture(session, '训练测试 "' + body['train']['paths'][0] + '" "' + body['test']['paths'][0] + '"')
    draft.update(session, DraftUpdate.model_validate(patch))
    with pytest.raises(DataError) as caught:
        draft.run_confirmed(session, '确认执行', 'before-review')
    assert caught.value.code == 'EXPERIMENT_CONFIRMATION_REQUIRED'
    draft.presented(session, 'review-one')
    for text in ('不要确认执行', '确认执行，但把潜变量改成3', '请问能否确认执行？'):
        with pytest.raises(DataError) as caught:
            draft.run_confirmed(session, text, 'later-turn')
        assert caught.value.code == 'EXPERIMENT_CONFIRMATION_REQUIRED'
    draft.update(session, DraftUpdate(expected_revision=1, model={'n_components': 3}))
    with pytest.raises(DataError) as caught:
        draft.run_confirmed(session, '确认执行', 'later-turn')
    assert caught.value.code == 'EXPERIMENT_CONFIRMATION_REQUIRED'
    with pytest.raises(DataError) as caught:
        draft.update(session, DraftUpdate(expected_revision=1, name='stale'))
    assert caught.value.code == 'EXPERIMENT_DRAFT_CONFLICT'
    injected = ScriptedModel(tool('experiments.run', {}))
    events = list(machine_for(application, session, injected).message(content='先讨论一下训练方案'))
    assert events[-1][0] == 'error' and events[-1][1]['code'] == 'EXPERIMENT_TOOL_PROTOCOL'
    assert not list(application.state.experiments.root.glob('*'))


def test_input_inspection_directory_and_session_isolation(tmp_path, application):
    body, patch = patch_for(tmp_path)
    store = AgentStore(application.state.experiments.paths.database)
    first, second = [store.create_session()['id'] for _ in range(2)]
    draft = application.state.agent_tools.experiment_dialogue
    assert draft.handles(first, f'训练数据目录是“{tmp_path}”')
    assert draft.handles(first, f'测试集在“{tmp_path}”')
    assert not draft.handles(first, '对D1训练PLSDA')
    safe = draft.capture(first, f'训练测试目录 "{tmp_path}"')
    assert str(tmp_path) not in safe
    inspected = draft.inspect(first, 'S1')
    assert inspected['file_count'] == 2
    assert 'X' in inspected['file_1_keys'] and inspected['file_1_field_1_shape']
    draft.capture(second, '数值实验')
    assert not draft.inspect(second, 'S1')['available']
    assert draft.view(second)['revision'] == 0
    # Source stage, material names and preprocessing are not inferred from field names.
    assert draft._read(first)['document'] == {}
    draft.cancel(first)
    assert not draft.handles(first, '你好')
    assert draft.handles(first, '继续数值实验')
    assert not draft.handles(first, '对当前数据进行标注')


def test_http_chat_uses_registered_tools_and_no_external_model(tmp_path, application):
    body, patch = patch_for(tmp_path)
    calls = ScriptedModel(tool('experiments.input_inspect', {'source_ref': 'S1'}),
                          tool('experiments.draft_update', patch))
    app, engine = application, application.state.testing_identity
    app.state.agent_llm_factory = lambda session_id: calls
    with TestClient(app) as client:
        client.headers['Authorization'] = 'Bearer ' + engine.token
        created = client.post('/api/v1/agent/sessions', json={})
        assert created.status_code == 200, created.text
        session = created.json()['id']
        url = '/api/v1/agent/sessions/' + session + '/messages'
        response = client.post(url, json={'content': 'PLSDA训练测试 "' + body['train']['paths'][0]
                             + '" "' + body['test']['paths'][0] + '"', 'request_id': str(uuid4())})
        assert response.status_code == 200 and '确认执行' in response.text, response.text
        response = client.post(url, json={'content': '确认执行', 'request_id': str(uuid4())})
        assert 'event: error' not in response.text and '训练与测试已完成' in response.text, response.text
        history = client.get('/api/v1/agent/sessions/' + session + '/history')
        assert history.status_code == 200
        record = app.state.agent_tools.experiment_dialogue.result(session)
        artifact = client.get('/api/v1/experiments/' + record['experiment_id'] + '/artifacts/report.html')
        assert artifact.status_code == 200 and b'<html' in artifact.content
    # Provider names also work when the tool list contains only experiments.
    messages, tools = calls.requests[0]
    _, wire, reverse = _workflow_wire(messages, tools)
    assert all('.' not in entry['function']['name'] for entry in wire)
    assert 'experiments.draft_update' in reverse.values()


def test_changed_source_after_review_is_rejected_before_fit(tmp_path, application, monkeypatch):
    body, patch = patch_for(tmp_path)
    store = AgentStore(application.state.experiments.paths.database)
    session = store.create_session()['id']
    draft = application.state.agent_tools.experiment_dialogue
    draft.capture(session, '训练测试 "' + body['train']['paths'][0] + '" "' + body['test']['paths'][0] + '"')
    draft.update(session, DraftUpdate.model_validate(patch))
    draft.presented(session, 'review-turn')
    file = body['train']['paths'][0]
    with np.load(file) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    arrays['X'][0, 0] += .25
    np.savez(file, **arrays)
    fits = []
    monkeypatch.setattr(ExperimentModel, 'fit', lambda *args: fits.append(True))
    with pytest.raises(DataError) as caught:
        draft.run_confirmed(session, '确认执行', 'next-turn')
    assert caught.value.code == 'EXPERIMENT_INPUT_CHANGED'
    assert not fits
    assert draft.result(session)['status'] == 'failed'
    assert not list(application.state.experiments.root.rglob('model.joblib'))


def test_raw_image_refs_include_implicit_binary_and_explicit_null_saturation(tmp_path, application):
    config = config_for(tmp_path)
    draft = application.state.agent_tools.experiment_dialogue
    session = AgentStore(application.state.experiments.paths.database).create_session()['id']
    patch = {'expected_revision': 0, 'name': '原图显式配对',
             'classes': [{'label': 1, 'name': 'A'}, {'label': 2, 'name': 'B'}],
             'axis': {'kind': 'grid', 'start_nm': 1100., 'stop_nm': 1140., 'step_nm': 5.},
             'model': config['model'], 'preprocessing': [], 'test_usage': 'independent_test'}
    paths = []
    for index, role in enumerate(('train', 'test')):
        header, roi = tmp_path / (role + '.hdr'), tmp_path / (role + '.json')
        header.with_suffix('.img').write_bytes(np.ones((3, 3, 9), dtype=np.uint16).tobytes())
        header.write_text('ENVI\nlines=3\nsamples=3\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\n'
                          'wavelength units=nm\nwavelength={' + ','.join(map(str, config['wavelengths_nm'])) + '}\n')
        roi.write_text('{}')
        paths.extend((str(header), str(roi)))
        patch[role] = {'kind': 'roi_images', 'members': [{'header_ref': 'S' + str(index*2+1), 'roi_ref': 'S' + str(index*2+2), 'sample_id': role}],
                       'neighborhood': 1, 'wavelength_unit': 'nm', 'mapping_window_nm': 5., 'nearest_tolerance_nm': 5.,
                       'quality': {'min_mean': .02, 'min_std': .002, 'max_zero_fraction': .05, 'saturation': None}}
    draft.capture(session, '数值实验，原图与ROI ' + ' '.join('"' + value + '"' for value in paths))
    view = draft.update(session, DraftUpdate.model_validate(patch))
    assert view['can_run'], view
    draft.presented(session, 'review-raw')
    record = draft._read(session)
    assert record['document']['train']['quality']['saturation'] is None
    hashes = json.loads(record['review_sources_json'])
    assert len(hashes) == 6 and any(value.endswith('.img') for value in hashes)
    assert '中心像元' in view['plan'] and str(tmp_path) not in view['plan']
