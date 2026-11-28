"""Conversation integration and execution guards; no external model credentials."""
import copy
import json
from pathlib import Path
import time
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
from backend.database import connect_database


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
    yield app
    for task_id, row in app.state.agent_tools.experiment_dialogue.tasks.rows.items():
        wait_task(app.state.agent_tools.experiment_dialogue.tasks, row['session_id'], task_id)


def wait_task(tasks, session, task_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        row = tasks.view(session, task_id)
        if row['status'] in {'succeeded', 'failed', 'cancelled'}:
            return row
        time.sleep(.02)
    raise AssertionError('后台实验未及时结束')


def machine_for(app, session, model):
    store = AgentStore(app.state.experiments.paths.database)
    return StateMachine(store, session, model, ScopedToolRegistry(
        app.state.agent_tools, app.state.agent_sessions, session))


def test_metric_update_keeps_same_reply_explanation(application):
    from spectrumagent.agent.experiment_flow import generate

    store = AgentStore(application.state.experiments.paths.database)
    session = store.create_session()['id']
    update = tool('experiments.draft_update', {'expected_revision': 0, 'additional_metrics': ['kappa']})
    path = r'E:\private\data.npz'
    update.content = f'已加入 Kappa。AUC 尚未实现。输入位置：{path}'
    model = ScriptedModel(update)
    machine = machine_for(application, session, model)

    events = list(generate(machine, '请附加 Kappa 和 AUC。'))

    card = next(payload['result_summary'] for kind, payload in events
                if kind == 'step' and payload['tool'] == 'experiments.draft_presentation')
    assert card['draft_notes'] == '已加入 Kappa。AUC 尚未实现。输入位置：本地输入源'
    assert events[-1][0] == 'clarify'
    assert events[-1][1]['question'].startswith(card['draft_notes'] + '\n\n当前实验方案')
    assert path not in str(events)
    dialogue = application.state.agent_tools.experiment_dialogue
    assert dialogue._read(session)['document']['additional_metrics'] == ['kappa']


def test_unapplied_metric_report_is_shown_and_is_not_part_of_the_draft(application):
    from spectrumagent.agent.experiment_flow import generate

    store = AgentStore(application.state.experiments.paths.database)
    session = store.create_session()['id']
    model = ScriptedModel(tool('experiments.draft_update', {
        'expected_revision': 0, 'additional_metrics': ['kappa'],
        'unapplied_requests': [{'topic': 'metrics', 'requested': 'AUC', 'reason': '当前未实现'}],
    }))
    events = list(generate(machine_for(application, session, model), '加上 kappa 和 AUC'))
    card = next(payload['result_summary'] for kind, payload in events
                if kind == 'step' and payload['tool'] == 'experiments.draft_presentation')
    assert '本轮未生效请求' in events[-1][1]['question']
    assert all(value in card['draft_notes'] for value in ('AUC', '未实现', 'balanced_accuracy'))
    dialogue = application.state.agent_tools.experiment_dialogue
    assert dialogue._read(session)['document'] == {'additional_metrics': ['kappa']}


def test_multi_turn_partial_patch_review_execute_and_query(tmp_path, application):
    body, patch = patch_for(tmp_path)
    app = application
    store = AgentStore(app.state.experiments.paths.database)
    session = store.create_session()['id']
    with connect_database(app.state.experiments.paths.database) as db:
        db.execute('UPDATE agent_session SET title=? WHERE id=?',('仅侧栏显示的会话标题',session))
    partial = copy.deepcopy(patch)
    partial['preprocessing'] = [{'op': 'savgol', 'derivative': 2}]
    model = ScriptedModel(tool('experiments.draft_update', partial),
        tool('experiments.draft_update', {'expected_revision': 1,
             'preprocessing': [{'op': 'savgol', 'derivative': 2, 'window': 5, 'polyorder': 2, 'delta_nm': 5.}, {'op': 'center'}]}))
    first = list(machine_for(app, session, model).message(content='PLSDA训练与测试，训练数据“' + body['train']['paths'][0]
                 + '”，测试数据“' + body['test']['paths'][0] + '”，用SG二阶导数，训练后输出实验结果。'))
    assert first[-1][0] == 'clarify', first
    assert '窗口长度' in first[-1][1]['question']
    assert not list(app.state.experiments.root.glob('*'))
    sent = json.dumps(model.requests[0][0], ensure_ascii=False)
    assert str(tmp_path) not in sent and 'S1' in sent
    second = list(machine_for(app, session, model).message(content='窗口5、多项式2阶、步长5nm，再中心化。'))
    assert second[-1][0] == 'clarify', second
    assert '确认执行' in second[-1][1]['question']
    draft = app.state.agent_tools.experiment_dialogue
    assert '仅侧栏显示的会话标题' not in json.dumps(model.requests,ensure_ascii=False)
    assert draft._read(session)['document']['train']['source_refs'] == ['S1']
    assert draft._read(session)['document']['model']['n_components'] == 2
    # A new service instance sees the same draft and review, not a process-only dictionary.
    reloaded = ExperimentDialogue(app.state.experiments)
    assert reloaded.view(session)['can_run']
    confirmed = list(machine_for(app, session, ScriptedModel()).message(content='确认执行'))
    assert confirmed[-1][0] == 'done', confirmed
    assert confirmed[-1][1]['task_result'] == 'working'
    task = wait_task(draft.tasks, session, draft.tasks.latest(session))
    assert task['status'] == 'succeeded', task
    result = draft.result(session)
    assert result['config']['classes'] == {'1': 'A', '2': 'B'}
    assert result['metrics']['test']['n'] == 18
    assert app.state.experiments.artifact(result['experiment_id'], 'report.html').is_file()
    assert any(step['tool'] == 'experiments.run' and step['tool_call_id'] is None for step in store.steps(session))
    repeated = list(machine_for(app, session, ScriptedModel()).message(content='确认执行'))
    assert repeated[-1][0] == 'clarify' and '没有有效的待确认方案' in repeated[-1][1]['question']
    assert draft.tasks.latest(session) == task['task_id']
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


def test_split_conflict_blocks_confirmation_and_survives_export(tmp_path, application):
    body, patch = patch_for(tmp_path)
    draft = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(draft.database).create_session()['id']
    path = body['train']['paths'][0]
    draft.capture(owner, f'训练和测试目录均使用 "{path}"')
    patch['test']['source_refs'] = ['S1']
    draft.update(owner, DraftUpdate.model_validate(patch))
    with connect_database(draft.database) as db:
        db.execute('INSERT INTO inference_draft(session_id) VALUES (?)', (owner,))
        draft.set_confirmation(db, owner, 'inference', 1, 'older-inference-plan')
    blocked = draft.presented(owner, 'independent')
    assert not blocked['can_run'] and '同一文件 train.npz' in blocked['plan']
    assert blocked['split_checks']['duplicate_test_spectra'] is None
    assert draft.confirmation(owner) is None
    denied = list(machine_for(application, owner, ScriptedModel()).message(content='确认执行'))
    assert denied[-1][0] == 'clarify' and draft.tasks.latest(owner) is None
    change = ScriptedModel(tool('experiments.draft_update', {'expected_revision':1, 'test_usage':'development_regression'}))
    revised = list(machine_for(application, owner, change).message(content='改作开发复现核验'))
    assert revised[-1][0] == 'clarify' and '确认执行' in revised[-1][1]['question']
    review = draft.presented(owner, 'regression')
    assert review['can_run'] and review['split_checks']['conflicts'] == blocked['split_checks']['conflicts']
    assert '实物独立性未知' in review['plan']
    list(machine_for(application, owner, ScriptedModel()).message(content='确认执行'))
    task = wait_task(draft.tasks, owner, draft.tasks.latest(owner))
    assert task['status'] == 'succeeded', task
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer ' + application.state.testing_identity.token
        prefix = f'/api/v1/agent/sessions/{owner}/experiments/{task["task_id"]}'
        result = client.get(prefix+'/result').json()
        response = client.get(prefix+'/export/report')
        assert response.status_code == 200
        report = response.content.decode('utf-8')
    checks = result['split_checks']
    assert checks['conflicts'] == review['split_checks']['conflicts']
    assert checks['status'] == 'completed' and checks['duplicate_test_spectra'] == 36
    assert '测试侧有 36 条光谱' in result['split_check_text'] and '测试侧有 36 条光谱' in report
    assert '实物独立性未知' in report
    assert 'data-split-warning' not in report


def test_split_conflict_inside_directories_never_exposes_full_paths_to_model(tmp_path,application):
    training = tmp_path/'secret parent train'
    training.mkdir()
    _,patch = patch_for(training)
    holdout = tmp_path/'secret parent test'
    holdout.mkdir()
    (holdout/'copy with spaces.npz').write_bytes((training/'train.npz').read_bytes())
    (training/'test.npz').unlink()
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    create = ScriptedModel(tool('experiments.draft_update',patch))
    message = f'PLS-DA 训练目录在 "{training}"，测试目录在 "{holdout}"'
    first = list(machine_for(application,owner,create).message(content=message))
    assert 'train.npz 与 copy with spaces.npz' in first[-1][1]['question']
    rename = ScriptedModel(tool('experiments.draft_update',{'expected_revision':1,'name':'预查'}))
    list(machine_for(application,owner,rename).message(content='改一下实验名称为预查'))
    outbound = json.dumps(rename.requests[0][0],ensure_ascii=False)
    assert 'train.npz 与 copy with spaces.npz' in outbound
    assert all(root not in outbound for root in ['secret parent train','secret parent test',tmp_path.as_posix()])
    assert '\\\\secret parent' not in outbound


def test_independent_exact_duplicates_warn_in_result_and_exports(tmp_path,application):
    body,patch = patch_for(tmp_path)
    train,test = (Path(body[role]['paths'][0]) for role in ('train','test'))
    with np.load(train) as original, np.load(test) as held:
        values = {key:held[key].copy() for key in held.files}
        values['X'][0] = original['X'][0]
    np.savez(test,**values)
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    base.capture(owner,f'训练测试 "{train}" "{test}"')
    base.update(owner,DraftUpdate.model_validate(patch))
    base.presented(owner,'review')
    recorded = base.run_confirmed(owner,'确认执行','run')
    identifier = recorded['experiment_id']
    from spectrumagent.experiments.results import ExperimentResults
    results = ExperimentResults(base)
    warning = results.summary(owner,experiment_id=identifier)['split_warning']
    assert '独立测试中存在与训练侧精确相同的光谱（1 条）' in warning
    report = results.export(owner,None,'report',experiment_id=identifier).decode()
    assert report.count('data-split-warning="true"') == 1 and warning in report
    from spectrumagent.experiments.service import write_json
    del recorded['artifacts']['test_processed.png']
    write_json(base.service.folder(identifier)/'result.json',recorded)
    with pytest.raises(DataError) as error:
        results.export(owner,None,'report',experiment_id=identifier)
    assert error.value.code=='EXPERIMENT_ARTIFACT_NOT_FOUND'


def test_preprocessing_edit_retries_once_preserves_steps_and_shows_diff(tmp_path, application):
    body, patch = patch_for(tmp_path)
    draft = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(draft.database).create_session()['id']
    train, test = body['train']['paths'][0], body['test']['paths'][0]
    draft.capture(owner, f'训练数据 "{train}" 测试数据 "{test}"')
    patch['preprocessing'] = [{'op':'savgol','window':7,'polyorder':2,'derivative':2,'delta_nm':5.},
                              {'op':'l2'}, {'op':'center'}]
    draft.update(owner, DraftUpdate.model_validate(patch))
    draft.presented(owner, 'prior-review')

    def edit(window, revision=1):
        return tool('experiments.draft_update', {'expected_revision':revision, 'preprocessing_edit':
            {'action':'update','index':1,'step':{'op':'savgol','window':window}}})

    model = ScriptedModel(edit('5'), edit(5))
    result = list(machine_for(application,owner,model).message(content='分析一下为什么准确率低，把 SG 窗口改成 5 再训一次'))
    assert result[-1][0] == 'clarify', result
    assert 'window 从 7 改为 5' in result[-1][1]['question'] and '确认执行' in result[-1][1]['question']
    assert [step['op'] for step in draft._read(owner)['document']['preprocessing']] == ['savgol','l2','center']
    correction_message = next(message['content'] for message in model.requests[1][0] if '上一组工具参数' in message.get('content',''))
    assert 'preprocessing_edit.step.savgol.window' in correction_message
    model = ScriptedModel(edit('7',2), edit('9',2))
    result = list(machine_for(application,owner,model).message(content='把 SG 窗口改成 7'))
    assert result[-1][0] == 'error' and result[-1][1]['code'] == 'TOOL_ARGS_INVALID'
    assert len(model.requests) == 2 and draft._read(owner)['revision'] == 2
    draft.update(owner, DraftUpdate(expected_revision=2, preprocessing_edit={'action':'remove','index':2}))
    assert [item['op'] for item in draft._read(owner)['document']['preprocessing']] == ['savgol','center']

    other = AgentStore(draft.database).create_session()['id']
    model = ScriptedModel(tool('experiments.draft_update', patch))
    new = list(machine_for(application,other,model).message(content=f'重新训练，训练数据在 "{train}" 测试数据在 "{test}"'))
    assert new[-1][0] == 'clarify' and '确认执行' in new[-1][1]['question'], new


def test_tool_invalid_arguments_keep_schema_paths_without_echoing_unknown_fields():
    from pydantic import ValidationError
    from spectrumagent.data.validation import validation_error, safe_error

    with pytest.raises(ValidationError) as invalid:
        DraftUpdate.model_validate({'expected_revision':5,
            'axis':{'kind':'grid','start_nm':1100,'stop_nm':1650,'workstation_private_key':123},
            'train':{'kind':'roi_images','quality':{'min_std':'private_value'}},
            'model':{'n_components':'9'},'preprocessing':[{'op':'savgol','derivative':'2'}]})
    summary = safe_error(validation_error('TOOL_ARGS_INVALID',invalid.value))
    locations = {value for field,value in summary.items() if field.endswith('_location')}
    assert {'axis.grid.step_nm','axis.grid.field','train.roi_images.quality.min_std',
            'model.n_components','preprocessing.0.savgol.derivative'} <= locations
    assert 'workstation_private_key' not in str(summary) and 'private_value' not in str(summary)


def test_retraining_finished_draft_uses_new_focused_archive(application,tmp_path):
    draft = application.state.agent_tools.experiment_dialogue
    body, patch = patch_for(tmp_path)
    owner = AgentStore(draft.database).create_session()['id']
    draft.capture(owner, '训练测试 "' + body['train']['paths'][0] + '" "' + body['test']['paths'][0] + '"')
    draft.update(owner, DraftUpdate.model_validate(patch))
    draft.presented(owner, 'earlier')
    first = draft.run_confirmed(owner, '确认执行', 'run-first')
    body['name'] = '另一项归档'
    body['preprocessing'] = [{'op':'l2'}]
    from spectrumagent.experiments.schema import ExperimentConfig
    second = draft.service.run(ExperimentConfig.model_validate(body))
    draft.select(owner, second['experiment_id'])
    events = list(machine_for(application,owner,ScriptedModel()).message(content='换个预处理再训一次'))
    assert events[-1][0] == 'clarify', events
    text = events[-1][1]['question']
    assert second['experiment_id'] in text and first['experiment_id'] not in text and '另一项归档' in text
    assert [step['op'] for step in draft._read(owner)['document']['preprocessing']] == ['l2']
    assert draft.confirmation(owner) is None


def test_change_one_operator_and_explicitly_replace_multiple_steps(application,tmp_path):
    body, patch = patch_for(tmp_path)
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    base.capture(owner, '训练测试 "'+body['train']['paths'][0]+'" "'+body['test']['paths'][0]+'"')
    patch['preprocessing'] = [{'op':'l2'},{'op':'center'}]
    base.update(owner,DraftUpdate.model_validate(patch))
    single = ScriptedModel(tool('experiments.draft_update',{'expected_revision':1,'preprocessing_edit':
        {'action':'update','index':1,'step':{'op':'snv'}}}))
    events = list(machine_for(application,owner,single).message(content='把第 1 步 L2 换成 SNV'))
    assert events[-1][0]=='clarify' and '移除原第 1 步 l2' in events[-1][1]['question']
    card = next(data['result_summary'] for kind,data in events
                if kind=='step' and data['tool']=='experiments.draft_presentation')
    assert card['draft_ready'] and '移除原第 1 步 l2' in card['draft_changes'] and '加入第 1 步 snv' in card['draft_changes']
    assert [row['op'] for row in base._read(owner)['document']['preprocessing']]==['snv','center']
    multiple = ScriptedModel(tool('experiments.draft_update',{'expected_revision':2,
        'preprocessing':[{'op':'l2'},{'op':'standard_scale'}]}))
    events = list(machine_for(application,owner,multiple).message(content='把预处理改成 L2 + 标准化'))
    assert events[-1][0]=='clarify'
    assert [row['op'] for row in base._read(owner)['document']['preprocessing']]==['l2','standard_scale']


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
        assert 'event: error' not in response.text and '实验任务已受理' in response.text, response.text
        tasks = app.state.agent_tools.experiment_dialogue.tasks
        task_id = tasks.latest(session)
        task = wait_task(tasks, session, task_id)
        assert task['status'] == 'succeeded', task
        task_url = '/api/v1/agent/sessions/' + session + '/experiments/' + task_id
        assert client.get(task_url).json()['completed_phases'] == ['checking','preparing','training','testing','reporting']
        assert client.post(task_url + '/cancel').json()['status'] == 'succeeded'
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
        header.with_suffix('.img').write_bytes(np.full((3, 3, 9), index+1, dtype=np.uint16).tobytes())
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
