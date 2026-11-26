"""Chat label forms and named requests execute locally, with atomic writes."""
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from test_data_intake import application, source, session, workspace
from test_experiment_conversation import ScriptedModel
from backend.database import connect_database
from spectrumagent.annotation.labels import LabelStore, SimpleLabelRequest
from spectrumagent.data import DataError


def rows(app):
    with connect_database(app.state.experiments.paths.database) as db:
        return db.execute('SELECT id,code,name,color_hex,is_background FROM label WHERE deleted_at IS NULL ORDER BY sort_order').fetchall()


@pytest.mark.parametrize('text', [
    '为刚导入的数据创建标签，标签名称为：PE、PET、PP',
    '创建标签：PE、PET、PP',
    '创建标签 PE，PET，PP',
    '帮我新建标签：PE\nPET\nPP',
])
def test_chat_creates_explicit_names_without_model_or_pixel_assignment(application, tmp_path, text):
    images, _ = source(tmp_path, 1)
    _, send = session(application)
    reply, _ = send(f'导入未标注的数据 "{images}"')
    assert reply['data_intake']['imported_count'] == 1
    reply, events = send(text)
    assert [r[2] for r in rows(application)] == ['PE', 'PET', 'PP'], reply
    assert len({r[3] for r in rows(application)}) == 3
    assert not any(r[4] for r in rows(application))
    assert '新增 3 个' in reply['content']
    assert any(kind == 'step' and data['tool'] == 'labels.create_many' for kind, data in events)
    with connect_database(application.state.experiments.paths.database) as db:
        assert db.execute('SELECT count(*) FROM sample_label').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM annotation_version').fetchone()[0] == 0


def test_chat_opens_form_before_import_and_form_submit_reuses_names(application):
    _, send = session(application)
    reply, _ = send('请帮我创建标签')
    card = reply['data_intake']
    assert card['stage'] == 'labels' and card['label_form_open']
    assert not rows(application)
    command = f'创建导入标签 {card["id"]} '+json.dumps(['PE', 'PET', 'PP', 'PE'])
    reply, _ = send(command)
    assert len(rows(application)) == 3 and len(reply['data_intake']['labels']) == 3
    ids = [r[0] for r in rows(application)]
    reply, _ = send(command)
    assert '新增 0 个，复用 3 个' in reply['content']
    assert [r[0] for r in rows(application)] == ids


def test_asking_about_labels_does_not_create_a_label(application):
    from test_experiment_conversation import machine_for
    sid, _ = session(application)
    machine = machine_for(application, sid, ScriptedModel())
    for content in ['创建标签是什么意思？', '如何创建标签', '不要创建标签']:
        assert application.state.agent_tools.data_intake.route(machine, content) is None
    assert not rows(application)


@pytest.mark.parametrize('payload', ['[]', '[""]', '["PE",42]', '["PE","bad\\tname"]', '["'+'x'*101+'"]', '{invalid'])
def test_invalid_form_payload_does_not_write_or_call_model(application, payload):
    _, send = session(application)
    reply, _ = send('创建标签')
    reply, _ = send(f'创建导入标签 {reply["data_intake"]["id"]} {payload}')
    assert '标签创建未完成' in reply['content']
    assert reply['data_intake']['label_form_open']
    assert not rows(application)


def test_old_form_cannot_create_labels_for_a_new_batch(application, tmp_path):
    _, send = session(application)
    first, _ = send('创建标签')
    images, _ = source(tmp_path, 1)
    send(f'导入未标注的数据 "{images}"')
    reply, _ = send(f'创建导入标签 {first["data_intake"]["id"]} ["PE"]')
    assert '失效' in reply['content'] and not rows(application)


def test_batch_rolls_back_on_mid_write_failure_and_concurrent_requests_reuse(application, monkeypatch):
    import spectrumagent.annotation.labels as labels_module
    database = application.state.experiments.paths.database
    project = LabelStore(database).projects()[0]['id']
    original = labels_module.insert_label
    def fail_second(db, request, *, origin):
        if request.name == 'PET':
            raise DataError('TEST_WRITE_FAILURE', 'synthetic failed second insert')
        return original(db, request, origin=origin)
    monkeypatch.setattr(labels_module, 'insert_label', fail_second)
    with pytest.raises(DataError):
        LabelStore(database).ensure_names(project, ['PE', 'PET', 'PP'])
    assert not rows(application)
    monkeypatch.setattr(labels_module, 'insert_label', original)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: LabelStore(database).ensure_names(project, ['PE', 'PET', 'PP']), range(2)))
    assert len(rows(application)) == 3
    assert sum(not label['existing'] for result in results for label in result) == 3


def test_http_form_submission_and_history_work_with_an_offline_model(application):
    application.state.agent_llm_factory = lambda sid: ScriptedModel()
    identity = application.state.testing_identity
    with TestClient(application, headers={'Authorization': 'Bearer '+identity.token}) as client:
        sid = client.post('/api/v1/agent/sessions', json={'scope': {'kind': 'global'}}).json()['id']
        endpoint = f'/api/v1/agent/sessions/{sid}/messages'
        def post(body):
            response = client.post(endpoint, json=body)
            assert response.status_code == 200, response.text
            return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')][-1]
        card = post({'content': '创建标签', 'request_id': str(uuid4())})['data_intake']
        body = {'content': f'创建导入标签 {card["id"]} ["PE","PET","PP"]', 'request_id': str(uuid4())}
        created = post(body)
        repeated = post(body)
        assert created == repeated and len(rows(application)) == 3
        history = client.get(f'/api/v1/agent/sessions/{sid}/history').json()['events']
        assert any(e['kind'] == 'done' and len(e['payload'].get('data_intake', {}).get('labels', [])) == 3 for e in history)


def test_http_eleven_image_import_then_named_labels_without_selecting_a_cube(application, tmp_path):
    """A project label request must precede generic dataset clarification."""
    from spectrumagent.agent.state import AgentStore

    images, _ = source(tmp_path, 11)
    model = ScriptedModel()
    application.state.agent_llm_factory = lambda sid: model
    database = application.state.experiments.paths.database
    store = AgentStore(database)
    identity = application.state.testing_identity
    with TestClient(application, headers={'Authorization': 'Bearer '+identity.token}) as client:
        sid = client.post('/api/v1/agent/sessions', json={'scope': {'kind': 'global'}}).json()['id']
        endpoint = f'/api/v1/agent/sessions/{sid}/messages'

        def post(content):
            response = client.post(endpoint, json={'content': content, 'request_id': str(uuid4())})
            assert response.status_code == 200, response.text
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            return events[-1]

        card = post(f'导入路径"{images}"下的数据，之后新建标签')['data_intake']
        assert card['stage'] == 'choose_mode'
        imported = post(f'选择导入方式 {card["id"]} 未标注')['data_intake']
        assert imported['imported_count'] == 11
        context = store.context(sid)
        assert len(context['dataset_catalog']) == 11
        assert not context.get('selected_cube_id')
        # A restored conversation may still have an earlier unanswered data
        # question. It must not block a project-level label operation either.
        context['pending_clarify'] = {'kind': 'dataset', 'reason': 'not_found', 'asked': False}
        store.save_context(sid, context)
        result = post('创建标签：PE、PET、PP')
        assert result['reply_status'] == 'replied', result
        assert result['data_intake']['id'] == card['id']
        assert [label['name'] for label in result['data_intake']['labels']] == ['PE', 'PET', 'PP']
        assert [row[2] for row in rows(application)] == ['PE', 'PET', 'PP']
        assert not store.context(sid).get('selected_cube_id')
        assert not model.requests
        assert len(application.state.dataset_registry.catalog()['datasets']) == 11
        assert result['data_intake']['ready_count'] == 0
        assert '11 个样品未保存区域标注' in result['content']
        assert '下一步：超像素人工标注' in result['content']
        # The next step offers generation modes for this intake's actual scope,
        # without opening an unprepared canvas or silently starting a task.
        selected = post(f'进入人工标注 {card["id"]}')
        targets = selected['annotation_target_cube_ids']
        assert targets == context['last_imported_cube_ids']
        assert '逐张生成' in selected['content'] and '提前生成全部' in selected['content']
        assert not selected.get('annotation_task_id')
        assert not application.state.agent_sessions.annotation_tasks.receipts
        assert not store.context(sid).get('pending_clarify')
        # Choosing a mode uses the existing task endpoint, retaining all eleven
        # targets for on-demand navigation while preparing only the first image.
        response = client.post(f'/api/v1/agent/sessions/{sid}/annotation-flow', json={
            'cube_ids': targets, 'mode': 'per_image', 'request_id': str(uuid4())})
        assert response.status_code == 200, response.text
        accepted = response.json()
        assert accepted['member_count'] == 11
        import time
        tasks = application.state.agent_sessions.annotation_tasks
        deadline = time.monotonic() + 15
        task = tasks.view(sid, accepted['task_id'])
        while task['task_status'] not in {'completed', 'failed', 'canceled'} and time.monotonic() < deadline:
            time.sleep(.02)
            task = tasks.view(sid, accepted['task_id'])
        assert task['counts']['ready'] == 1, task
        with connect_database(database) as db:
            assert db.execute('SELECT count(*) FROM annotation_version').fetchone()[0] == 0
        assert not model.requests


def test_manual_saved_annotations_refresh_intake_count_and_path_detour_can_return(application, tmp_path):
    import numpy as np
    from spectrumagent.annotation.engines.superpixels import Parameters

    images, _ = source(tmp_path, 2)
    sid, send = session(application)
    imported, _ = send(f'导入未标注的数据 "{images}"')
    intake_id = imported['data_intake']['id']
    created, _ = send('创建标签：PE、PET、PP')
    label = created['data_intake']['labels'][0]['id']
    with connect_database(application.state.experiments.paths.database) as db:
        cube = db.execute('SELECT id FROM dataset_registry ORDER BY rowid LIMIT 1').fetchone()[0]
    application.state.segmentation_resources.prepare(cube, Parameters(n_segments=4, pca_components=3))
    sessions = application.state.annotation_sessions
    sessions.edit(cube, np.ones((8, 8), bool), action='confirm', label_id=label)
    sessions.save(cube)
    # The original intake persisted zero external annotations. A later manual
    # save must count, and reopening the label form must not erase the result.
    refreshed, _ = send('创建标签')
    assert refreshed['data_intake']['ready_count'] == 1
    detour, _ = send(f'调整标注路径 {intake_id}')
    assert detour['data_intake']['stage'] == 'need_annotations'
    returned, events = send(f'进入人工标注 {intake_id}')
    assert returned['data_intake']['stage'] == 'imported'
    assert len(returned['annotation_target_cube_ids']) == 2
    assert not any(kind == 'workspace' for kind, _ in events)
    # A new draft edit invalidates the saved input until it is saved again.
    sessions.edit(cube, np.ones((8, 8), bool), action='erase')
    refreshed, _ = send('创建标签')
    assert refreshed['data_intake']['ready_count'] == 0


def test_duplicate_live_names_abort_and_deleted_name_gets_new_identity(application):
    database = application.state.experiments.paths.database
    store = LabelStore(database)
    project = store.projects()[0]['id']
    old = store.add(SimpleLabelRequest(project_id=project, name='PE', color_hex='#123456'))
    store.add(SimpleLabelRequest(project_id=project, name='PE', color_hex='#abcdef'))
    with pytest.raises(DataError):
        store.ensure_names(project, ['PP', 'PE'])
    assert len(rows(application)) == 2
    for row in rows(application):
        store.delete(row[0], confirm=True)
    replacement = store.ensure_names(project, ['PE'])[0]
    assert replacement['id'] != old['id'] and replacement['code'] != old['code']
