"""Dataset intake runs without model guesses or mandatory train/test paths."""
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from spectral.io import envi

from test_experiment_conversation import application, machine_for, ScriptedModel, workspace
from backend.database import connect_database
from spectrumagent.agent.state import AgentStore
from spectrumagent.experiments.inputs import roi_maps, sha256
from spectrumagent.preprocess.current import CurrentWorkspace


def source(tmp_path, count=2):
    images = tmp_path / '原始 ENVI'
    annotations = tmp_path / '已有 ROI'
    images.mkdir(); annotations.mkdir()
    for i in range(count):
        header = images / f'plastic{i}.hdr'
        envi.save_image(str(header), np.random.default_rng(i).uniform(.1, .8, (8, 8, 6)).astype(np.float32),
                        ext='.dat', metadata={'wavelength': [1000, 1010, 1020, 1030, 1040, 1050], 'wavelength units': 'nm'})
        doc = dict(source_hdr=str(header), imagePath=header.with_suffix('.png').name,
                   imageHeight=8, imageWidth=8, shapes=[
                       dict(label='pe', shape_type='rectangle', points=[[0, 0], [2, 7]]),
                       dict(label='pet', shape_type='polygon', points=[[4, 0], [7, 0], [7, 7], [4, 7]]),
                   ])
        (annotations / f'plastic{i}.json').write_text(json.dumps(doc), 'utf-8')
    return images, annotations


def session(app):
    sid = AgentStore(app.state.experiments.paths.database).create_session()['id']
    model = ScriptedModel()
    def send(text):
        events = list(machine_for(app, sid, model).message(content=text))
        assert events[-1][0] == 'done', events
        assert not model.requests
        return events[-1][1], events
    return sid, send


def test_unlabeled_import_choice_and_resume_do_not_infer_labels(application, tmp_path):
    images, _ = source(tmp_path)
    sid, send = session(application)
    reply, _ = send(f'导入 "{images}"')
    card = reply['data_intake']
    assert card['stage'] == 'choose_mode'
    assert application.state.dataset_registry.catalog()['total'] == 0
    assert str(images) not in json.dumps(card)
    # Every send constructs a fresh state machine: selection is durable.
    reply, _ = send(f'选择导入方式 {card["id"]} 未标注')
    assert reply['data_intake']['imported_count'] == 2
    with connect_database(application.state.experiments.paths.database) as db:
        assert db.execute('SELECT count(*) FROM label').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM annotation_version').fetchone()[0] == 0
    assert {row['workflow_status'] for row in application.state.dataset_registry.catalog()['datasets']} == {'need_annotation'}
    reply, _ = send('查看已导入的数据')
    assert '2 个数据集' in reply['content'] and '训练原图' not in reply['content']
    context = json.loads(AgentStore(application.state.experiments.paths.database).session(sid)['context_json'])
    assert len(context['dataset_catalog']) == 2
    assert all(row['name'].startswith('plastic') for row in context['dataset_catalog'])
    # Old choices cannot change the mode or accidentally start a second import.
    reply, _ = send(f'选择导入方式 {card["id"]} 已有标注')
    assert reply['data_intake']['mode'] == 'unlabeled'
    assert application.state.dataset_registry.catalog()['total'] == 2
    history = machine_for(application, sid, ScriptedModel())._history_messages(
        AgentStore(application.state.experiments.paths.database).skill(sid))
    assert str(images) not in json.dumps(history, ensure_ascii=False)


def test_external_annotations_reach_preprocessing_without_superpixels(application, tmp_path, monkeypatch):
    images, annotations = source(tmp_path)
    sid, send = session(application)
    send('创建标签：pe、pet')
    reply, _ = send(f'导入带标注的数据，原图 "{images}"')
    assert reply['data_intake']['stage'] == 'need_annotations'
    assert '训练原图' not in reply['content']
    reply, _ = send(f'标注位置为 "{annotations}"')
    card = reply['data_intake']
    assert card['stage'] == 'review' and card['paired_count'] == 2
    assert card['classes'] == ['pe', 'pet']
    assert application.state.dataset_registry.catalog()['total'] == 0  # read-only preview
    def forbidden(*args, **kwargs):
        raise AssertionError('external annotations must not prepare superpixels')
    monkeypatch.setattr(application.state.superpixel_engine, 'prepare', forbidden)
    reply, _ = send(f'使用已配对标注 {card["id"]}')
    assert reply['data_intake']['ready_count'] == 2, application.state.agent_tools.data_intake.read(sid)['issues']
    current = CurrentWorkspace(application.state.annotation_sessions, application.state.preprocess_runner)
    assert {row['status'] for row in current.state()['members']} == {'need_preprocess'}
    for row in application.state.dataset_registry.catalog()['datasets']:
        cube = row['id']
        assert row['workflow_status'] == 'need_preprocess'
        application.state.annotation_sessions.working(cube)
        assert application.state.annotation_sessions._states[cube].segments is None
        header = Path(row['source_path'])
        _, expected = roi_maps(annotations / (header.stem + '.json'), (8, 8), {1:'pe', 2:'pet'}, sha256(header))
        saved = application.state.annotation_sessions.working(cube)
        actual = saved['label_map']
        assert np.array_equal(actual == -1, expected == 0)
        for index, label_id in saved['label_index'].items():
            with connect_database(current.database) as db:
                name = db.execute('SELECT name FROM label WHERE id=?', (label_id,)).fetchone()[0]
            assert np.array_equal(actual == int(index), expected == {'pe':1, 'pet':2}[name])
        recipe = application.state.preprocess_runner.recipes.create(code='EXT'+header.stem.upper(), name='外部标注基线', description='', pipeline={'steps': []})
        result = current.process(cube, recipe['id'])
        assert result['status'] == 'succeeded', result
    assert {row['workflow_status'] for row in application.state.dataset_registry.catalog()['datasets']} == {'ready'}
    # Restart reconstructs the saved annotation without an in-memory segmentation.
    from spectrumagent.annotation.session import SessionStore
    restored = SessionStore(application.state.dataset_registry, application.state.experiments.paths)
    assert np.any(restored.working(cube)['label_map'] >= 0)
    assert CurrentWorkspace(restored, application.state.preprocess_runner).state()['members'][0]['annotation_id']
    reply, events = send(f'进入预处理 {card["id"]}')
    assert not any(kind == 'workspace' for kind, data in events)
    assert any(kind == 'step' and data.get('tool') == 'experiments.draft_presentation' for kind, data in events)
    dialogue = application.state.agent_tools.experiment_dialogue
    assert dialogue.view(sid)['can_study']
    assert not dialogue.view(sid)['can_run']
    # A completed card is idempotent.
    send(f'使用已配对标注 {card["id"]}')
    with connect_database(current.database) as db:
        assert db.execute('SELECT count(*) FROM annotation_version').fetchone()[0] == 2


def test_partial_batch_ambiguity_and_single_annotation_path(application, tmp_path):
    images, annotations = source(tmp_path, 3)
    (annotations / 'plastic2.json').unlink()
    duplicate = json.loads((annotations / 'plastic1.json').read_text())
    (annotations / 'duplicate.json').write_text(json.dumps(duplicate))
    _, send = session(application)
    send('创建标签：pe、pet')
    reply, _ = send(f'导入 "{images}"')
    intake = reply['data_intake']['id']
    send(f'选择导入方式 {intake} 已有标注')
    reply, _ = send(f'标注 "{annotations}"')
    card = reply['data_intake']
    assert (card['image_count'], card['paired_count'], card['missing_count'], card['issue_count']) == (3, 1, 2, 1)
    reply, _ = send(f'使用已配对标注 {intake}')
    assert reply['data_intake']['ready_count'] == 1
    reply, _ = send(f'配置预处理与训练 {intake}')
    assert '2 张' in reply['content'] and '未纳入' in reply['content']
    assert sorted(r['workflow_status'] for r in application.state.dataset_registry.catalog()['datasets']) == ['need_annotation', 'need_annotation', 'need_preprocess']
    # A single JSON can be attached to one explicitly selected image.
    _, other = session(application)
    reply, _ = other(f'导入已有标注的原图 "{images / "plastic2.hdr"}"')
    single = dict(duplicate, source_hdr=str(images / 'plastic2.hdr'), imagePath='plastic2.png')
    single_path = annotations / 'single.json'
    single_path.write_text(json.dumps(single))
    reply, _ = other(f'标注文件 "{single_path}"')
    assert reply['data_intake']['paired_count'] == 1


def test_source_changes_and_existing_manual_edits_are_not_overwritten(application, tmp_path):
    images, annotations = source(tmp_path, 1)
    _, send = session(application)
    send('创建标签：pe、pet')
    reply, _ = send(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    intake = reply['data_intake']['id']
    annotation = annotations / 'plastic0.json'
    annotation.write_text(annotation.read_text() + '\n')
    reply, _ = send(f'使用已配对标注 {intake}')
    assert '来源发生变化' in reply['content']
    assert application.state.dataset_registry.catalog()['total'] == 0
    send(f'调整标注路径 {intake}')
    send(f'标注 "{annotation}"')
    reply, _ = send(f'使用已配对标注 {intake}')
    assert reply['data_intake']['ready_count'] == 1, reply
    cube = application.state.dataset_registry.catalog()['datasets'][0]['id']
    sessions = application.state.annotation_sessions
    old = sessions.drafts.get(cube)
    edited = json.loads(json.dumps(old['document']))
    edited['regions'].pop()
    sessions.drafts.replace(cube, edited, old['revision'])
    original = sessions.drafts.get(cube)
    _, again = session(application)
    reply, _ = again(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    reply, _ = again(f'使用已配对标注 {reply["data_intake"]["id"]}')
    assert reply['data_intake']['ready_count'] == 0
    assert sessions.drafts.get(cube) == original


def test_http_cards_survive_history_and_stale_actions_are_rejected(application, tmp_path):
    images, annotations = source(tmp_path, 1)
    identity = application.state.testing_identity
    with TestClient(application, headers={'Authorization':'Bearer '+identity.token}) as client:
        sid = client.post('/api/v1/agent/sessions', json={'scope':{'kind':'global'}}).json()['id']
        def send(text):
            response = client.post(f'/api/v1/agent/sessions/{sid}/messages', json={'content':text, 'request_id':str(uuid4())})
            assert response.status_code == 200, response.text
            return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')][-1]
        first = send(f'导入 "{images}"')['data_intake']
        second = send(f'导入 "{images}"')['data_intake']
        assert first['id'] != second['id']
        reply = send(f'选择导入方式 {first["id"]} 未标注')
        assert '失效' in reply['content']
        assert application.state.dataset_registry.catalog()['total'] == 0
        send(f'选择导入方式 {second["id"]} 已有标注')
        # Same-directory scanning is an explicit action, with no assumed labels.
        (images / 'plastic0.json').write_text((annotations / 'plastic0.json').read_text())
        card = send(f'检查同目录标注 {second["id"]}')['data_intake']
        assert card['paired_count'] == 1
        history = client.get(f'/api/v1/agent/sessions/{sid}/history').json()['events']
        assert any(item['kind'] == 'done' and item['payload'].get('data_intake', {}).get('paired_count') == 1 for item in history)


def test_intake_does_not_capture_questions_npz_or_explicit_training_roles(application, tmp_path):
    images, _ = source(tmp_path, 1)
    sid, _ = session(application)
    intake = application.state.agent_tools.data_intake
    machine = machine_for(application, sid, ScriptedModel())
    for content in ('为什么导入数据后只有一个？', '不要导入数据', '如何导入带标注的数据？',
                    f'导入 NPZ 数据 "{images}"', f'训练原图 "{images}"，测试原图 "{images}"'):
        assert intake.route(machine, content) is None
    # Directory names are local paths, not instructions assigning train/test roles.
    folder = tmp_path / '训练数据'
    folder.mkdir()
    events = list(intake.route(machine, f'导入 "{folder}"'))
    assert events[-1][1]['data_intake']['stage'] == 'choose_mode'


@pytest.mark.parametrize('signature', [None, {'hdr_sha256': 'bad-signature'}, {'img_bytes': True}])
def test_invalid_annotation_signatures_are_reported_without_writing(application, tmp_path, signature):
    images, annotations = source(tmp_path, 1)
    path = annotations / 'plastic0.json'
    doc = json.loads(path.read_text())
    doc['source_signature'] = signature
    path.write_text(json.dumps(doc))
    _, send = session(application)
    reply, _ = send(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    card = reply['data_intake']
    assert card['paired_count'] == 0 and card['issue_count'] == 1
    assert application.state.dataset_registry.catalog()['total'] == 0


def test_labelme_relocation_and_annotation_dimension_errors(application, tmp_path):
    images, annotations = source(tmp_path, 2)
    good = annotations / 'plastic0.json'
    doc = json.loads(good.read_text())
    doc['source_hdr'] = r'Z:\old-workstation\plastic0.hdr'
    good.write_text(json.dumps(doc))
    bad = annotations / 'plastic1.json'
    doc = json.loads(bad.read_text()); doc['imageWidth'] = 123
    bad.write_text(json.dumps(doc))
    _, send = session(application)
    send('创建标签：pe、pet')
    reply, _ = send(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    card = reply['data_intake']
    assert card['paired_count'] == 1 and card['issue_count'] == 1
    reply, _ = send(f'使用已配对标注 {card["id"]}')
    assert reply['data_intake']['ready_count'] == 1


def test_bad_unmatched_header_does_not_block_valid_pairs_or_widen_preview(application, tmp_path):
    images, annotations = source(tmp_path, 2)
    (images / 'plastic1.hdr').write_text('not an ENVI header')
    _, send = session(application)
    send('创建标签：pe、pet')
    reply, _ = send(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    card = reply['data_intake']
    assert card['paired_count'] == 1 and card['issue_count'] == 1
    # New directory members are not part of the reviewed batch.
    envi.save_image(str(images / 'new.hdr'), np.ones((8, 8, 6), np.float32), ext='.dat')
    reply, _ = send(f'使用已配对标注 {card["id"]}')
    assert reply['data_intake']['imported_count'] == reply['data_intake']['ready_count'] == 1
    assert application.state.dataset_registry.catalog()['total'] == 1


def test_roi_requires_chat_labels_and_retry_matches_case(application, tmp_path):
    images, annotations = source(tmp_path, 2)
    owner, send = session(application)
    reply, _ = send(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    intake = reply['data_intake']['id']
    reply, _ = send(f'使用已配对标注 {intake}')
    assert reply['data_intake']['ready_count'] == 0
    assert reply['data_intake']['annotation_retry']
    with connect_database(application.state.experiments.paths.database) as db:
        assert db.execute('SELECT count(*) FROM label').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM annotation_version').fetchone()[0] == 0
    reply, _ = send('创建标签：PE、PET')
    assert len(reply['data_intake']['labels']) == 2
    reply, _ = send(f'使用已配对标注 {intake}')
    assert reply['data_intake']['ready_count'] == 2, application.state.agent_tools.data_intake.read(owner)['issues']
    assert not reply['data_intake']['annotation_retry']
    assert reply['data_intake']['issue_count'] == 0
    with connect_database(application.state.experiments.paths.database) as db:
        assert {row[0] for row in db.execute('SELECT name FROM label')} == {'PE', 'PET'}


def test_create_labels_preserves_roi_preview(application, tmp_path):
    images, annotations = source(tmp_path, 2)
    _, send = session(application)
    reply, _ = send(f'导入已有标注的数据，原图 "{images}"，标注 "{annotations}"')
    intake = reply['data_intake']['id']
    reply, _ = send('创建标签：PE、PET')
    assert reply['data_intake']['id'] == intake
    assert reply['data_intake']['stage'] == 'review'
    assert reply['data_intake']['paired_count'] == 2
    assert application.state.dataset_registry.catalog()['total'] == 0
    reply, _ = send(f'使用已配对标注 {intake}')
    assert reply['data_intake']['ready_count'] == 2
