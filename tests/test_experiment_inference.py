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
from test_experiment_conversation import application, ScriptedModel, machine_for, tool, wait_task
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


def test_completed_inference_explain_retrain_then_confirm(application,tmp_path):
    body = config_for(tmp_path)
    body['classes'] = {1:'PE', 2:'PET'}
    model = application.state.experiments.run(ExperimentConfig.model_validate(body))['experiment_id']
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    path,_,_ = input_file(tmp_path)
    prepare(base.inference, owner, model, path)
    def chat(message, llm=None):
        return list(machine_for(application,owner,llm or ScriptedModel()).message(content=message))
    assert chat('确认执行')[-1][1]['task_result'] == 'working'
    run = base.inference.read(owner)['run_id']
    assert wait(base.inference.service,model,run)['status'] == 'succeeded'
    assert not base.inference.read(owner)['active']
    reply = chat('为什么 PET 预测错这么多')[-1][1]['content']
    assert '无真值推理' in reply and '已分类 27/27' in reply and 'PET' in reply
    assert chat('确认执行')[-1][0] == 'clarify'
    base.select(owner, model)
    reply = chat('为什么 PET 预测错这么多')[-1][1]['content']
    assert 'PET 混淆矩阵摘要' in reply and '真值 9 条' in reply
    edited = chat('解释为什么 PET 错分，调整实验方案', ScriptedModel(tool('experiments.draft_update',{
        'expected_revision':1,'name':'混淆核查'})))
    notes = next(data['result_summary']['draft_notes'] for kind,data in edited
                 if kind=='step' and data['tool']=='experiments.draft_presentation')
    assert len(notes.splitlines())>=2 and 'PET 混淆矩阵摘要' in notes
    assert chat('查询推理结果')[-1][1]['task_result'] == 'succeeded'
    clarify = chat('换个预处理再训一次')
    assert '请指定要改的预处理' in clarify[-1][1]['question'] and base.confirmation(owner) is None
    model_reply = ScriptedModel(tool('experiments.draft_update', {'expected_revision':base._read(owner)['revision'],
        'preprocessing_edit':{'action':'insert','index':2,'step':{'op':'l2'}}}))
    ready = chat('在第 2 步添加 L2 后再训一次', model_reply)
    assert ready[-1][0] == 'clarify' and '确认执行' in ready[-1][1]['question'], ready
    assert base.confirmation(owner)[0] == 'experiment'
    assert chat('确认执行')[-1][1]['task_result'] == 'working'
    task = wait_task(base.tasks, owner, base.tasks.latest(owner))
    assert task['status'] == 'succeeded' and task['experiment_id'] != model
    assert base.inference.read(owner)['run_id'] == run
    assert len(base.inference.service.history(model)) == 1


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
    first=list(machine_for(application,owner,scripted).message(content=f'使用模型 {model} 推理这份训练数据 "{path}"'))
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
    assert repeated[-1][0]=='clarify' and '没有待确认推理方案' in repeated[-1][1]['question']
    assert all(kind!='step' for kind,_ in repeated)
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
        with pytest.raises(DataError) as caught:
            dialogue.confirm(owner,'确认推理','again')
        assert caught.value.code=='INFERENCE_CONFIRMATION_REQUIRED'
        with pytest.raises(DataError):dialogue.service.cancel('foreign',model,run)
        assert dialogue.service.cancel(owner,model,run)['cancel_requested']
    finally:release.set()
    state=wait(dialogue.service,model,run)
    assert state['status']=='cancelled'
    with pytest.raises(DataError):dialogue.service.result(model,run)


def test_history_focus_changes_chat_target_without_polling_side_effects(application,tmp_path):
    model,dialogue = train(application,tmp_path)
    path,X,waves = input_file(tmp_path)
    owner = AgentStore(dialogue.database).create_session()['id']
    prepare(dialogue,owner,model,path)
    first = dialogue.confirm(owner,'确认推理','first')['inference_run_id']
    assert wait(dialogue.service,model,first)['status']=='succeeded'
    small = tmp_path/'brief.npz'
    np.savez(small,X=X[:5],wavelengths_nm=waves)
    config = dialogue.config(owner)
    second_config = config.model_copy(update={'input':config.input.model_copy(update={'paths':[str(small)]})})
    second = dialogue.service.submit(owner,second_config,dialogue.service.inspect(second_config))['inference_run_id']
    assert wait(dialogue.service,model,second)['status']=='succeeded'
    prefix = f'/api/v1/agent/sessions/{owner}/experiment-history/{model}/inferences'
    with TestClient(application) as client:
        assert client.post(f'{prefix}/{second}/focus').status_code==401
        client.headers['Authorization'] = 'Bearer '+application.state.testing_identity.token
        assert client.post(f'{prefix}/{second}/focus').json()['run_id']==second
        assert client.get(f'{prefix}/{first}').status_code==200
        assert client.get(f'{prefix}/{first}/result').status_code==200
    assert dialogue.base.focus(owner)==('inference', model, second)
    events = list(machine_for(application,owner,ScriptedModel()).message(content='为什么 PET 预测错这么多'))
    assert '已分类 5/5' in events[-1][1]['content']


@pytest.mark.parametrize('saturation',[65535.,None])
def test_envi_neighborhood_prediction_matches_independent_reference(application,tmp_path,monkeypatch,saturation):
    from spectrumagent.annotation.labels import LabelStore
    store = LabelStore(application.state.experiments.paths.database)
    project = store.projects()[0]['id']
    labels = store.ensure_names(project, ['A', 'B'])
    expected_colors = {'1': '#123456', '2': '#abcdef'}
    for row, color in zip(labels, expected_colors.values()):
        store.update(row['id'], color_hex=color)
    model,dialogue=train(application,tmp_path,image=True)
    saved_model = application.state.experiments.archive.load_model(model)
    assert {str(key): color for key, color in saved_model.config.class_colors.items()} == expected_colors
    # The model's palette stays reproducible if the project is later edited.
    store.update(labels[0]['id'], color_hex='#654321')
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
    assert result['colors'] == expected_colors
    from PIL import Image
    folder = dialogue.service.folder(model,task['inference_run_id'])
    with np.load(folder/'0.npz') as data, Image.open(folder/'0.png') as image:
        pixels = np.asarray(image)
        for label, color in expected_colors.items():
            mask = data['valid_mask'] & (data['prediction_map'] == int(label))
            assert np.all(pixels[mask] == list(bytes.fromhex(color[1:])))
    report = (folder/'report.html').read_text('utf-8')
    assert all(color in report for color in expected_colors.values())
    assert result['files'][0]['excluded']==int((~expected_mask).sum())
    assert dialogue.service.plot(model,task['inference_run_id'],0)['png_base64'].startswith('iVBOR')
    assert result['files'][0]['relative_path']==header.name
    assert (dialogue.service.folder(model,task['inference_run_id'])/'report.html').is_file()


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
        from PIL import Image
        with Image.open(dialogue.service.artifact(model,run,'0.png')) as image:
            rgb = np.asarray(image)
        assert np.all(rgb[data['exclusion_reason'] == 1] == 0)
        assert np.all(rgb[data['exclusion_reason'] == 2] == 224)
        result = dialogue.service.result(model,run)
        assert result['background_colors'] == {'brightness':'#000000', 'other':'#e0e0e0'}
        for label, color in result['colors'].items():
            selected = expected & (data['prediction_map'] == int(label))
            assert np.all(rgb[selected] == list(bytes.fromhex(color[1:])))
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
    card = json.loads(next(data['result_summary']['inference_card_json'] for kind,data in events
                           if kind=='step' and data['tool']=='experiments.inference_presentation'))
    fields = {field['label']:field['value'] for group in card['groups'] for field in group['fields']}
    assert card['ready'] and card['checked_files']==1 and fields['评价单位']=='中心像元'
    assert fields['空间邻域']=='3 × 3' and fields['输入源']=='I1 · unlabelled.npz'
    assert '模型 SHA-256' in card['raw'] and str(path) not in card['raw']
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


def test_envi_batch_keeps_empty_scene_and_continues_to_report_and_export(application,tmp_path,monkeypatch):
    from PIL import Image

    model,dialogue = train(application,tmp_path,image=True)
    waves = np.arange(1100,1145,5)
    folder = tmp_path/'batch'
    folder.mkdir()
    height,width = 36,10
    for name,level in (('01-dark',600),('02-foreground',4200)):
        header = folder/f'{name}.hdr'
        header.write_text(f'ENVI\nlines={height}\nsamples={width}\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\n'
                          'reflectance scale factor=10000\nwavelength units=nm\nwavelength={'
                          +','.join(map(str,waves))+'}\n',encoding='ascii')
        signal = np.broadcast_to(level+np.arange(9)*50,(height,width,9)).astype('<u2')
        signal.tofile(header.with_suffix('.img'))

    owner = AgentStore(dialogue.database).create_session()['id']
    dialogue.capture(owner,f'使用模型 {model} 推理 "{folder}"')
    dialogue.update(owner,InferenceUpdate(expected_revision=1,input={
        'kind':'envi','source_refs':['I1'],'wavelength_unit':'nm','mapping_window_nm':5.,'nearest_tolerance_nm':5.,
        'quality':{'min_mean':0.,'min_std':0.,'max_zero_fraction':1.,'saturation':None},
        'foreground':{'mode':'brightness_edges','wavelengths_nm':[1105.,1110.,1115.,1120.,1125.,1130.],
                      'threshold':.11,'left_min':1,'right_min':1,'edge_search_columns':0,
                      'edge_bad_fraction':.6,'edge_low':0.,'edge_high':1.}}))
    predict = ExperimentModel.predict
    seen = []
    def nonempty_only(self, X, wavelengths):
        assert len(X)>0
        seen.extend(X[:,0].tolist())
        return predict(self,X,wavelengths)
    monkeypatch.setattr(ExperimentModel,'predict',nonempty_only)
    review = dialogue.presented(owner,'review')
    assert review['presentation']['ready'] and review['presentation']['checked_files']==2
    run = dialogue.confirm(owner,'确认推理','confirm')['inference_run_id']
    service = dialogue.service
    state = wait(service,model,run)
    assert state['status']=='succeeded' and state['completed_files']==2
    dark,bright = service.result(model,run)['files']
    assert dark['name']=='01-dark.hdr' and dark['classified']==sum(dark['counts'].values())==0
    assert dark['excluded']==dark['total']==height*width
    assert dark['exclusion_counts']==dict(brightness=height*(width-2),side_edges=2*height,
                                         quality_or_neighborhood=0,image_boundary=0)
    assert len(seen)==bright['classified']>0 and min(seen)>.11
    with np.load(service.artifact(model,run,'0.npz')) as data:
        assert not data['valid_mask'].any() and not data['prediction_map'].any()
        reasons = data['exclusion_reason']
        assert np.all(reasons[:,1:-1]==1) and np.all(reasons[:,[0,-1]]==2)
    with Image.open(service.artifact(model,run,'0.png')) as image:
        rgb = np.asarray(image)
        assert np.all(rgb[:,1:-1]==0) and np.all(rgb[:,[0,-1]]==224)
    with ZipFile(BytesIO(service.export(model,run))) as bundle:
        assert bundle.testzip() is None
        report = bundle.read('report.html').decode('utf8')
        assert 'data-path="01-dark.hdr" data-vote="none"' in report and '无已分类像元' in report
        assert all(name in bundle.namelist() for name in ('0.npz','0.png','0_input.png','1.npz'))


def test_inference_draft_migrates_without_losing_existing_review(application,tmp_path):
    from spectrumagent.experiments.inference_dialogue import InferenceDialogue
    from spectrumagent.experiments.inference_presentation import pipeline

    model,dialogue = train(application,tmp_path)
    path,_,_ = input_file(tmp_path)
    owner = AgentStore(dialogue.database).create_session()['id']
    prepare(dialogue,owner,model,path)
    before = dialogue.read(owner)
    with connect_database(dialogue.database) as db:
        db.execute('ALTER TABLE inference_draft DROP COLUMN previous_document_json')
    recovered = InferenceDialogue(dialogue.base)
    assert recovered.read(owner)=={**before,'previous_document_json':None}
    assert recovered.base.confirmation(owner)==('inference',before['revision'],'review')
    assert pipeline([{'op':'savgol','derivative':1,'window':9,'polyorder':2,'delta_nm':5.},
                     {'op':'snv'},{'op':'center'}])=='SG 一阶导 (W9, 2阶, Δ5 nm) → SNV → 中心化'


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


def test_batch_envi_checks_metadata_then_hashes_each_image_once(application,tmp_path,monkeypatch):
    import os
    from pathlib import Path
    from spectrumagent.experiments import inputs
    from spectrumagent.experiments.inference import InferenceConfig

    model,dialogue = train(application,tmp_path,image=True)
    folder = tmp_path/'envi-batch'
    folder.mkdir()
    hdr = 'ENVI\nlines=8\nsamples=8\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\n'
    hdr += 'wavelength units=nm\nwavelength={1100,1105,1110,1115,1120,1125,1130,1135,1140}\n'
    for index in range(3):
        path = folder/f'image-{index}.hdr'
        path.write_text(hdr,encoding='utf8')
        rng = np.random.default_rng(index)
        path.with_suffix('.img').write_bytes(rng.integers(100,1000,(8,8,9),dtype=np.uint16).tobytes())
    owner = AgentStore(dialogue.database).create_session()['id']
    config = InferenceConfig.model_validate(dict(model_id=model,input=dict(kind='envi',paths=[str(folder)],
        wavelength_unit='nm',mapping_window_nm=5.,nearest_tolerance_nm=5.,
        quality=dict(min_mean=0.,min_std=0.,max_zero_fraction=1.,saturation=None))))
    service = dialogue.service
    image_hashes = []
    real_hash = inputs.sha256
    def track(path, check=None):
        if Path(path).suffix=='.img':
            image_hashes.append(Path(path).name)
        return real_hash(path,check)
    monkeypatch.setattr(inputs,'sha256',track)
    review = service.inspect(config)
    assert len(review['images'])==3
    assert all(item['snapshot']['change_time'] is not None for item in review['images'].values())
    assert not image_hashes

    entered = Event()
    real_inspect = service.inspect
    def hold(config, *, check=None, on_file=None, register=True):
        def progress(count):
            on_file(count)
            if count==1:
                entered.set()
                while True:
                    check()
                    time.sleep(.01)
        return real_inspect(config,check=check,on_file=progress,register=register)
    with monkeypatch.context() as patch:
        patch.setattr(service,'inspect',hold)
        run = service.submit(owner,config,review)['inference_run_id']
        try:
            assert entered.wait(3)
            state = service.status(model,run)
            assert state['phase']=='checking' and state['checked_files']==1 and state['completed_files']==0
        finally:
            service.cancel(owner,model,run)
        assert wait(service,model,run)['status']=='cancelled'
    assert not image_hashes
    deadline = time.monotonic()+3
    while not service.experiments.lock.acquire(blocking=False):
        assert time.monotonic()<deadline
        time.sleep(.01)
    service.experiments.lock.release()

    run = service.submit(owner,config,review)['inference_run_id']
    state = wait(service,model,run)
    assert state['status']=='succeeded',state
    assert sorted(image_hashes)==['image-0.img','image-1.img','image-2.img']
    sources = json.loads((service.folder(model,run)/'sources.json').read_bytes())
    assert sum(Path(key).suffix=='.img' and bool(value['sha256']) for key,value in sources.items())==3

    binary = folder/'image-1.img'
    stat = binary.stat()
    with binary.open('r+b') as stream:
        first = stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0]^1]))
    os.utime(binary,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert (binary.stat().st_size,binary.stat().st_mtime_ns)==(stat.st_size,stat.st_mtime_ns)
    run = service.submit(owner,config,review)['inference_run_id']
    state = wait(service,model,run)
    assert state['status']=='failed' and state['error']=='INFERENCE_SOURCE_CHANGED',state
    # A size change also fails at the checking phase.
    fresh = service.inspect(config)
    with binary.open('ab') as stream:
        stream.write(b'x')
    run = service.submit(owner,config,fresh)['inference_run_id']
    state = wait(service,model,run)
    assert state['status']=='failed' and state['phase']=='checking',state


def test_legacy_model_uses_existing_project_palette(application, tmp_path):
    from spectrumagent.annotation.labels import LabelStore
    from spectrumagent.annotation.palette import model_colors
    store = LabelStore(application.state.experiments.paths.database)
    labels = store.ensure_names(store.projects()[0]['id'], ['PE', 'PET'])
    body = config_for(tmp_path)
    body['classes'] = {1: 'pe', 2: 'pet'}
    config = ExperimentConfig.model_validate(body)
    # Old pickles have no class_colors field in their saved instance state.
    del config.__dict__['class_colors']
    colors = model_colors(application.state.experiments.paths.database, config)
    assert colors == {index: label['color_hex'] for index, label in enumerate(labels, 1)}
    assert len([label for field in store.tree(store.projects()[0]['id']) for label in field['labels']]) == 2


def test_material_palette_without_project_colors_and_partial_override():
    from spectrumagent.experiments.inference import class_palette
    materials = {1:'EPS', 2:'PE', 3:'PET', 4:'PP', 5:'纸', 6:'自定义'}
    expected = {'1':(255,163,35), '2':(255,62,62), '3':(63,118,255),
                '4':(38,211,79), '5':(177,99,215), '6':(6,182,212)}
    assert class_palette(list(materials), materials) == expected
    assert class_palette(list(materials), materials, {2:'#123456'}) == {**expected, '2':(18,52,86)}
