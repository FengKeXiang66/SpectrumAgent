"""Current-state workflow, invalidation and removal of historical entry points."""
from pathlib import Path
import sys
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from test_experiments import workspace
from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.annotation.labels import LabelStore, SimpleLabelRequest
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.preprocess.current import CurrentWorkspace
from spectrumagent.modeling import ModelingError


def test_current_data_flows_through_processing_training_and_prediction(workspace, tmp_path, monkeypatch):
    from spectral.io import envi
    monkeypatch.setenv('SPECTRUMAGENT_PERMANENT_ROOT', str(workspace.root))
    identity = EngineIdentity()
    app = create_app(workspace, identity)
    registry, sessions, runner = app.state.dataset_registry, app.state.annotation_sessions, app.state.preprocess_runner
    current = CurrentWorkspace(sessions, runner)
    source = tmp_path / 'source'
    source.mkdir()
    cubes, labels = [], None
    for index in range(6):
        data = np.random.default_rng(23+index).uniform(.05, .25, (8,8,8)).astype(np.float32)
        data[:,:,index] += .5
        data[:4,:,6] += .15
        data[4:,:,7] += .15
        # Spectra can be nearly parallel while carrying useful class variation.
        data = .5 + data*.001
        envi.save_image(str(source / f'cube-{index}.hdr'), data, ext='.dat',
                        metadata={'wavelength': list(range(1100,1180,10))})
        cube = str(registry.import_path(str(source / f'cube-{index}.hdr')).datasets[0].id)
        cubes.append(cube)
        if labels is None:
            with connect_database(workspace.database) as db:
                project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?',(cube,)).fetchone()[0]
            labels = [LabelStore(workspace.database).add(SimpleLabelRequest(project_id=project,name=name,color_hex=color))
                      for name,color in (('A','#2288cc'),('B','#22aa44'))]
        app.state.segmentation_resources.prepare(cube, Parameters(n_segments=4,pca_components=3))
        mask = np.zeros((8,8),bool); mask[:4] = True
        sessions.edit(cube,mask,action='confirm',label_id=labels[0]['id'])
        sessions.edit(cube,~mask,action='confirm',label_id=labels[1]['id'])

    recipe = runner.recipes.create('current-test','当前配方',None,{'steps':[]})
    with TestClient(app,headers={'Authorization':'Bearer '+identity.token}) as client:
        for cube in cubes:
            # Processing automatically saves current annotations; no confirm or
            # version identifiers appear in this request.
            response = client.post(f'/api/v1/preprocess/current/datasets/{cube}/run',json={'recipe_id':recipe['id']})
            assert response.status_code == 200, response.text
            assert response.json()['status'] == 'succeeded', response.text
        from spectrumagent.preprocess import submissions
        with submissions.execution_context(submissions.explicit_submission(source='test')):
            batch = app.state.agent_tools.invoke('workspace.preprocess',{'cube_ids':cubes[:2],'recipe_id':recipe['id']})
        assert batch['succeeded'] == 2 and batch['failed'] == 0, batch
        members = {row['cube_id']:row for row in client.get('/api/v1/preprocess/current').json()['members']}
        assert all(row['status'] == 'ready' for row in members.values())
        annotation = members[cubes[0]]['annotation_id']
        for _ in range(2):
            saved = client.post(f'/api/v1/datasets/{cubes[0]}/annotations/save',json={})
            assert saved.status_code == 200, saved.text
            assert saved.json()['id'] == annotation
        with connect_database(workspace.database) as db:
            assert db.execute('SELECT count(*) FROM annotation_version WHERE cube_id=?',(cubes[0],)).fetchone()[0] == 1
            assert db.execute('SELECT count(*) FROM dataset_version').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM training_set_version').fetchone()[0] == 0
        # Conversation editing uses a logical recipe ID and saves in place.
        from spectrumagent.agent.tool_context import owner_session
        owner = app.state.agent_sessions.create()['id']
        token = owner_session.set(owner)
        try:
            draft = app.state.agent_tools.invoke('workspace.recipe_edit',{'recipe_id':recipe['id']})
            assert 'source_recipe_version_id' not in draft
            edited = app.state.agent_tools.invoke('preprocess.draft_update',{'draft_id':draft['draft_id'],'expected_revision':draft['revision'],'steps':[]})
            app.state.agent_tools.invoke('preprocess.draft_save',{'draft_id':draft['draft_id'],'expected_revision':edited['revision'],'recipe_id':recipe['id']})
        finally:
            owner_session.reset(token)
        # Former REST endpoints are gone, including history overlays.
        for path in ('/api/v1/dataset-versions','/api/v1/training-sets',f'/api/v1/datasets/{cubes[0]}/annotations/{annotation}/overlay'):
            assert client.get(path).status_code == 404
        listing = client.get(f'/api/v1/datasets/{cubes[0]}/annotations').json()
        assert 'versions' not in listing and listing['current']['id'] == annotation
        tool_names = {row['function']['name'] for row in app.state.agent_tools.snapshot()}
        assert 'workspace.classify' in tool_names
        assert not any(name.startswith(('versions.','training_sets.')) for name in tool_names)
        with pytest.raises(Exception) as missing:
            app.state.agent_tools.resolve('training_sets.confirm')
        assert missing.value.code == 'TOOL_NOT_FOUND'

        from test_experiment_conversation import machine_for
        from spectrumagent.agent.llm import ChatResult, ToolCall
        import json

        class LocalTrainingModel:
            def chat(self,messages,tools):
                assert any(tool['function']['name']=='workspace.classify' for tool in tools)
                return ChatResult(content=None,finish_reason='tool_calls',tool_calls=[
                    ToolCall(id='train-current',name='workspace.classify',
                             arguments_json=json.dumps(dict(cube_ids=cubes,cv_folds=2,n_components=1)))])
        owner = app.state.agent_sessions.create()['id']
        machine = machine_for(app,owner,LocalTrainingModel())
        messages = list(machine.message(content='把这些已处理好的样品拿来训练分类模型'))
        assert messages[-1][0]=='human_check',messages
        pending = messages[-1][1]
        assert pending['summary']['cube_ids_count']==len(cubes)
        assert list(machine.message(check_id=pending['check_id'],decision='reject'))[-1][1]['content'].startswith('已拒绝')

        body = dict(task='classification',target='label',cube_ids=cubes,
                    annotation_version_ids=[members[c]['annotation_id'] for c in cubes],
                    preprocess_run_ids=[members[c]['run_id'] for c in cubes],
                    cv_strategy='group_kfold',cv_folds=3,seed=17,split_strategy='none',
                    evaluation_protocol='nested_group_cv',n_components=1,max_components=2)
        diagnostic = app.state.training_runs.preflight(**{k: v for k, v in body.items()
                                                        if k not in ('n_components', 'max_components')})
        assert diagnostic['status'] == 'failed'
        assert diagnostic['leak_report']['near_duplicate_spectra']['pair_count'] > 0

        def forbidden_check(*args, **kwargs):
            pytest.fail('training must not run spectral similarity or leakage diagnostics')

        from spectrumagent.modeling import leak, run
        for module in (leak, run):
            for name in ('preflight_report', 'sample_preflight_report'):
                monkeypatch.setattr(module, name, forbidden_check)
        result = app.state.training_runs.classify(**body)
        assert result['status'] == 'succeeded', result
        assert result['leak_report']['status'] == 'skipped'
        assert result['leak_report']['passed'] is None
        for protocol in (None, 'exploratory_group_cv'):
            trained = app.state.training_runs.classify(**{**body, 'evaluation_protocol': protocol})
            assert trained['status'] == 'succeeded', trained
            assert trained['leak_report']['status'] == 'skipped'
            assert trained['leak_report']['passed'] is None
        from spectrumagent.modeling.classification_operations import operations_for
        ops = operations_for(registry,workspace)
        model = ops.models.register(result['evaluation']['evaluation_id'],'当前分类模型')
        task = ops.tasks.submit(model['id'],[cubes[0]])
        deadline = time.monotonic()+30
        while task['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.02)
            task = ops.tasks.status(task['task_id'])
        assert task['status'] == 'succeeded', task
        assert task['summary']['valid_pixels'] == 64
        truth = ops.tasks.evaluate(task['items'][0]['prediction_id'],annotation)
        assert truth['evaluation_id'] and truth['protocol'] == 'independent_inference'

        # The regression path also consumes current results directly.
        response = client.post('/api/v1/labels',json={'project_id':project,'schema':{'name':'amount','tree_path':'amount','field_type':'continuous','unit':'%','config':{}}})
        assert response.status_code < 300, response.text
        schema = response.json()['id']
        for i,cube in enumerate(cubes):
            response = client.put(f'/api/v1/models/sample-targets/{cube}/{schema}',json={'value':float(i+1)})
            assert response.status_code == 200, response.text
        regression = app.state.training_runs.regress(preprocess_run_ids=body['preprocess_run_ids'],target_schema_id=schema,cv_folds=2,n_components=1,max_components=1)
        assert regression['status'] == 'succeeded', regression
        assert regression['leak_report']['status'] == 'skipped'
        assert regression['leak_report']['passed'] is None
        regression_model = app.state.model_registry.register(regression['run_id'],'当前回归模型')
        prediction = app.state.inference_runs.create(regression_model['id'],cubes[0],members[cubes[0]]['run_id'],annotation)
        assert prediction['status'] == 'succeeded', prediction
        # A change with the SAME number of labeled pixels must invalidate a run.
        mask = np.zeros((8,8),bool);mask[0,0] = True
        sessions.edit(cubes[0],mask,action='confirm',label_id=labels[1]['id'])
        assert next(row for row in current.state()['members'] if row['cube_id']==cubes[0])['status'] == 'need_preprocess'
        sessions.save(cubes[0])
        with pytest.raises(ModelingError):
            app.state.training_runs.classify(**body)
        updated = current.process(cubes[0],recipe['id'])
        assert updated['input_fingerprint'] != runner.get(members[cubes[0]]['run_id'])['input_fingerprint']
        before_id = recipe['versions'][0]['id']
        for pipeline in ({'steps':[{'op':'snv','version':1,'params':{}}]}, {'steps':[]}):
            response = client.put(f"/api/v1/preprocess/current/recipes/{recipe['id']}",json={'pipeline':pipeline})
            assert response.status_code == 200, response.text
            if pipeline['steps']:
                assert all(row['status'] == 'need_preprocess' for row in response.json()['members'])
                processed = current.process(cubes[0],recipe['id'])
                predicted_again = app.state.inference_runs.create(regression_model['id'],cubes[0],processed['id'],annotation)
                assert predicted_again['status'] == 'succeeded'
                for key in ('mean','min','max','sample_prediction'):
                    assert predicted_again['stats'][key] == prediction['stats'][key]
        with connect_database(workspace.database) as db:
            assert db.execute('SELECT count(*) FROM preprocess_recipe_version WHERE recipe_id=?',(recipe['id'],)).fetchone()[0] == 1
        assert runner.recipes.get(recipe['id'])['versions'][0]['id'] == before_id
        # Saved model evidence survives input changes; predictions use its own
        # trained transform rather than the mutable recipe definition.
        assert ops.models.get(model['id'])['id'] == model['id']
