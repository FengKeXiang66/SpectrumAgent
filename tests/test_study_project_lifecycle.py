"""Study ownership exists before review and survives non-default project execution."""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from test_experiment_conversation import application, workspace, wait_task
from test_experiment_study import chat, until
from test_study_sample_scoring import image_draft
from backend.database import connect_database
from spectrumagent import projects
from spectrumagent.data import DataError
from spectrumagent.app import create_app
from spectrumagent.experiments.study import StudyService
from backend.identity import EngineIdentity


def proposal(app, tmp_path):
    database = app.state.experiments.paths.database
    project = projects.Projects(database).create('Study 生命周期')['id']
    with projects.bind(project):
        dialogue, owner, record = image_draft(app, tmp_path)
        events = chat(app, owner, f'基于此数据寻优 {record["experiment_id"]}，折数 3，潜变量 1-2；预处理候选：原谱；归一化候选：无')
        assert events[-1][0] == 'clarify', events
    with connect_database(database) as db:
        row = db.execute('SELECT document FROM study_draft WHERE session_id=?', (owner,)).fetchone()
        assert row is not None, events
        draft = json.loads(row[0])
    return project, owner, dialogue, draft


def test_draft_ownership_is_committed_before_confirmation(application, tmp_path):
    project, owner, dialogue, draft = proposal(application, tmp_path)
    database = dialogue.database
    with projects.bind(project), connect_database(database) as db:
        projects.check_document(db, {'study_id': draft['id']})
        assert db.execute("SELECT project_id FROM project_resource WHERE kind='study' AND resource_id=?",
                          (draft['id'],)).fetchone()[0] == project
    assert dialogue.study.latest(owner) is None  # Review does not run a numerical job.
    default = projects.Projects(database).list()['current_project_id']
    with connect_database(database) as db, projects.bind(default):
        with pytest.raises(DataError):
            projects.require(db, 'study', draft['id'])


def test_non_default_project_confirmation_runs_with_desktop_on_default(application, tmp_path):
    project, owner, dialogue, draft = proposal(application, tmp_path)
    # chat binds the immutable session project, not the selected desktop project.
    events = chat(application, owner, '确认探索性寻优')
    with projects.bind(project):
        state = dialogue.study.latest(owner)
        assert state is not None, events
        assert state['study_id'] == draft['id']
        completed = until(dialogue.study, owner, draft['id'])
        assert completed['status'] == 'succeeded', completed
        result = dialogue.study.result(owner, draft['id'])
        assert result['folds'] == 3 and len(result['candidates']) == 2
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer '+application.state.testing_identity.token
        assert client.get(f'/api/v1/agent/sessions/{owner}/studies/{draft["id"]}/result').status_code == 200
    again = chat(application, owner, '确认探索性寻优')
    assert again[-1][0] == 'clarify', again
    with projects.bind(project):
        assert dialogue.study.latest(owner)['study_id'] == draft['id']
    adopted = chat(application, owner, '采用推荐方案新建正式训练')
    assert adopted[-1][0] == 'clarify', adopted
    submitted = chat(application, owner, '确认执行')
    with projects.bind(project):
        task_id = dialogue.tasks.latest(owner)
        assert task_id, submitted
        trained = wait_task(dialogue.tasks, owner, task_id)
        assert trained['status'] == 'succeeded', trained


def test_ambiguous_or_invalid_legacy_drafts_are_not_claimed(application):
    database = application.state.experiments.paths.database
    management = projects.Projects(database)
    a = management.list()['current_project_id']
    b = management.create('冲突草稿')['id']
    shared = str(uuid4())
    for project, raw in ((a, json.dumps({'id': shared})), (b, json.dumps({'id': shared})),
                         (b, 'not json'), (b, json.dumps({'id': '../invalid'}))):
        owner = application.state.agent_sessions.create(project_id=project)['id']
        with connect_database(database) as db:
            db.execute('INSERT INTO study_draft VALUES(?,?)', (owner, raw))
    StudyService(application.state.agent_tools.experiment_dialogue)
    with connect_database(database) as db:
        assert db.execute("SELECT count(*) FROM project_resource WHERE kind='study'").fetchone()[0] == 0
        for project in (a, b):
            with projects.bind(project):
                assert not projects.owned(db, 'study', shared)


def test_existing_pending_draft_recovers_from_session_on_restart(application, tmp_path):
    project, owner, dialogue, draft = proposal(application, tmp_path)
    expected_confirmation = dialogue.confirmation(owner)
    with connect_database(dialogue.database) as db:
        # Simulate an actual pre-fix pending card, without touching real user data.
        db.execute("DELETE FROM project_resource WHERE kind='study' AND resource_id=?", (draft['id'],))
    fresh = create_app(dialogue.service.paths, EngineIdentity())
    restored = fresh.state.agent_tools.experiment_dialogue
    with projects.bind(project), connect_database(dialogue.database) as db:
        projects.require(db, 'study', draft['id'])
        assert json.loads(db.execute('SELECT document FROM study_draft WHERE session_id=?', (owner,)).fetchone()[0]) == draft
    assert restored.confirmation(owner) == expected_confirmation
    events = chat(fresh, owner, '确认探索性寻优')
    with projects.bind(project):
        completed = until(restored.study, owner, draft['id'])
        assert completed['status'] == 'succeeded', (events, completed)


def test_registration_is_idempotent_and_never_transfers_to_another_project(application):
    database = application.state.experiments.paths.database
    management = projects.Projects(database)
    a = management.list()['current_project_id']
    b = management.create('不能接管资源')['id']
    identifier = str(uuid4())
    for project in (a, b):
        with projects.bind(project), connect_database(database) as db:
            assert not projects.owned(db, 'study', identifier)
    with projects.bind(b), connect_database(database) as db:
        projects.register(db, 'study', identifier)
        projects.register(db, 'study', identifier)
    with projects.bind(a), connect_database(database) as db:
        with pytest.raises(DataError) as failure:
            projects.register(db, 'study', identifier)
        assert failure.value.code == 'RESOURCE_NOT_FOUND'
        assert db.execute("SELECT project_id FROM project_resource WHERE resource_id=?", (identifier,)).fetchall() == [(b,)]


def test_conflicting_legacy_index_is_not_overwritten_or_executed(application, tmp_path):
    project, owner, dialogue, draft = proposal(application, tmp_path)
    default = projects.Projects(dialogue.database).list()['current_project_id']
    with connect_database(dialogue.database) as db:
        db.execute("UPDATE project_resource SET project_id=? WHERE kind='study' AND resource_id=?", (default, draft['id']))
    manager = StudyService(dialogue)
    with projects.bind(project), pytest.raises(DataError) as failure:
        manager.submit(owner, str(uuid4()), '确认探索性寻优')
    assert failure.value.code == 'RESOURCE_NOT_FOUND'
    assert not (manager.root / draft['id']).exists()
    assert not dialogue.service.lock.locked()
    assert dialogue.confirmation(owner)[2] == draft['id']
    with connect_database(dialogue.database) as db:
        assert db.execute("SELECT project_id FROM project_resource WHERE resource_id=?", (draft['id'],)).fetchone()[0] == default


def test_failed_draft_save_rolls_back_ownership_and_keeps_review(application, tmp_path, monkeypatch):
    project, owner, dialogue, draft = proposal(application, tmp_path)
    confirmation = dialogue.confirmation(owner)
    def index():
        with connect_database(dialogue.database) as db:
            return db.execute('SELECT * FROM project_resource ORDER BY kind,resource_id').fetchall()
    before = index()
    def fail(*args):
        raise RuntimeError('injected confirmation failure')
    monkeypatch.setattr(dialogue, 'set_confirmation', fail)
    with projects.bind(project), pytest.raises(RuntimeError, match='injected'):
        dialogue.study.prepare(owner, str(uuid4()), '调整寻优，折数 2')
    assert index() == before
    assert dialogue.confirmation(owner) == confirmation
    with connect_database(dialogue.database) as db:
        assert json.loads(db.execute('SELECT document FROM study_draft WHERE session_id=?', (owner,)).fetchone()[0]) == draft


def test_failed_experiment_registration_releases_numerical_lock(application, tmp_path, monkeypatch):
    project, owner, dialogue, _ = proposal(application, tmp_path)
    with projects.bind(project):
        config = dialogue._config(dialogue._read(owner))
        def fail(*args):
            raise projects.denied()
        monkeypatch.setattr(projects, 'register', fail)
        with pytest.raises(DataError) as failure:
            dialogue.service.run(config)
    assert failure.value.code == 'RESOURCE_NOT_FOUND'
    assert not dialogue.service.lock.locked()
