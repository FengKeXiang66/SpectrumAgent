"""Regression plan: no model dependency for forms, real foldwise engine on consent."""
import json
from uuid import uuid4

import numpy as np
import pytest

from test_experiment_conversation import application, workspace, machine_for, tool
from test_preprocessing_editor import client_session, offline
from test_data_intake import source
from backend.database import connect_database
from spectrumagent.agent.regression_plan import PREFIX, PlanPatch, PlanReview, PlanExecute, RegressionPlans
from spectrumagent.agent.llm import ChatResult
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.preprocess.current import CurrentWorkspace
from spectrumagent.modeling.dataset import SampleTargets
from spectrumagent.data import DataError


@pytest.fixture
def prepared(application, tmp_path):
    offline(application)
    client, sid = client_session(application)
    registry, sessions, runner = application.state.dataset_registry, application.state.annotation_sessions, application.state.preprocess_runner
    images, _ = source(tmp_path, 8)
    cubes = [str(registry.import_path(str(images/f'plastic{i}.hdr')).datasets[0].id) for i in range(8)]
    with connect_database(runner.database) as db:
        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cubes[0],)).fetchone()[0]
    label = LabelStore(runner.database).ensure_names(project, ['PE'])[0]['id']
    recipe = runner.recipes.create('plan-test', '方案测试', None, {'steps': [dict(op='standardize', version=1, params={'method': 'standard'})]})
    runs = []
    for cube in cubes:
        application.state.segmentation_resources.prepare(cube, Parameters(n_segments=4, pca_components=3))
        sessions.edit(cube, np.ones((8, 8), bool), action='confirm', label_id=label)
        runs.append(CurrentWorkspace(sessions, runner).process(cube, recipe['id'])['id'])
    response = client.post('/api/v1/labels', json={'project_id': project, 'schema': {
        'name': '含量', 'tree_path': '含量', 'field_type': 'continuous', 'unit': '%', 'config': {}}})
    assert response.status_code == 201, response.text
    schema = response.json()['id']
    for i, cube in enumerate(cubes):
        SampleTargets(runner.database).put(cube, schema, float(i+1))
    return dict(client=client, sid=sid, cubes=cubes, runs=runs, schema=schema, app=application,
                plans=application.state.agent_tools.regression_plans)


def read(p):
    response = p['client'].get(f"/api/v1/agent/sessions/{p['sid']}/regression-plan")
    assert response.status_code == 200, response.text
    return response.json()


def submit(p, action, *, revision=None, **fields):
    command = dict(action=action, expected_revision=read(p)['revision'] if revision is None else revision, form_id=str(uuid4()), **fields)
    response = p['client'].post(f"/api/v1/agent/sessions/{p['sid']}/messages", json={
        'content': PREFIX+json.dumps(command), 'request_id': str(uuid4())})
    assert response.status_code == 200, response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    return events[-1]


def save(p, **patch):
    revision = read(p)['revision']
    return submit(p, 'save', patch=dict(expected_revision=revision, preprocess_run_ids=p['runs'],
        target_schema_id=p['schema'], template='ks_5fold_v1', cv_folds=2, n_components=1, max_components=1, **patch))


def test_forms_review_execute_restore_and_duplicate_confirmation(prepared, monkeypatch, tmp_path):
    p = prepared
    assert read(p)['revision'] == 0
    assert read(p)['document'] == {}  # merely opening cannot silently choose parameters
    assert str(tmp_path) not in json.dumps(read(p))
    assert save(p)['reply_status'] == 'replied'
    assert read(p)['status'] == 'draft'
    with connect_database(p['plans'].database) as db:
        assert db.execute('SELECT COUNT(*) FROM training_run').fetchone()[0] == 0
    def forbidden(*args, **kwargs):
        raise AssertionError('review must never fit')
    with monkeypatch.context() as blocked:
        blocked.setattr('spectrumagent.preprocess.fitted.fit', forbidden)
        assert submit(p, 'review')['reply_status'] == 'replied'
    reviewed = read(p)
    assert len(reviewed['review']['values']) == 8
    assert set(reviewed['review']['train_cube_ids']).isdisjoint(reviewed['review']['test_cube_ids'])
    assert reviewed['review']['metrics'] == ['R²C', 'RMSEC', 'R²P', 'RMSEP', 'RPD', 'RER', '偏差']
    assert submit(p, 'execute', review_digest=reviewed['review_digest'])['reply_status'] == 'replied'
    completed = read(p)
    assert completed['status'] == 'succeeded', completed
    run_id = completed['run_id']
    actual = p['app'].state.training_runs.get(run_id)
    assert actual['training_protocol'] == 'sample_pls_foldwise_v1'
    assert p['app'].state.training_runs.artifact(run_id, 'split')['train_cube_ids'] == reviewed['review']['train_cube_ids']
    frozen = p['app'].state.training_runs.artifact(run_id, 'calibration')
    assert frozen['reviewed_plan']['revision'] == reviewed['revision']
    assert frozen['reviewed_plan']['review_digest'] == reviewed['review_digest']
    assert submit(p, 'execute', review_digest=reviewed['review_digest'])['reply_status'] == 'replied'
    assert read(p)['run_id'] == run_id
    # Fresh service = process/session restoration, no navigation replay or model call.
    tools = p['app'].state.agent_tools
    restored = RegressionPlans(tools, p['app'].state.dataset_registry, p['app'].state.preprocess_runner,
                               p['app'].state.annotation_sessions, p['app'].state.training_runs)
    assert restored.view(p['sid'])['run_id'] == run_id
    with connect_database(p['plans'].database) as db:
        assert db.execute('SELECT COUNT(*) FROM training_run').fetchone()[0] == 1
    history = p['client'].get(f"/api/v1/agent/sessions/{p['sid']}/history").json()['events']
    assert any(row['kind'] == 'step' and row['payload'].get('tool') == 'modeling.regression_form' for row in history)


def test_stale_revisions_missing_targets_and_input_changes_never_train(prepared):
    p = prepared
    assert save(p)['reply_status'] == 'replied'
    assert submit(p, 'review')['reply_status'] == 'replied'
    first = read(p)
    assert submit(p, 'save', revision=0, patch=dict(expected_revision=0, seed=99))['reply_status'] == 'needs_input'
    SampleTargets(p['plans'].database).put(p['cubes'][0], p['schema'], 200.)
    assert submit(p, 'execute', review_digest=first['review_digest'])['reply_status'] == 'needs_input'
    assert read(p)['status'] == 'draft' and read(p)['review_digest'] is None
    assert submit(p, 'review')['reply_status'] == 'replied'
    second = read(p)
    assert first['review_digest'] != second['review_digest']
    # Parameter edits invalidate the review even when source files are unchanged.
    assert submit(p, 'save', patch=dict(expected_revision=second['revision'], seed=99))['reply_status'] == 'replied'
    assert submit(p, 'execute', review_digest=second['review_digest'])['reply_status'] == 'needs_input'
    with connect_database(p['plans'].database) as db:
        db.execute('DELETE FROM sample_target WHERE cube_id=? AND schema_id=?', (p['cubes'][0], p['schema']))
    assert submit(p, 'review')['reply_status'] == 'needs_input'
    assert read(p)['status'] == 'draft'
    with connect_database(p['plans'].database) as db:
        assert db.execute('SELECT COUNT(*) FROM training_run').fetchone()[0] == 0


def test_annotation_change_and_session_isolation(prepared):
    p = prepared
    assert save(p)['reply_status'] == 'replied'
    assert submit(p, 'review')['reply_status'] == 'replied'
    reviewed = read(p)
    other = p['client'].post('/api/v1/agent/sessions', json={}).json()['id']
    assert p['client'].get(f'/api/v1/agent/sessions/{other}/regression-plan').json()['document'] == {}
    clone = {**p, 'sid': other}
    assert submit(clone, 'execute', revision=reviewed['revision'], review_digest=reviewed['review_digest'])['reply_status'] == 'needs_input'
    assert p['client'].get(f"/api/v1/agent/sessions/{p['sid']}/regression-plan?tool=modeling.regress").status_code == 400
    mask = np.zeros((8, 8), bool); mask[0] = True
    p['app'].state.annotation_sessions.edit(p['cubes'][0], mask, action='erase')
    assert submit(p, 'execute', review_digest=reviewed['review_digest'])['reply_status'] == 'needs_input'
    with connect_database(p['plans'].database) as db:
        assert not db.execute('SELECT id FROM training_run').fetchall()


def test_claim_recovery_failed_training_and_explicit_retry(prepared, monkeypatch):
    p = prepared
    save(p); submit(p, 'review')
    reviewed = read(p)
    def fail(**args):
        raise DataError('TEST_FIT_FAILED', '拟合失败测试')
    with monkeypatch.context() as blocked:
        blocked.setattr(p['plans'].training, 'regress', fail)
        assert submit(p, 'execute', review_digest=reviewed['review_digest'])['reply_status'] == 'needs_input'
    assert read(p)['status'] == 'failed'
    # Retrying an execute command alone cannot start another training.
    assert submit(p, 'execute', review_digest=reviewed['review_digest'])['reply_status'] == 'needs_input'
    assert submit(p, 'review')['reply_status'] == 'replied'
    assert submit(p, 'execute', review_digest=read(p)['review_digest'])['reply_status'] == 'replied'
    assert read(p)['status'] == 'succeeded'
    with connect_database(p['plans'].database) as db:
        db.execute("UPDATE agent_regression_plan SET status='running',run_id=?,boot_id='previous-process' WHERE session_id=?", (str(uuid4()), p['sid']))
    assert read(p)['status'] == 'interrupted'
    assert submit(p, 'execute', review_digest=read(p)['review_digest'])['reply_status'] == 'needs_input'


def test_native_ai_plan_tools_keep_numerical_confirmation(prepared):
    p = prepared
    class Model:
        def __init__(self, response): self.responses = [response, ChatResult(content='方案已更新。', finish_reason='stop')]
        def chat(self, *args): return self.responses.pop(0)
        def route_chat(self, *args, **kwargs):
            return ChatResult(content='{"intent":"annotation_workspace","explain_result":false,"confidence":"high"}', finish_reason='stop')
    def call(name, args, message):
        model = Model(tool(name, args))
        return model, list(machine_for(p['app'], p['sid'], model).message(content=message))
    _, events = call('modeling.regression_plan_get', {}, '打开回归训练方案表单')
    assert any(kind == 'step' and event['result_summary'].get('regression_plan') for kind, event in events)
    _, events = call('modeling.regression_plan_update', dict(expected_revision=0, preprocess_run_ids=p['runs'], target_schema_id=p['schema'],
        template='ks_5fold_v1', cv_folds=2, n_components=1, max_components=1), '采用 KS 五折模板并改成两折，固定 LV 1，上限 1，选择这些样品与含量字段，保存回归方案')
    assert read(p)['revision'] == 1, events
    _, events = call('modeling.regression_plan_review', dict(expected_revision=1), '审阅当前回归方案')
    reviewed = read(p)
    assert reviewed['status'] == 'reviewed', events
    model, events = call('modeling.regression_plan_execute', dict(expected_revision=1, review_digest=reviewed['review_digest']), '确认当前回归训练方案，请执行')
    check = next(event for kind, event in events if kind == 'human_check')
    assert read(p)['status'] == 'reviewed'  # LLM tool call is not user consent
    events = list(machine_for(p['app'], p['sid'], model).message(check_id=check['check_id'], decision='approve'))
    assert read(p)['status'] == 'succeeded', events
    assert any(kind == 'step' and event['tool'] == 'modeling.regression_plan_execute' and event['status'] == 'ok' for kind, event in events)


def test_configuration_intent_and_curated_recovery_errors():
    from spectrumagent.agent.authorization import operations
    from spectrumagent.data.validation import safe_error, INPUT_ERRORS
    assert operations('保存回归训练方案，使用随机种子 17') == set()
    assert operations('创建回归方案并保存标注') == {'save'}
    assert operations('保存标注') == {'save'}
    error = DataError('REGRESSION_TARGETS_MISSING', r'不应向模型发送的 E:\private\file')
    assert error.code in INPUT_ERRORS
    assert '补齐测量值' in safe_error(error)['detail']
    assert 'private' not in json.dumps(safe_error(error))
