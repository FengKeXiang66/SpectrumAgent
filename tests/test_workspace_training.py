"""Saved manual and imported truth share the train-only Study/experiment path."""
import json
from pathlib import Path

import numpy as np
import pytest

from test_experiment_conversation import application, wait_task, workspace
from backend.database import connect_database
from spectrumagent.agent.tools.experiments import DraftUpdate
from spectrumagent.data import DataError
from spectrumagent.experiments.inputs import image_samples
from spectrumagent.experiments.study import group_kind
from spectrumagent.experiments.workspace_training import prepare
from test_data_intake import source, session
from test_experiment_study import chat, until


def imported(app, tmp_path, count=6):
    images, annotations = source(tmp_path, count)
    owner, send = session(app)
    send('创建标签：pe、pet')
    reply, _ = send(f'导入 "{images}"')
    intake = reply['data_intake']['id']
    send(f'选择导入方式 {intake} 已有标注')
    send(f'标注 "{annotations}"')
    reply, _ = send(f'使用已配对标注 {intake}')
    send('接下来对数据进行预处理')
    return owner, app.state.agent_tools.experiment_dialogue, send


def test_saved_masks_study_split_adopt_and_train(application, tmp_path, monkeypatch):
    owner, dialogue, send = imported(application, tmp_path)
    record = dialogue._read(owner)
    assert not record['document'].get('test')
    assert dialogue.view(owner)['can_study'] and not dialogue.view(owner)['can_run']
    config = dialogue._config(record, training_only=True)
    assert group_kind(config, {'grouping': 'auto'}) == 'image'
    data = image_samples(config.train, np.array(config.wavelengths_nm), config.classes)
    assert len(data.y) == sum(sum(row['counts'].values()) for row in record['document']['workspace_selection'])
    for member, row in zip(config.train.members, record['document']['workspace_selection']):
        saved = application.state.annotation_sessions.working(row['cube_id'])
        with np.load(member.roi_path) as archive:
            assert np.array_equal(archive['region_map'] > 0, saved['label_map'] >= 0)
            assert np.all(archive['label_map'][saved['label_map'] < 0] == 0)
        assert member.sample_id == member.header_path
    # Shared extraction settings do not invent a held-out test set.
    dialogue.update(owner, DraftUpdate(expected_revision=record['revision'],
                    train={'kind': 'roi_images', 'sampling_stride': 2}))
    assert 'test' not in dialogue._read(owner)['document']
    # Explicit numbered split persists and keeps all training classes.
    events = chat(application, owner, '将第2、4张设为测试，其余用于训练')
    assert events[-1][0] == 'clarify', events
    record = dialogue._read(owner)
    assert len(record['document']['train']['members']) == 4
    assert len(record['document']['test']['members']) == 2
    assert dialogue.view(owner)['can_run']
    members = {role: record['document'][role]['members'] for role in ('train', 'test')}
    dialogue.update(owner, DraftUpdate(expected_revision=record['revision'],
                    train={'kind': 'roi_images', 'neighborhood': 3, 'sampling_stride': 1}))
    record = dialogue._read(owner)
    assert all(record['document'][role]['members'] == members[role] and record['document'][role]['neighborhood'] == 3
               for role in ('train', 'test'))
    test_paths = {str(dialogue._source(record, m['roi_ref'])) for m in record['document']['test']['members']}
    real_load = np.load
    def no_test(file, *args, **kwargs):
        assert str(file) not in test_paths, 'Study read held-out labels'
        return real_load(file, *args, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(np, 'load', no_test)
        events = chat(application, owner, '发起寻优，折数 2，潜变量 1-2')
        assert '确认探索性寻优' in events[-1][1]['question'], events
        chat(application, owner, '确认探索性寻优')
        identifier = dialogue.study.latest(owner)['study_id']
        result = until(dialogue.study, owner, identifier)
        assert result['status'] == 'succeeded', result
    chat(application, owner, '采用推荐方案新建正式训练')
    assert dialogue.tasks.latest(owner) is None
    events = chat(application, owner, '确认执行')
    assert dialogue.tasks.latest(owner), events
    state = wait_task(dialogue.tasks, owner, dialogue.tasks.latest(owner))
    assert state['status'] == 'succeeded', json.dumps(state, ensure_ascii=False)


def test_manual(application, tmp_path):
    from spectrumagent.annotation.engines.superpixels import Parameters
    from spectrumagent.annotation.labels import LabelStore, SimpleLabelRequest
    images, _ = source(tmp_path, 2)
    owner, send = session(application)
    reply, _ = send(f'导入 "{images}"')
    send(f'选择导入方式 {reply["data_intake"]["id"]} 未标注')
    registry, sessions = application.state.dataset_registry, application.state.annotation_sessions
    cubes = [row['id'] for row in registry.catalog()['datasets']]
    with connect_database(registry.database) as db:
        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cubes[0],)).fetchone()[0]
    store = LabelStore(registry.database)
    labels = [store.add(SimpleLabelRequest(project_id=project, name=name, color_hex='#2288cc'))['id'] for name in ('PE', 'PET')]
    for cube in cubes:
        application.state.segmentation_resources.prepare(cube, Parameters(n_segments=4, pca_components=3))
        mask = np.zeros((8,8), bool); mask[1:3, 1:3] = True
        sessions.edit(cube, mask, action='confirm', label_id=labels[0])
        other = np.zeros((8,8), bool); other[5:7, 5:7] = True
        sessions.edit(cube, other, action='confirm', label_id=labels[1])
        sessions.save(cube)
    reply, _ = send('我已经对数据标注完毕')
    assert reply['data_intake']['ready_count'] == 2
    send('接下来对数据进行预处理')
    dialogue = application.state.agent_tools.experiment_dialogue
    assert dialogue.view(owner)['can_study']
    record = dialogue._read(owner)
    assert all(sum(row['counts'].values()) == 8 for row in record['document']['workspace_selection'])
    # Editing the canvas cannot silently change an existing training snapshot.
    sessions.edit(cubes[0], other, action='confirm', label_id=labels[0])
    assert dialogue._config(record, training_only=True)
    with pytest.raises(DataError, match='保存'):
        prepare(dialogue, registry, sessions, owner, cubes)
