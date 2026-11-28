"""Submitted inference plans are read-only; explicit new plans keep archived runs."""
import json

import numpy as np
import pytest

from test_experiment_conversation import application, workspace, ScriptedModel, machine_for, tool
from test_experiment_inference import train, wait
from test_experiment_study import envi_scene, chat
from backend.database import connect_database
from spectrumagent.agent.state import AgentStore
from spectrumagent.agent.tools.inference import InferenceUpdate
from spectrumagent.data import DataError
from spectrumagent import projects
from spectrumagent.app import create_app
from backend.identity import EngineIdentity


def completed(app, tmp_path):
    model, dialogue = train(app, tmp_path, image=True)
    header = tmp_path/'first.hdr'
    envi_scene(header, np.arange(1100, 1145, 5))
    owner = AgentStore(dialogue.database).create_session()['id']
    dialogue.capture(owner, f'使用模型 {model} 推理 "{header}"')
    settings = dict(kind='envi', source_refs=['I1'], wavelength_unit='nm', mapping_window_nm=5.,
                    nearest_tolerance_nm=2., quality=dict(min_mean=0., min_std=0., max_zero_fraction=1., saturation=None),
                    foreground=dict(mode='none'))
    dialogue.update(owner, InferenceUpdate(expected_revision=1, input=settings))
    assert dialogue.presented(owner, 'review')['can_run']
    run = dialogue.confirm(owner, '确认推理', 'execute')['inference_run_id']
    assert wait(dialogue.service, model, run)['status'] == 'succeeded'
    return model, dialogue, owner, header, run, settings


def files(dialogue, model, run):
    folder = dialogue.service.folder(model, run)
    return {str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()}


def card(events):
    return next(json.loads(data['result_summary']['inference_card_json']) for kind, data in events
                if kind == 'step' and data['tool'] == 'experiments.inference_presentation')


def test_submitted_plan_is_readonly_and_not_inspected_again(application, tmp_path, monkeypatch):
    model, dialogue, owner, header, run, _ = completed(application, tmp_path)
    before, artifacts = dialogue.read(owner), files(dialogue, model, run)
    def forbidden(*args, **kwargs):
        raise AssertionError('A submitted record must not be inspected or probed')
    monkeypatch.setattr(dialogue.service, 'inspect', forbidden)
    monkeypatch.setattr(dialogue, 'probe', forbidden)
    shown = dialogue.presented(owner, 'show-again')
    assert shown['presentation']['editable'] is False and not shown['can_run']
    assert shown['presentation']['state'] == 'submitted' and shown['presentation']['run_id'] == run
    assert '已执行' in shown['presentation']['todo']
    for change in (
        lambda: dialogue.capture(owner, f'使用模型 {model} 推理 "{header}"'),
        lambda: dialogue.apply_inline(owner, json.dumps(dict(expected_revision=before['revision'], quality=dict(min_mean=.01)))),
        lambda: dialogue.update(owner, InferenceUpdate(expected_revision=before['revision'], input={'kind':'envi','quality':{'min_mean':.01}})),
    ):
        with pytest.raises(DataError) as failure:
            change()
        assert failure.value.code == 'INFERENCE_DRAFT_READ_ONLY'
    assert dialogue.read(owner) == before
    assert files(dialogue, model, run) == artifacts


@pytest.mark.parametrize('change_model', [False, True])
def test_repeated_request_offers_choice_then_uses_new_input(application, tmp_path, change_model):
    model, dialogue, owner, _, run, settings = completed(application, tmp_path)
    before, artifacts = dialogue.read(owner), files(dialogue, model, run)
    header = tmp_path/'second.hdr'
    envi_scene(header, np.arange(1100, 1145, 5))
    new_model = model
    if change_model:
        other = tmp_path/'other'
        other.mkdir()
        new_model, _ = train(application, other, image=True)
    events = chat(application, owner, f'使用模型 {new_model} 进行推理，数据目录 "{header}"')
    shown = card(events)
    assert not shown['editable'] and shown['run_id'] == run and '暂存本次请求' in shown['todo']
    assert dialogue.read(owner) == before
    # Pending choice and its token survive an engine/session restore.
    fresh = create_app(dialogue.service.experiments.paths, EngineIdentity())
    dialogue = fresh.state.agent_tools.experiment_dialogue.inference
    assert dialogue.view(owner, structured=True)['presentation']['restart_command'] == shown['restart_command']
    scripted = ScriptedModel(tool('experiments.inference_update', {
        'expected_revision':before['revision']+1+int(change_model), 'input':settings}))
    events = list(machine_for(fresh, owner, scripted).message(content=shown['restart_command']))
    assert card(events)['editable'] and card(events)['ready'], events
    draft = dialogue.read(owner)
    assert draft['active'] == 1 and draft['run_id'] is None
    assert dialogue.config(owner).input.paths == [str(header)]
    assert dialogue.config(owner).model_id == new_model
    changed = chat(fresh, owner, '应用推理参数 '+json.dumps(dict(expected_revision=draft['revision'], quality=dict(min_mean=.01))))
    assert card(changed)['revision'] == draft['revision']+1 and card(changed)['editable']
    assert files(dialogue, model, run) == artifacts


def test_restart_operations_reject_a_foreign_session(application):
    dialogue = application.state.agent_tools.experiment_dialogue.inference
    project = projects.Projects(dialogue.database).create('其他项目')['id']
    owner = application.state.agent_sessions.create(project_id=project)['id']
    for change in (lambda: dialogue.request_restart(owner, '再次推理'), lambda: dialogue.restart(owner)):
        with pytest.raises(DataError) as failure:
            change()
        assert failure.value.code == 'RESOURCE_NOT_FOUND'
    assert dialogue.read(owner) is None


def test_explicit_new_from_record_clones_plan_and_rejects_stale_action(application, tmp_path):
    model, dialogue, owner, _, run, _ = completed(application, tmp_path)
    before, artifacts = dialogue.read(owner), files(dialogue, model, run)
    command = dialogue.view(owner, structured=True)['presentation']['restart_command']
    events = chat(application, owner, command)
    assert card(events)['editable'] and card(events)['ready']
    draft = dialogue.read(owner)
    assert draft['revision'] == before['revision']+1 and draft['run_id'] is None and draft['active'] == 1
    assert draft['document'] == before['document'] and draft['sources'] == before['sources']
    result = chat(application, owner, '查看上次推理结果')
    archived = next(data['result_summary'] for kind, data in result if kind=='step' and data['tool']=='experiments.inference_status')
    assert archived['inference_run_id'] == run
    chat(application, owner, command)
    assert dialogue.read(owner) == draft
    changed = chat(application, owner, '应用推理参数 '+json.dumps(dict(expected_revision=draft['revision'], quality=dict(min_mean=.01))))
    assert card(changed)['revision'] == draft['revision']+1
    assert files(dialogue, model, run) == artifacts


def test_latest_restart_choice_and_viewing_results_preserve_old_run(application, tmp_path):
    model, dialogue, owner, header, run, _ = completed(application, tmp_path)
    before, artifacts = dialogue.read(owner), files(dialogue, model, run)
    first = card(chat(application, owner, f'使用模型 {model} 推理 "{header}"'))
    second = card(chat(application, owner, f'使用模型 {model} 再次推理 "{header}"'))
    assert first['restart_command'] != second['restart_command']
    events = chat(application, owner, first['restart_command'])
    assert events[-1][0] == 'clarify' and '新建请求已更新' in events[-1][1]['question']
    assert dialogue.read(owner) == before
    events = chat(application, owner, '查看上次推理结果')
    assert any(kind == 'step' and data['tool'] == 'experiments.inference_status' for kind, data in events)
    with connect_database(dialogue.database) as db:
        assert db.execute('SELECT count(*) FROM inference_restart_request WHERE session_id=?', (owner,)).fetchone()[0] == 0
    assert dialogue.read(owner) == before
    assert files(dialogue, model, run) == artifacts
