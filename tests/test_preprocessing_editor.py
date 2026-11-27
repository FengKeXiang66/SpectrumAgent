"""Conversation forms edit real shared drafts without starting numerical work."""
import json
from uuid import uuid4

import numpy as np
from fastapi.testclient import TestClient

from test_experiment_conversation import application, workspace, patch_for, machine_for, tool
from test_data_intake import source
from backend.database import connect_database
from spectrumagent.agent.state import AgentStore
from spectrumagent.agent.llm import ChatResult
from spectrumagent.agent.preprocessing_editor import PREFIX
from spectrumagent.agent.tools.experiments import DraftUpdate
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.data import DataError


def client_session(app):
    client = TestClient(app, headers={'Authorization': 'Bearer '+app.state.testing_identity.token})
    sid = client.post('/api/v1/agent/sessions', json={'scope': {'kind': 'global'}}).json()['id']
    return client, sid


def submit(client, sid, body):
    body = {'form_id': str(uuid4()), **body}
    response = client.post(f'/api/v1/agent/sessions/{sid}/messages', json={
        'content': PREFIX+json.dumps(body), 'request_id': str(uuid4())})
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    return events[-1], body


def read(client, sid, kind, cube=None):
    response = client.get(f'/api/v1/agent/sessions/{sid}/preprocessing-editor', params={
        'kind': kind, **({'cube_id': cube} if cube else {})})
    assert response.status_code == 200, response.text
    return response.json()


def offline(app):
    def unavailable(sid):
        class Model:
            def chat(self, *args, **kwargs):
                raise AssertionError('form commands must not call a model')
        return Model()
    app.state.agent_llm_factory = unavailable


def test_classification_form_edits_same_draft_invalidates_review_and_rejects_stale_revision(application, tmp_path):
    offline(application)
    client, sid = client_session(application)
    dialogue = application.state.agent_tools.experiment_dialogue
    _, patch = patch_for(tmp_path)
    dialogue.capture(sid, '训练数据和测试数据')
    dialogue.update(sid, DraftUpdate.model_validate(patch))
    before = read(client, sid, 'classification')
    # Reading metadata does not create a round or reveal local data paths.
    assert str(tmp_path) not in json.dumps(before)
    assert not AgentStore(dialogue.database).rounds(sid)
    dialogue.presented(sid, 'review-before-edit')
    steps = [{'op': 'savgol', 'window': 5, 'polyorder': 2, 'derivative': 1, 'delta_nm': 5.0}]
    answer, body = submit(client, sid, dict(kind='classification', action='update', draft_id=sid,
        expected_revision=before['revision'], steps=steps))
    assert answer['reply_status'] == 'replied', answer
    after = read(client, sid, 'classification')
    assert after['steps'] == steps and after['revision'] > before['revision']
    assert after['last_form_id'] == body['form_id'] and after['last_form_ok']
    assert dialogue._read(sid)['reviewed_revision'] is None
    assert not dialogue.tasks.active(sid)
    stale, _ = submit(client, sid, dict(kind='classification', action='update', draft_id=sid,
        expected_revision=before['revision'], steps=[]))
    assert stale['reply_status'] == 'needs_input'
    assert read(client, sid, 'classification')['steps'] == steps
    # A second session cannot submit a form bound to the first session.
    other = client.post('/api/v1/agent/sessions', json={}).json()['id']
    rejected, _ = submit(client, other, dict(kind='classification', action='update', draft_id=sid,
        expected_revision=after['revision'], steps=[]))
    assert rejected['reply_status'] == 'needs_input'
    history = client.get(f'/api/v1/agent/sessions/{sid}/history').json()['events']
    assert any(e['kind'] == 'step' and e['payload'].get('tool') == 'preprocess.form_update' for e in history)
    assert client.get(f'/api/v1/agent/sessions/{sid}/preprocessing-editor?kind=tool').status_code in {400, 422}


def test_recipe_form_shared_edits_axis_metadata_and_explicit_save_do_not_process(application, tmp_path):
    offline(application)
    client, sid = client_session(application)
    runner = application.state.preprocess_runner
    images, _ = source(tmp_path, 1)
    cube = str(application.state.dataset_registry.import_path(str(images/'plastic0.hdr')).datasets[0].id)
    empty = read(client, sid, 'recipe', cube)
    assert empty['draft_id'] is None
    assert empty['bands'] == 6 and len(empty['axis']) == 6
    submit(client, sid, dict(kind='recipe', action='open'))
    draft = read(client, sid, 'recipe')
    steps = [{'op': 'snv', 'version': 1, 'params': {'zero_std': 'zeros'}}]
    answer, _ = submit(client, sid, dict(kind='recipe', action='update', draft_id=draft['draft_id'],
        expected_revision=draft['revision'], steps=steps, name='对话配方', axis_cube_id=cube))
    assert answer['reply_status'] == 'replied', answer
    assert runner.drafts.get(sid)['pipeline']['steps'] == steps
    # Natural-language tool edits share this exact draft, and invalidate old forms.
    from spectrumagent.agent.tool_context import owner_session
    token = owner_session.set(sid)
    try:
        application.state.agent_tools.invoke('preprocess.draft_update', dict(draft_id=draft['draft_id'],
            expected_revision=draft['revision']+1, name='改名后配方'))
    finally:
        owner_session.reset(token)
    rejected, _ = submit(client, sid, dict(kind='recipe', action='update', draft_id=draft['draft_id'],
        expected_revision=draft['revision']+1, steps=[]))
    assert rejected['reply_status'] == 'needs_input'
    current = read(client, sid, 'recipe')
    saved, _ = submit(client, sid, dict(kind='recipe', action='save', draft_id=current['draft_id'],
        expected_revision=current['revision'], recipe_id=None, name=current['name']))
    assert saved['reply_status'] == 'replied', saved
    recipe = read(client, sid, 'recipe')['recipe_id']
    assert recipe and runner.recipes.get(recipe)['name'] == '改名后配方'
    with connect_database(runner.database) as db:
        assert db.execute('SELECT count(*) FROM preprocess_run').fetchone()[0] == 0
    # Opening a different plan makes the previous form invalid even with its revision.
    submit(client, sid, dict(kind='recipe', action='open'))
    stale, _ = submit(client, sid, dict(kind='recipe', action='update', draft_id=current['draft_id'],
        expected_revision=current['revision'], steps=[]))
    assert stale['reply_status'] == 'needs_input'


def test_committed_classification_edit_is_reported_even_if_presentation_fails(application, tmp_path, monkeypatch):
    offline(application)
    client, sid = client_session(application)
    dialogue = application.state.agent_tools.experiment_dialogue
    _, patch = patch_for(tmp_path)
    dialogue.capture(sid, '训练数据和测试数据')
    dialogue.update(sid, DraftUpdate.model_validate(patch))
    before = read(client, sid, 'classification')

    def unavailable(*args, **kwargs):
        raise DataError('PRESENTATION_UNAVAILABLE', 'synthetic presentation failure')
    monkeypatch.setattr(dialogue, 'draft_presentation', unavailable)
    answer, body = submit(client, sid, dict(kind='classification', action='update', draft_id=sid,
        expected_revision=before['revision'], steps=[{'op': 'snv'}]))
    assert answer['reply_status'] == 'replied'
    assert '参数已保存' in answer['content'] and 'snv' in answer['content']
    assert read(client, sid, 'classification')['last_form_id'] == body['form_id']
    assert read(client, sid, 'classification')['last_form_ok']


def test_forms_reject_tool_injection_and_duplicate_http_request_replays(application):
    offline(application)
    client, sid = client_session(application)
    answer, _ = submit(client, sid, dict(kind='recipe', action='open', tool='workspace.preprocess'))
    assert answer['reply_status'] == 'needs_input'
    assert read(client, sid, 'recipe')['draft_id'] is None
    body = dict(content=PREFIX+json.dumps(dict(kind='recipe', action='open', form_id=str(uuid4()))), request_id=str(uuid4()))
    endpoint = f'/api/v1/agent/sessions/{sid}/messages'
    first = client.post(endpoint, json=body)
    draft = read(client, sid, 'recipe')['draft_id']
    second = client.post(endpoint, json=body)
    assert first.status_code == second.status_code == 200
    assert first.text == second.text
    assert read(client, sid, 'recipe')['draft_id'] == draft


def test_recipe_form_then_natural_language_edit_does_not_touch_existing_classification(application, tmp_path):
    offline(application)
    client, sid = client_session(application)
    dialogue = application.state.agent_tools.experiment_dialogue
    _, patch = patch_for(tmp_path)
    dialogue.capture(sid, '训练数据和测试数据')
    dialogue.update(sid, DraftUpdate.model_validate(patch))
    classification = dialogue._read(sid)['document']['preprocessing']
    submit(client, sid, dict(kind='recipe', action='open'))
    draft = read(client, sid, 'recipe')
    submit(client, sid, dict(kind='recipe', action='update', draft_id=draft['draft_id'], expected_revision=draft['revision'],
        steps=[{'op': 'sg_smooth', 'version': 1, 'params': {'window': 3, 'polyorder': 1, 'mode': 'interp'}}]))
    current = read(client, sid, 'recipe')

    class Model:
        def __init__(self):
            self.replies = [tool('preprocess.draft_update', dict(draft_id=current['draft_id'],
                expected_revision=current['revision'], step_updates=[{'step_no': 1, 'window': 5}])),
                ChatResult(content='SG 窗口已改为 5。', finish_reason='stop')]
        def route_chat(self, *args, **kwargs):
            raise AssertionError('the recipe form already established the editing domain')
        def chat(self, *args): return self.replies.pop(0)

    events = list(machine_for(application, sid, Model()).message(content='把 SG 窗口改为 5'))
    assert any(kind == 'step' and p['tool'] == 'preprocess.draft_update' and p['status'] == 'ok' for kind, p in events)
    assert read(client, sid, 'recipe')['steps'][0]['params']['window'] == 5
    assert dialogue._read(sid)['document']['preprocessing'] == classification


def test_recipe_form_to_conversation_preprocessing_and_pls_regression(application, tmp_path):
    offline(application)
    client, sid = client_session(application)
    registry, sessions = application.state.dataset_registry, application.state.annotation_sessions
    runner = application.state.preprocess_runner
    images, _ = source(tmp_path, 6)
    cubes = [str(registry.import_path(str(images/f'plastic{i}.hdr')).datasets[0].id) for i in range(6)]
    with connect_database(runner.database) as db:
        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cubes[0],)).fetchone()[0]
    label = LabelStore(runner.database).ensure_names(project, ['PE'])[0]['id']
    for cube in cubes:
        application.state.segmentation_resources.prepare(cube, Parameters(n_segments=4, pca_components=3))
        sessions.edit(cube, np.ones((8, 8), bool), action='confirm', label_id=label)
        sessions.save(cube)
    submit(client, sid, dict(kind='recipe', action='open'))
    draft = read(client, sid, 'recipe')
    submit(client, sid, dict(kind='recipe', action='update', draft_id=draft['draft_id'],
        expected_revision=draft['revision'], steps=[], name='回归基线'))
    draft = read(client, sid, 'recipe')
    submit(client, sid, dict(kind='recipe', action='save', draft_id=draft['draft_id'],
        expected_revision=draft['revision'], recipe_id=None, name=draft['name']))
    recipe_id = read(client, sid, 'recipe')['recipe_id']

    class Model:
        def __init__(self, response): self.responses = [response, ChatResult(content='已完成。', finish_reason='stop')]
        def chat(self, *args): return self.responses.pop(0)
        def route_chat(self, *args, **kwargs):
            return ChatResult(content='{"intent":"annotation_workspace","explain_result":false,"confidence":"high"}', finish_reason='stop')

    def call(name, args, text):
        model = Model(tool(name, args))
        events = list(machine_for(application, sid, model).message(content=text))
        check = next((payload for kind, payload in events if kind == 'human_check'), None)
        if check:
            # Training retains its existing explicit review/approval boundary.
            assert name == 'modeling.regress'
            events += list(machine_for(application, sid, model).message(check_id=check['check_id'], decision='approve'))
        successes = [p['result_summary'] for kind, p in events if kind == 'step' and p['tool'] == name and p['status'] == 'ok']
        assert successes, events
        return successes[-1]

    call('datasets.list', {}, '列出已登记数据集')
    processed = call('workspace.preprocess', dict(cube_ids=cubes, recipe_id=recipe_id),
                     '使用配方“回归基线”，对样品 '+ '、'.join(cubes)+' 执行预处理')
    assert processed['succeeded'] == 6, processed
    state = call('workspace.current', {}, '查看当前样品处理状态和配方')
    runs = [state[f'sample_{i}_run_id'] for i in range(1, 7)]
    assert all(runs)
    with TestClient(application, headers={'Authorization': 'Bearer '+application.state.testing_identity.token}) as second:
        members = second.get('/api/v1/preprocess/current').json()['members']
    assert all(row['status'] == 'ready' and row['run_id'] for row in members)
    schema = call('labels.continuous_create', dict(project_id=project, name='含量', tree_path='含量', unit='%'), '创建回归连续量字段含量，单位百分比')
    for i, cube in enumerate(cubes):
        call('modeling.target_set', dict(cube_id=cube, schema_id=schema['id'], value=float(i+1)), f'将样品 {cube} 的含量测量值设为 {i+1}')
    trained = call('modeling.regress', dict(preprocess_run_ids=runs, target_schema_id=schema['id'],
        cv_folds=2, n_components=1, max_components=1), '使用上述已处理样品和含量字段训练 PLS 回归，潜变量 1，训练内两折验证')
    assert trained['status'] == 'succeeded', trained
