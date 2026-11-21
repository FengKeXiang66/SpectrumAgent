"""Inference replays frozen preprocessing; no labels, fitting or test-driven selection."""
from io import BytesIO
import json
from threading import Event
import time
from zipfile import ZipFile

from fastapi.testclient import TestClient
import numpy as np
import pytest

from test_experiments import config_for, workspace
from test_experiment_conversation import application, ScriptedModel, machine_for, tool
from test_experiment_archive import archived_app, restart
from backend.database import connect_database
from spectrumagent.agent.state import AgentStore
from spectrumagent.agent.tools.inference import InferenceUpdate
from spectrumagent.data import DataError
from spectrumagent.experiments.pipeline import SpectralPipeline
from spectrumagent.experiments.schema import ExperimentConfig
from spectrumagent.experiments.service import ExperimentModel


def train(app, tmp_path, image=False):
    body = config_for(tmp_path)
    if image:
        for role in ('train','test'):
            body[role].update(input_stage='neighborhood_mean',neighborhood=3,evaluation_unit='center_pixel')
    result = app.state.experiments.run(ExperimentConfig.model_validate(body))
    return result['experiment_id'], app.state.agent_tools.experiment_dialogue.inference


def wait(service, model, run):
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        state=service.status(model,run)
        if state['status'] not in {'queued','running'}:return state
        time.sleep(.02)
    raise AssertionError('Inference did not finish')


def input_file(tmp_path):
    waves=np.arange(1100,1145,5,dtype=float)
    X=np.random.default_rng(48).normal(size=(27,len(waves)))+200
    path=tmp_path/'unlabelled.npz'
    np.savez(path,X=X,wavelengths_nm=waves)
    return path,X,waves


def prepare(dialogue, owner, model, path):
    dialogue.capture(owner,f'使用模型 {model} 推理 "{path}"')
    dialogue.update(owner,InferenceUpdate(expected_revision=dialogue.read(owner)['revision'],input={
        'kind':'npz','source_refs':['I1'],'spectra_key':'X','wavelengths_key':'wavelengths_nm','input_stage':'spectra'}))
    view=dialogue.presented(owner,'review')
    assert view['can_run'],view


def test_multiturn_inference_matches_original_predictions_without_fit(application,tmp_path,monkeypatch):
    model,dialogue=train(application,tmp_path)
    path,X,waves=input_file(tmp_path)
    expected=application.state.experiments.archive.load_model(model).predict(X,waves)
    original=(application.state.experiments.folder(model)/'model.joblib').read_bytes()
    owner=AgentStore(dialogue.database).create_session()['id']
    scripted=ScriptedModel(tool('experiments.inference_update',{'expected_revision':1,'input':{
        'kind':'npz','source_refs':['I1'],'spectra_key':'X'}}),
        tool('experiments.inference_update',{'expected_revision':2,'input':{
        'kind':'npz','wavelengths_key':'wavelengths_nm','input_stage':'spectra'}}))
    first=list(machine_for(application,owner,scripted).message(content=f'使用模型 {model} 进行推理，数据 "{path}"'))
    assert first[-1][0]=='clarify' and 'wavelengths_key' in first[-1][1]['question'],first
    assert not list((application.state.experiments.folder(model)/'inferences').glob('*'))
    second=list(machine_for(application,owner,scripted).message(content='波长字段wavelengths_nm，输入未做空间均值或SG等预处理。'))
    assert second[-1][0]=='clarify' and '确认推理' in second[-1][1]['question'],second
    def cannot_fit(*args):raise AssertionError('Inference must not fit')
    monkeypatch.setattr(ExperimentModel,'fit',cannot_fit)
    monkeypatch.setattr(SpectralPipeline,'fit_transform',cannot_fit)
    confirmed=list(machine_for(application,owner,ScriptedModel()).message(content='确认推理'))
    assert confirmed[-1][1]['task_result']=='working',confirmed
    run=dialogue.read(owner)['run_id']
    state=wait(dialogue.service,model,run)
    assert state['status']=='succeeded',state
    result=dialogue.service.result(model,run)
    assert result['files'][0]['classified']==27
    assert sum(result['files'][0]['counts'].values())==27 and 'accuracy' not in json.dumps(result)
    with np.load(dialogue.service.artifact(model,run,'0.npz')) as data:
        np.testing.assert_array_equal(data['prediction'],expected)
        np.testing.assert_allclose(data['responses'],application.state.experiments.archive.load_model(model).decision_function(X,waves),rtol=0,atol=0)
    repeated=list(machine_for(application,owner,ScriptedModel()).message(content='确认推理'))
    assert repeated[-1][1]['task_result']=='working'
    assert dialogue.read(owner)['run_id']==run and len(list((application.state.experiments.folder(model)/'inferences').iterdir()))==1
    assert (application.state.experiments.folder(model)/'model.joblib').read_bytes()==original
    prefix=f'/api/v1/agent/sessions/{owner}/experiment-history/{model}/inferences'
    with TestClient(application) as client:
        assert client.get(prefix).status_code==401
        client.headers['Authorization']='Bearer '+application.state.testing_identity.token
        assert client.get(prefix).json()['items'][0]['run_id']==run
        assert client.get(prefix+'/'+run+'/result').json()['files']==result['files']
        archive=client.get(prefix+'/'+run+'/export')
        assert archive.status_code==200
        with ZipFile(BytesIO(archive.content)) as zipfile:
            assert {'result.json','0.csv','0.npz','sources.json','config.json'}.issubset(zipfile.namelist())
            assert 'model.joblib' not in zipfile.namelist()
    dialogue.service.artifact(model,run,'0.npz').write_bytes(b'changed')
    with pytest.raises(DataError):dialogue.service.export(model,run)
    damaged=application.state.experiments.archive.load_model(model)
    damaged.pipeline.fitted[0]=None
    with pytest.raises(DataError) as caught:damaged.predict(X,waves)
    assert caught.value.code=='EXPERIMENT_MODEL_INVALID'


@pytest.mark.parametrize('problem',['axis','stage','new_member'])
def test_incompatible_or_changed_inputs_cannot_predict(application,tmp_path,monkeypatch,problem):
    model,dialogue=train(application,tmp_path)
    path,X,waves=input_file(tmp_path)
    owner=AgentStore(dialogue.database).create_session()['id']
    if problem=='axis':
        np.savez(path,X=X,wavelengths_nm=waves+1)
    directory=tmp_path/'only-inference'
    if problem=='new_member':
        directory.mkdir();path.rename(directory/path.name);path=directory
    dialogue.capture(owner,f'模型 {model} 推理 "{path}"')
    dialogue.update(owner,InferenceUpdate(expected_revision=1,input={'kind':'npz','source_refs':['I1'],
        'spectra_key':'X','wavelengths_key':'wavelengths_nm','input_stage':'neighborhood_mean' if problem=='stage' else 'spectra'}))
    view=dialogue.presented(owner,'review')
    if problem!='new_member':
        assert not view['can_run']
        with pytest.raises(DataError):dialogue.confirm(owner,'确认推理','confirm')
        return
    np.savez(directory/'new.npz',X=X,wavelengths_nm=waves)
    def cannot_predict(*args):raise AssertionError('Changed input must fail before prediction')
    monkeypatch.setattr(ExperimentModel,'decision_function',cannot_predict)
    result=dialogue.confirm(owner,'确认推理','confirm')
    state=wait(dialogue.service,model,result['inference_run_id'])
    assert state['status']=='failed' and state['error']=='INFERENCE_SOURCE_CHANGED'


def test_inference_cancel_ownership_and_duplicate_confirmation(application,tmp_path,monkeypatch):
    model,dialogue=train(application,tmp_path)
    path,_,_=input_file(tmp_path)
    owner=AgentStore(dialogue.database).create_session()['id']
    prepare(dialogue,owner,model,path)
    entered,release=Event(),Event()
    original=ExperimentModel.decision_function
    def held(self,*args):
        entered.set();assert release.wait(10);return original(self,*args)
    monkeypatch.setattr(ExperimentModel,'decision_function',held)
    try:
        accepted=dialogue.confirm(owner,'确认推理','confirm')
        run=accepted['inference_run_id']
        assert entered.wait(5)
        assert dialogue.confirm(owner,'确认推理','again')['inference_run_id']==run
        with pytest.raises(DataError):dialogue.service.cancel('foreign',model,run)
        assert dialogue.service.cancel(owner,model,run)['cancel_requested']
    finally:release.set()
    state=wait(dialogue.service,model,run)
    assert state['status']=='cancelled'
    with pytest.raises(DataError):dialogue.service.result(model,run)


@pytest.mark.parametrize('saturation',[65535.,None])
def test_envi_neighborhood_prediction_matches_independent_reference(application,tmp_path,monkeypatch,saturation):
    model,dialogue=train(application,tmp_path,image=True)
    waves=np.arange(1100,1145,5,dtype=float)
    raw=np.random.default_rng(24).integers(3000,12000,(68,10,9),dtype=np.uint16)
    raw[31,3,4]=65535;raw[32,6]=0
    header=tmp_path/'unlabelled.hdr'
    header.with_suffix('.img').write_bytes(raw.tobytes())
    header.write_text('ENVI\nlines=68\nsamples=10\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\nreflectance scale factor=10000\nwavelength units=nm\nwavelength={'+','.join(map(str,waves))+'}\n',encoding='utf-8')
    quality={'min_mean':.02,'min_std':.002,'max_zero_fraction':.05,'saturation':saturation}
    owner=AgentStore(dialogue.database).create_session()['id']
    dialogue.capture(owner,f'使用模型 {model} 推理“{header}”')
    dialogue.update(owner,InferenceUpdate(expected_revision=1,input={'kind':'envi','source_refs':['I1'],'wavelength_unit':'nm',
        'mapping_window_nm':5.,'nearest_tolerance_nm':5.,'quality':quality}))
    config=dialogue.config(owner)
    assert config.input.quality.saturation==saturation
    reviewed=dialogue.service.inspect(config)
    expected_mask=np.zeros(raw.shape[:2],bool);spectra=[]
    for r in range(1,67):
        for c in range(1,9):
            block=raw[r-1:r+2,c-1:c+2]
            if (saturation is not None and np.any(block>=saturation)) or np.any((block==0).mean(axis=2)>.05):continue
            total=np.zeros(9)
            for dr in (-1,0,1):
                for dc in (-1,0,1):total+=raw[r+dr,c+dc].astype(float)/10000
            spectra.append((total/9).astype(np.float32));expected_mask[r,c]=True
    expected=application.state.experiments.archive.load_model(model).predict(np.stack(spectra),waves)
    def cannot_fit(*args):raise AssertionError('Must not refit')
    monkeypatch.setattr(SpectralPipeline,'fit_transform',cannot_fit)
    task=dialogue.service.submit(owner,config,reviewed)
    state=wait(dialogue.service,model,task['inference_run_id'])
    assert state['status']=='succeeded',state
    with np.load(dialogue.service.artifact(model,task['inference_run_id'],'0.npz')) as data:
        np.testing.assert_array_equal(data['valid_mask'],expected_mask)
        np.testing.assert_array_equal(data['prediction_map'][expected_mask],expected)
    result=dialogue.service.result(model,task['inference_run_id'])
    assert result['files'][0]['excluded']==int((~expected_mask).sum())
    assert dialogue.service.plot(model,task['inference_run_id'],0)['png_base64'].startswith('iVBOR')


def test_explicit_foreground_masks_centers_without_eroding_brightness(application,tmp_path):
    model,dialogue=train(application,tmp_path,image=True)
    waves=np.arange(1100,1145,5,dtype=float)
    raw=np.random.default_rng(38).integers(3000,12000,(68,10,9),dtype=np.uint16)
    raw[:,1]=20000+np.arange(9)*100
    raw[:,-1]=0
    raw[32,4]=600+np.arange(9)*100
    raw[32,3]=8000+np.arange(9)*100
    raw[32,6]=0
    header=tmp_path/'foreground.hdr'
    header.with_suffix('.img').write_bytes(raw.tobytes())
    header.write_text('ENVI\nlines=68\nsamples=10\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\nreflectance scale factor=10000\nwavelength units=nm\nwavelength={'+','.join(map(str,waves))+'}\n',encoding='utf-8')
    fg={'mode':'brightness_edges','wavelengths_nm':[1100.,1110.,1120.],'threshold':.4,'left_min':1,'right_min':1,
        'edge_search_columns':2,'edge_bad_fraction':.6,'edge_low':.005,'edge_high':1.4}
    owner=AgentStore(dialogue.database).create_session()['id']
    dialogue.capture(owner,f'使用模型 {model} 推理“{header}”')
    dialogue.update(owner,InferenceUpdate(expected_revision=1,input={'kind':'envi','source_refs':['I1'],'wavelength_unit':'nm',
        'mapping_window_nm':5.,'nearest_tolerance_nm':5.,'quality':{'min_mean':0.,'min_std':.002,'max_zero_fraction':.05,'saturation':None},'foreground':fg}))
    config=dialogue.config(owner)
    reviewed=dialogue.service.inspect(config)
    accepted=dialogue.service.submit(owner,config,reviewed)
    run=accepted['inference_run_id']
    assert wait(dialogue.service,model,run)['status']=='succeeded'
    level=np.median(raw[:,:,[0,2,4]].astype(np.float32)/10000,axis=2)
    expected=np.zeros((68,10),bool)
    for r in range(1,67):
        for c in range(3,8):
            if level[r,c]<=.4:continue
            block=raw[r-1:r+2,c-1:c+2].astype(float)/10000
            if np.any(block.std(axis=2)<=.002) or np.any((block==0).mean(axis=2)>.05):continue
            expected[r,c]=True
    assert expected[32,3] and not expected[32,4] # brightness is a center gate, not a nine-pixel gate
    with np.load(dialogue.service.artifact(model,run,'0.npz')) as data:
        np.testing.assert_array_equal(data['valid_mask'],expected)
        np.testing.assert_array_equal(data['exclusion_reason']==0,expected)
    row=dialogue.service.result(model,run)['files'][0]
    assert row['edges']=={'left':2,'right':1}
    assert sum(row['exclusion_counts'].values())==row['excluded']
    assert sum(row['counts'].values())+row['excluded']==68*10
    prefix=f'/api/v1/agent/sessions/{owner}/experiment-history/{model}/inferences/{run}/plots/0'
    with TestClient(application) as client:
        client.headers['Authorization']='Bearer '+application.state.testing_identity.token
        assert client.get(prefix+'?kind=input').json()['png_base64'].startswith('iVBOR')
        assert client.get(prefix+'?kind=other').status_code==400
    # Explicitly disabling foreground must replace the old parameter object.
    dialogue.update(owner,InferenceUpdate(expected_revision=dialogue.read(owner)['revision'],input={'kind':'envi','foreground':{'mode':'none'}}))
    assert dialogue.config(owner).input.foreground.mode=='none'
    dialogue.update(owner,InferenceUpdate(expected_revision=dialogue.read(owner)['revision'],reset=True,input={
        'kind':'envi','source_refs':['I1'],'wavelength_unit':'nm','mapping_window_nm':5.,'nearest_tolerance_nm':5.,
        'quality':{'min_mean':0.,'min_std':.002,'max_zero_fraction':.05,'saturation':None},'foreground':{'mode':'none'}}))
    assert dialogue.config(owner).model_id==model
    assert dialogue.read(owner)['reviewed_revision'] is None


def test_real_model_null_fields_inherit_without_reasking(application,tmp_path):
    model,dialogue=train(application,tmp_path,image=True)
    path,_,_=input_file(tmp_path)
    owner=AgentStore(dialogue.database).create_session()['id']
    scripted=ScriptedModel(tool('experiments.inference_update',{'expected_revision':1,'input':{
        'kind':'npz','source_refs':['I1'],'spectra_key':'X','wavelengths_key':'wavelengths_nm',
        'input_stage':'neighborhood_mean','neighborhood':3,'evaluation_unit':None}}))
    events=list(machine_for(application,owner,scripted).message(content=f'使用上次归档的模型推理，输入“{path}”，已经做过3×3均值。'))
    assert events[-1][0]=='clarify' and '确认推理' in events[-1][1]['question'],events
    assert '评价单位：中心像元（沿用归档模型）' in events[-1][1]['question']
    assert '请补充或明确' not in events[-1][1]['question']
    assert dialogue.read(owner)['document']['model_id']==model
    assert dialogue.view(owner)['model_evaluation_unit']=='center_pixel'
    before=dialogue.read(owner)
    dialogue.update(owner,InferenceUpdate(expected_revision=before['revision'],model_id=None,input={
        'kind':'npz','source_refs':None,'spectra_key':None,'wavelengths_key':None,'input_stage':None,'neighborhood':None,'evaluation_unit':None}))
    assert dialogue.read(owner)['document']==before['document']
    assert dialogue.config(owner).input.evaluation_unit=='center_pixel'
    # Existing drafts created before this fix must recover without retyping input.
    legacy=dialogue.read(owner)['document']
    legacy['input']['evaluation_unit']=None
    legacy['input']['neighborhood']=None
    with connect_database(dialogue.database) as db:
        db.execute('UPDATE inference_draft SET document_json=?,reviewed_revision=NULL,review_json=NULL WHERE session_id=?',
                   (json.dumps(legacy),owner))
    view=dialogue.presented(owner,'recheck')
    assert view['can_run'] and '确认推理' in view['question']
    assert '评价单位：中心像元' in view['plan']
    assert dialogue.config(owner).input.neighborhood==3


def test_inference_results_survive_restart(archived_app,tmp_path):
    model,dialogue=train(archived_app,tmp_path)
    path,_,_=input_file(tmp_path)
    owner=AgentStore(dialogue.database).create_session()['id']
    prepare(dialogue,owner,model,path)
    task=dialogue.confirm(owner,'确认推理','confirm')
    assert wait(dialogue.service,model,task['inference_run_id'])['status']=='succeeded'
    original=dialogue.service.result(model,task['inference_run_id'])
    fresh=restart(archived_app,tmp_path)
    service=fresh.state.agent_tools.experiment_dialogue.inference.service
    assert service.result(model,task['inference_run_id'])==original
    assert service.history(model)[0]['run_id']==task['inference_run_id']
