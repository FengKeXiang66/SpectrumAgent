"""Training-only Study, inference foreground proposals and business exclusions."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from threading import Event
import time
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.identity import EngineIdentity
from test_experiment_conversation import application, machine_for, patch_for, ScriptedModel, tool, wait_task, workspace
from test_experiment_inference import train, wait
from test_group_split import demo_data
from spectrumagent.agent.state import AgentStore
from spectrumagent.data import DataError
from spectrumagent.agent.tools.experiments import DraftUpdate
from spectrumagent.agent.tools.inference import InferenceUpdate
from spectrumagent.app import create_app
from spectrumagent.experiments.group_split import scan
from spectrumagent.experiments.exclusions import ExclusionRules
from spectrumagent.experiments.inference import filtered_files
from spectrumagent.experiments.pairing import inventory
from spectrumagent.experiments import inputs, study
from spectrumagent.experiments.inputs import load_input
from spectrumagent.experiments.pipeline import SpectralPipeline
from spectrumagent.experiments.schema import ExperimentConfig, ImageInput
from spectrumagent.experiments.service import ExperimentService, write_json
from spectrumagent.storage import guard


def grouped_draft(app, tmp_path):
    body, patch = patch_for(tmp_path)
    training, test = (Path(body[role]['paths'][0]) for role in ('train','test'))
    waves = np.array(body['wavelengths_nm'])
    rng = np.random.default_rng(71)
    labels = np.tile([1,2],48)
    groups = np.repeat(np.arange(12),8).astype(str)
    curve = np.linspace(-1,1,len(waves))**2
    X = rng.normal(0,.01,(len(labels),len(waves))) + (labels[:,None]==2)*curve + 3
    for group in range(12):
        X[groups==str(group)] += group*.5
    np.savez(training,X=X,y=labels,wavelengths_nm=waves,physical_group=groups)
    patch['train']['groups_key'] = 'physical_group'
    base = app.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    base.capture(owner,f'训练数据 "{training}" 测试数据 "{test}"')
    base.update(owner,DraftUpdate.model_validate(patch))
    return base,owner,training,test


def until(manager,owner,identifier):
    deadline = time.monotonic()+20
    while time.monotonic()<deadline:
        state = manager.status(owner,identifier)
        if state['status'] not in {'queued','running'}:
            return state
        time.sleep(.025)
    raise AssertionError('Study did not reach a terminal state')


def chat(app,owner,text):
    return list(machine_for(app,owner,ScriptedModel()).message(content=text))


def test_group_study_isolates_holdout_and_applies_recommendation(application,tmp_path,monkeypatch):
    base,owner,training,test = grouped_draft(application,tmp_path)
    manager = base.study
    real_load = np.load
    real_fit = SpectralPipeline.fit_transform
    fitting = []
    block_holdout = True
    def load(file,*args,**kwargs):
        if isinstance(file,(str,Path)) and Path(file)==test:
            assert not block_holdout, 'Study opened the holdout'
        return real_load(file,*args,**kwargs)
    def fit(pipe,array):
        fitting.append(np.array(array))
        return real_fit(pipe,array)
    monkeypatch.setattr(np,'load',load)
    monkeypatch.setattr(SpectralPipeline,'fit_transform',fit)
    proposal = chat(application,owner,'分析一下哪种预处理和潜变量准确率最高，折数 3，潜变量 1-3；预处理候选：原谱、SG1；归一化候选：无、L2')
    assert proposal[-1][0]=='clarify' and '确认寻优' in proposal[-1][1]['question'],proposal
    assert manager.latest(owner) is None
    submitted = chat(application,owner,'确认运行 Study')
    identifier = next(payload['result_summary']['study_id'] for kind,payload in submitted if kind=='step')
    completed = until(manager,owner,identifier)
    assert completed['status']=='succeeded',completed
    result = manager.result(owner,identifier)
    assert result['folds']==3 and result['group_count']==12 and len(result['candidates'])==12
    recommended = next(row for row in result['candidates'] if row['id']==result['recommended'])
    viable = [row for row in result['candidates'] if row.get('cv_f1',-1)>=result['one_se_threshold']]
    assert recommended['n_components']==min(row['n_components'] for row in viable)
    valid = [row for row in result['candidates'] if 'cv_f1' in row]
    assert len({round(row['cv_f1'],4) for row in valid})>1
    assert [row['cv_f1'] for row in valid]==sorted([row['cv_f1'] for row in valid],reverse=True)
    with real_load(manager.folder(identifier)/'training_cache.npz') as cache:
        assignment, groups, X = cache['fold_assignment'], cache['groups'], cache['X']
        assert all(len(set(assignment[groups==group]))==1 for group in set(groups))
        assert len(fitting)==12
        for observed in fitting:
            assert any(np.array_equal(observed,X[assignment!=fold]) for fold in range(1,4))
    assert str(test) not in json.loads((manager.folder(identifier)/'sources.json').read_bytes())
    block_holdout = False
    identity = EngineIdentity()
    fresh = create_app(base.service.paths,identity)
    stored = fresh.state.agent_tools.experiment_dialogue
    with TestClient(fresh) as client:
        client.headers['Authorization'] = 'Bearer '+identity.token
        url = f'/api/v1/agent/sessions/{owner}/studies/{identifier}/result'
        assert client.get(url).json()['recommended']==result['recommended']
    view = chat(fresh,owner,'采用推荐方案新建正式训练')
    assert view[-1][0]=='clarify' and '确认执行' in view[-1][1]['question'],view
    assert stored.tasks.latest(owner) is None
    config = stored._config(stored._read(owner))
    assert config.train.groups_key=='physical_group' and config.model.n_components==recommended['n_components']
    chat(fresh,owner,'确认执行')
    task = wait_task(stored.tasks,owner,stored.tasks.latest(owner))
    assert task['status']=='succeeded',task


def test_study_cancel_recovery_and_exploratory_confirmation(application,tmp_path,monkeypatch):
    base,owner,_,_ = grouped_draft(application,tmp_path)
    base.update(owner,DraftUpdate(expected_revision=1,train={'kind':'npz','groups_key':None}))
    manager = base.study
    view = chat(application,owner,'寻优，潜变量 1-2')
    assert '缺少实物／批次分组' in view[-1][1]['question']
    preview_id = next(p['result_summary']['study_preview_id'] for kind,p in view if kind=='step')
    confirmation = base.confirmation(owner)
    for command in ('调整寻优，步长 1，每类上限 1200','修改寻优，潜变量 1-2'):
        rejected = chat(application,owner,command)
        steps = [p for kind,p in rejected if kind=='step']
        assert [p['tool'] for p in steps]==['experiments.study_preview_retained']
        assert steps[0]['result_summary']['retained_study_preview_id']==preview_id
        assert '上一张寻优方案仍待确认' in rejected[-1][1]['question']
        assert base.confirmation(owner)==confirmation
    assert '确认探索性寻优' in chat(application,owner,'确认执行')[-1][1]['question']
    entered,release = Event(),Event()
    original = SpectralPipeline.fit_transform
    def blocked(pipe,X):
        entered.set()
        assert release.wait(7)
        return original(pipe,X)
    monkeypatch.setattr(SpectralPipeline,'fit_transform',blocked)
    task = chat(application,owner,'确认探索性寻优')
    identifier = next(payload['result_summary']['study_id'] for kind,payload in task if kind=='step')
    assert identifier==preview_id
    try:
        assert entered.wait(7)
        manager.cancel(owner,identifier)
    finally:
        release.set()
    assert until(manager,owner,identifier)['status']=='cancelled'
    stale = str(uuid4())
    # Pre-project archive fixture: startup, not a permissive folder lookup,
    # establishes its owner from the saved session receipt.
    legacy_folder = manager.root/stale
    guard.mkdir(legacy_folder,parents=True)
    write_json(legacy_folder/'status.json',dict(study_id=stale,session_id=owner,status='running',
                                                        started_at=time.time(),finished_at=None))
    fresh = create_app(base.service.paths,EngineIdentity())
    assert fresh.state.agent_tools.experiment_dialogue.study.status(owner,stale)['status']=='interrupted'


def envi_scene(path,waves):
    shape = (64,40,len(waves))
    X = np.broadcast_to(25+np.arange(len(waves)),shape).copy()
    X[4:60,10:30] += 700
    X[:,0:2] += 2100
    path.write_text('ENVI\nsamples=40\nlines=64\nbands='+str(len(waves))+
                    '\nheader offset=0\nfile type=ENVI Standard\ndata type=12\ninterleave=bip\nbyte order=0\n'
                    'reflectance scale factor=10000\nwavelength units=Nanometers\nwavelength={'+
                    ','.join(str(value) for value in waves)+'}\n',encoding='ascii')
    path.with_suffix('.img').write_bytes(X.astype('<u2').tobytes())


def test_probe_confirm_exclusions_and_verified_preset(application,tmp_path):
    model,inference = train(application,tmp_path,image=True)
    folder = tmp_path/'envi'
    folder.mkdir()
    path = folder/'scene.hdr'
    envi_scene(path, np.arange(1100,1145,5))
    (folder/'omit_scene.hdr').write_text('not an ENVI file')
    rule = tmp_path/'排除范围.json'
    rule.write_text(json.dumps({'prefixes':['omit_']}),encoding='utf-8')
    owner = AgentStore(inference.database).create_session()['id']
    inference.capture(owner,f'使用模型 {model} 推理 "{folder}"，排除规则 "{rule}"')
    revision = inference.read(owner)['revision']
    inference.update(owner,InferenceUpdate(expected_revision=revision,input={
        'kind':'envi','source_refs':['I1'],'exclusions_ref':'I2','wavelength_unit':'nm',
        'mapping_window_nm':5.,'nearest_tolerance_nm':2.,
        'quality':{'min_mean':0.,'min_std':0.,'max_zero_fraction':1.,'saturation':None}}))
    view = inference.presented(owner,'probe-auto')
    assert view['probe'] and not view['can_run']
    assert not view['presentation']['ready'] and '请选择' in view['presentation']['todo']
    probe = inference.probe_result(owner)
    assert len(probe['suggestion'])==9 and probe['png_base64'] and probe['estimated_left']>=2
    assert probe['excluded_files'][0]['reason']=='前缀 omit_'
    adopted = chat(application,owner,'采用前景建议')
    assert adopted[0] == ('progress', {'phase':'tool','tool':'experiments.inference_inspect'})
    assert '确认推理' in adopted[-1][1]['question'] and '按范围排除 1 幅' in adopted[-1][1]['question']
    card = json.loads(next(data['result_summary']['inference_card_json'] for kind,data in adopted
                           if kind=='step' and data['tool']=='experiments.inference_presentation'))
    assert card['ready'] and card['checked_files']==1 and card['excluded_files']==1
    assert {'label':'前景规则','before':'待选择','after':'亮度与左右边缘'} in card['changes']
    assert str(folder) not in json.dumps(card,ensure_ascii=False)
    assert inference.read(owner)['run_id'] is None
    chat(application,owner,'确认推理')
    run = inference.read(owner)['run_id']
    assert wait(inference.service,model,run)['status']=='succeeded'
    assert inference.service.result(model,run)['excluded_files'][0]['file']=='omit_scene.hdr'
    inference.update(owner,InferenceUpdate(expected_revision=inference.read(owner)['revision'],reset=True,input={
        'kind':'envi','source_refs':['I1'],'exclusions_ref':'I2'}))
    preset = inference.presented(owner,'reuse-review')
    assert preset['can_run'] and '上次已核验的 ENVI 预设' in preset['plan']
    assert inference.config(owner).input.foreground.model_dump()==probe['suggestion']
    from test_experiment_conversation import ScriptedModel, machine_for, tool
    revised = ScriptedModel(tool('experiments.inference_update', {
        'expected_revision':inference.read(owner)['revision'],
        'input':{'kind':'envi','foreground':{'mode':'brightness_edges','threshold':.11}}}))
    events = list(machine_for(application,owner,revised).message(content='把推理亮度阈值改为 0.11'))
    change = json.loads(next(data['result_summary']['inference_card_json'] for kind,data in events
                             if kind=='step' and data['tool']=='experiments.inference_presentation'))
    assert change['ready'] and len(change['changes'])==1
    assert change['changes'][0]['label']=='亮度阈值' and change['changes'][0]['after']=='0.11'
    assert 'foreground' not in json.loads(inference.read(owner)['previous_document_json'])['input']
    reprobe = chat(application,owner,'探查前景')
    card = json.loads(next(data['result_summary']['inference_card_json'] for kind,data in reprobe
                           if kind=='step' and data['tool']=='experiments.inference_presentation'))
    assert not card['ready'] and not card['changes'] and inference.base.confirmation(owner) is None


def test_inline_inference_edit_uses_current_probe_without_model_and_requires_new_confirmation(application,tmp_path):
    model,inference = train(application,tmp_path,image=True)
    header = tmp_path/'scene.hdr'
    envi_scene(header,np.arange(1100,1145,5))
    owner = AgentStore(inference.database).create_session()['id']
    inference.capture(owner,f'使用模型 {model} 推理 "{header}"')
    inference.update(owner,InferenceUpdate(expected_revision=1,input={
        'kind':'envi','source_refs':['I1'],'wavelength_unit':'nm','mapping_window_nm':5.,
        'nearest_tolerance_nm':2.,'quality':{'min_mean':0.,'min_std':0.,'max_zero_fraction':1.,'saturation':5000.}}))
    initial = inference.presented(owner,'first')
    assert initial['probe'] and not initial['can_run']
    suggested = inference.probe_result(owner)['suggestion']

    def apply(revision, **patch):
        text = '应用推理参数 '+json.dumps({'expected_revision':revision,**patch})
        events = chat(application,owner,text)
        card = next(json.loads(data['result_summary']['inference_card_json']) for kind,data in events
                    if kind=='step' and data['tool']=='experiments.inference_presentation')
        return card

    card = apply(2, quality={'max_zero_fraction':.8},foreground={'mode':'brightness_edges','threshold':.11})
    assert card['ready'] and card['revision']==3
    config = inference.config(owner)
    assert config.input.foreground.model_dump()=={**suggested,'threshold':.11}
    assert config.input.quality.model_dump()==dict(min_mean=0.,min_std=0.,max_zero_fraction=.8,saturation=5000.)
    assert {row['label'] for row in card['changes']} >= {'前景规则','亮度阈值','零值比例上限'}
    assert inference.read(owner)['run_id'] is None
    assert not inference.service.history(model)

    stale = apply(2,quality={'saturation':None})
    assert '草稿已更新' in stale['todo'] and stale['revision']==3 and stale['ready']
    invalid = apply(3,quality={'max_zero_fraction':2.})
    assert 'max_zero_fraction' in invalid['todo'] and invalid['revision']==3
    assert inference.config(owner).input.quality.max_zero_fraction==.8
    off = apply(3,quality={'saturation':None},foreground={'mode':'none'})
    assert off['ready'] and off['revision']==4
    assert inference.config(owner).input.quality.saturation is None
    assert inference.config(owner).input.foreground.mode=='none'
    assert not inference.probe_result(owner)['current']
    previous, target = inference.read(owner), inference.base.confirmation(owner)
    blocked = apply(4,foreground={'mode':'brightness_edges','threshold':.11})
    assert blocked['ready'] and blocked['revision']==4 and '重新探查前景' in blocked['todo']
    assert inference.read(owner)==previous and inference.base.confirmation(owner)==target
    chat(application,owner,'探查前景')
    assert inference.probe_result(owner)['current']
    reopened = apply(4,foreground={'mode':'brightness_edges','threshold':.11})
    assert reopened['ready'] and reopened['revision']==5 and inference.config(owner).input.foreground.threshold==.11
    assert inference.read(owner)['run_id'] is None
    chat(application,owner,'确认推理')
    run = inference.read(owner)['run_id']
    assert run and wait(inference.service,model,run)['status']=='succeeded'


def test_roi_sampling_cap_and_split_preview_exclusions(tmp_path,workspace):
    hdr = tmp_path/'uneven.hdr'
    waves = np.arange(1100,1145,5,dtype=float)
    envi_scene(hdr,waves)
    roi = tmp_path/'uneven.json'
    roi.write_text(json.dumps({'imageWidth':40,'imageHeight':64,'shapes':[
        {'label':'PE','shape_type':'rectangle','points':[[1,3],[18,58]]},
        {'label':'PP','shape_type':'rectangle','points':[[21,6],[24,14]]}]}),encoding='utf8')
    common = dict(kind='roi_images',members=[dict(header_path=str(hdr),roi_path=str(roi),sample_id='object1')],
                  neighborhood=1,wavelength_unit='nm',mapping_window_nm=5.,nearest_tolerance_nm=0.,
                  quality=dict(min_mean=0.,min_std=0.,max_zero_fraction=1.,saturation=None))
    first = load_input(ImageInput(**common,max_per_class=15,sampling_seed=9),waves,{1:'PE',2:'PP'})
    second = load_input(ImageInput(**common,max_per_class=15,sampling_seed=9),waves,{1:'PE',2:'PP'})
    full = load_input(ImageInput(**common),waves,{1:'PE',2:'PP'})
    assert first.origins==second.origins and len(first.y)==30 and len(full.y)>len(first.y)
    assert first.sampling['class_counts']['1']['eligible']>first.sampling['class_counts']['2']['eligible']
    test_hdr = tmp_path/'holdout.hdr'
    test_roi = tmp_path/'holdout.json'
    envi_scene(test_hdr,waves)
    shifted = np.fromfile(test_hdr.with_suffix('.img'),dtype='<u2')+13
    test_hdr.with_suffix('.img').write_bytes(shifted.tobytes())
    test_roi.write_bytes(roi.read_bytes())
    service = ExperimentService(workspace)
    result = service.run(ExperimentConfig(name='only cap train',wavelengths_nm=waves.tolist(),classes={1:'PE',2:'PP'},
        train={**common,'max_per_class':15,'sampling_seed':9},
        test={**common,'members':[dict(header_path=str(test_hdr),roi_path=str(test_roi),sample_id='object2')]},
        preprocessing=[],model=dict(n_components=1,scale=False,max_iter=1000),test_usage='independent_test'))
    archive = service.folder(result['experiment_id'])
    assert result['config']['training_sampling']==first.sampling
    assert result['metrics']['test']['n']==len(full.y)
    assert len(json.loads((archive/'train_origins.json').read_bytes())['origins'])==30
    assert '训练类别抽样上限 15' in (archive/'report.html').read_text('utf8')
    _, mapping = demo_data(tmp_path/'split')
    images = list((mapping.parent/'原图').iterdir())
    annotations = next(path for path in mapping.parent.iterdir() if path.is_dir() and path.name!='原图')
    rows,_,excluded = scan({'原图':[str(images[0].parent)],'标注':[str(annotations)],'分组表':[str(mapping)]},
                           {'prefixes':['PE-1-']})
    assert rows and len(excluded)==2 and all(item['reason']=='前缀 PE-1-' for item in excluded)


def test_exclusion_matches_scanned_subfolders_and_ignores_ancestors(tmp_path):
    root = tmp_path/'黑色测试工作区'
    excluded = root/'103061黑色PP餐盒'/'001.hdr'
    included = root/'pe'/'001.hdr'
    labels = tmp_path/'标注'
    labels.mkdir()
    for path in (excluded,included):
        path.parent.mkdir(parents=True)
        envi_scene(path,np.arange(1100,1145,5))
        record = dict(source_hdr=str(path),imageWidth=40,imageHeight=64,
                      shapes=[dict(label='PE',shape_type='rectangle',points=[[0,0],[3,3]])])
        (labels/(path.parent.name+'.json')).write_text(json.dumps(record),encoding='utf8')
    rules = ExclusionRules(codes={'103061':'黑色PP餐盒'},name_fragments=['黑色'])
    assert rules.reason(excluded,root)=='关键词 黑色、编码 103061（黑色PP餐盒）'
    assert not rules.reason(included,root) and not rules.reason(excluded)
    report = inventory({'待划分原图':[root],'待划分标注':[labels]},roles=('待划分',),exclusions=rules)
    assert not report['issues'] and [row['hdr'] for row in report['pairs']]==[str(included)]
    assert report['excluded'][0]['relative_file']=='103061黑色PP餐盒/001.hdr'
    spec = SimpleNamespace(kind='envi',paths=[str(root)],exclusions=rules)
    files,removed = filtered_files(spec)
    assert files==[included] and removed[0]['file']=='103061黑色PP餐盒/001.hdr'
    spec.paths = [str(excluded)]
    assert filtered_files(spec)==([excluded],[])


def test_multiple_sg_windows_are_default_and_selectable():
    waves = np.arange(1100.,1205.,5.)
    def windows(options):
        return {step['window'] for item in options['preparations'] for step in item['steps'] if step['op']=='savgol'}
    default = study.options('寻优，潜变量 2-16',waves,[])
    assert windows(default)=={9,15} and len(default['preparations'])==15
    chosen = study.options('SG窗口：5、11；预处理候选：SG1；归一化候选：SNV',waves,[])
    assert windows(chosen)=={5,11} and len({item['name'] for item in chosen['preparations']})==2
    assert windows(study.options('SG窗口：9、15\n调整寻优，SG窗口：7',waves,[]))=={7}
    with pytest.raises(ValueError,match='奇数'):
        study.options('SG窗口：9、14',waves,[])


def test_upper_bound_hint_and_progress_write_throttle(application,tmp_path,monkeypatch):
    base,owner,_,_ = grouped_draft(application,tmp_path)
    manager = base.study
    tick = 0.
    writes = []
    real_write = study.write_json
    monkeypatch.setattr(study,'monotonic',lambda:tick)
    def observe(path,payload):
        if path.name=='status.json':
            writes.append((payload['phase'],payload['status'],payload.get('fold')))
        return real_write(path,payload)
    monkeypatch.setattr(study,'write_json',observe)
    def fixed_results(config,data,folds,opts,progress,groups=None):
        assert groups is not None
        nonlocal tick
        for fold,elapsed in enumerate((0.,.24,.25,.49,.50),1):
            tick = elapsed
            progress(candidate=1,total=2,component=2,fold=fold,folds=5)
        return {'best':1,'recommended':1,'component_upper_reached':True,'candidates':[]}
    monkeypatch.setattr(study,'evaluate',fixed_results)
    chat(application,owner,'寻优，潜变量 1-2')
    submitted = chat(application,owner,'确认寻优')
    identifier = next(payload['result_summary']['study_id'] for kind,payload in submitted if kind=='step')
    assert until(manager,owner,identifier)['status']=='succeeded'
    assert writes==[('checking','queued',None),('preparing','running',None),('evaluating','running',None),
                    ('evaluating','running',3),('evaluating','running',5),('reporting','succeeded',5)]
    assert study.UPPER_BOUND_HINT in chat(application,owner,'查看寻优结果')[-1][1]['content']


def test_only_best_at_expandable_upper_bound_sets_flag(tmp_path,monkeypatch):
    body,_ = patch_for(tmp_path)
    config = ExperimentConfig.model_validate(body)
    y = np.tile([1,2],4)
    X = np.column_stack((y,np.arange(len(y)),np.zeros((len(y),7))))
    data = SimpleNamespace(X=X,y=y)
    folds = [(np.arange(4),np.arange(4,8)),(np.arange(4,8),np.arange(4))]
    class Estimator:
        def __init__(self,n_components,**_):
            self.components=n_components
        def fit(self,*_):
            return self
        def predict(self,X):
            success = (X[:,0]==2) if self.components>1 else np.zeros(len(X),bool)
            return np.column_stack((~success,success))
    from sklearn import cross_decomposition
    monkeypatch.setattr(cross_decomposition,'PLSRegression',Estimator)
    opts = {'components':[1,2],'preparations':[{'name':'原谱','steps':[]}]}
    assert study.evaluate(config,data,folds,opts,lambda **_:None)['component_upper_reached']
    opts['components'] = [1,2,3]
    assert not study.evaluate(config,data,folds,opts,lambda **_:None)['component_upper_reached']


@pytest.mark.parametrize('text,expected',[
    ('把实验方案改为 1120-1675nm',('1120','1675')),
    ('波段裁到 1120 至 1675 纳米',('1120','1675')),
    ('设为：1120.5–1675 nm',('1120.5','1675')),
    ('波段裁到 1120-1675',None),
    ('设为 1120-1675 nm，再改步长为 5 nm',None),
])
def test_wavelength_crop_requires_a_single_range_with_units(text,expected):
    from spectrumagent.experiments.wavelength_proposal import CROP
    match = CROP.fullmatch(text)
    assert (match.groups() if match else None)==expected


def test_paired_preview_through_image_study_and_formal_training(application,tmp_path,monkeypatch):
    base = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(base.database).create_session()['id']
    roots = {}
    for role, count in (('训练',4),('测试',2)):
        for kind in ('原图','标注'):
            roots[role+kind] = tmp_path/(role+kind)
            roots[role+kind].mkdir()
        for i in range(count):
            hdr = roots[role+'原图']/f'image{i}.hdr'
            axis = [1100,1104.18,1108.37,1112.55,1116.73,1120.92]
            if role=='测试':
                axis = [v+0.2 for v in axis]
            hdr.write_text('ENVI\nsamples=8\nlines=8\nbands=6\ninterleave=bip\ndata type=12\nbyte order=0\n'
                           'wavelength units=nm\nwavelength={'+','.join(map(str,axis))+'}\n')
            rng = np.random.default_rng(i+(10 if role=='测试' else 0))
            pixels = rng.integers(10,20,(8,8,6),dtype=np.uint16)
            pixels[:,:,i%2] += 100
            pixels.tofile(hdr.with_suffix('.img'))
            annotation = dict(imagePath=hdr.stem+'.png',imageWidth=8,imageHeight=8,shapes=[
                dict(shape_type='rectangle',label=('PE','EPS')[i%2],points=[[0,0],[8,8]])])
            if i:
                annotation['source_hdr'] = str(hdr)
            (roots[role+'标注']/(hdr.stem+'.json')).write_text(json.dumps(annotation),'utf8')
    def answer(text):
        event = chat(application,owner,text)[-1][1]
        return event.get('content') or event['question']
    from spectrumagent.experiments.pairing import TRAIN_COMMAND
    from spectrumagent.experiments.group_split import manifest_path
    msg = '配对预览；'+'；'.join(f'{k}：“{path}”' for k,path in roots.items())
    assert TRAIN_COMMAND in answer(msg)
    assert TRAIN_COMMAND in answer('帮我寻优')
    review_events = chat(application,owner,TRAIN_COMMAND)
    review = review_events[-1][1]['question']
    card = next(event['result_summary'] for kind,event in review_events if kind=='step')
    proposal = json.loads(card['wavelength_details'])
    assert '1105–1120 nm' in card['wavelength_label']
    assert proposal['overlap_start'] == pytest.approx(1100.2)
    assert proposal['step'] == proposal['window'] == proposal['tolerance'] == 5.
    assert proposal['bands'] == 4 and str(tmp_path) not in card['wavelength_details']
    assert '非严格等步长' in review and '共同目标' in review and 'image0.hdr' not in review
    record = base._read(owner)
    path = manifest_path(base.service.paths.exports,record['document']['split_id'])
    manifest = json.loads(path.read_text('utf8'))
    assert manifest['one_image_one_sample'] is False and all(r['img_sha256'] for r in manifest['rows'])
    assert not record['document']['train'].get('members')
    with monkeypatch.context() as m:
        m.setattr(study,'load_input',lambda *a,**kw: pytest.fail('preflight extracted spectra'))
        preview_events = chat(application,owner,'帮我寻优')
        preview_card = next(data['result_summary'] for kind,data in preview_events
                            if kind=='step' and data['tool']=='experiments.study_preview')
        assert preview_card['study_confirm']=='确认探索性寻优'
        assert '2 折' in preview_card['study_overview'] and 'EPS' in preview_card['study_fold_note']
        assert preview_card['study_sampling']=='采样步长 3 像元 · 每类上限 不限'
        for command,wording in (('整寻优，步长1，每类上限1200','在训练方案中修改'),
                                ('改寻优，折数 2','未重发寻优方案'),
                                ('调整寻优，未识别参数 9','未重发寻优方案')):
            feedback = chat(application,owner,command)
            assert wording in feedback[-1][1]['question']
            assert [p['tool'] for kind,p in feedback if kind=='step']==['experiments.study_preview_retained']
        revised = chat(application,owner,'整寻优，潜变量 1-2')
        revised_card = next(data['result_summary'] for kind,data in revised if kind=='step')
        assert revised_card['study_sampling']==preview_card['study_sampling']
        assert '潜变量 1 至 2' in revised[-1][1]['question']
        failure = answer('寻优，折数 3')
        assert '改为 2' in failure and 'EPS 2 组' in failure and '非严格等步长' in failure
        assert base.confirmation(owner)[2]==revised_card['study_preview_id']
        assert revised_card['study_preview_id']!=preview_card['study_preview_id']
        ready = answer('寻优，折数 2')
        assert '确认探索性寻优' in ready and '按原图分组' in ready
        assert '请单独回复' in answer('确认寻优')
    revision = record['revision']
    with monkeypatch.context() as m:
        m.setattr(inputs,'sha256',lambda *args,**kwargs: pytest.fail('cached review rehashed a source'))
        adopted = chat(application,owner,f'采用波长建议 {revision}')
    assert any(kind=='step' for kind,_ in adopted), adopted
    summary = next(event['result_summary'] for kind,event in adopted if kind=='step')
    assert summary['draft_ready'] is True and summary['study_folds'] == 2
    assert summary['study_label'] == '2 折 · 按原图分组 · 含 SG1/SG2'
    record = base._read(owner)
    assert record['document']['axis'] == dict(kind='grid', start_nm=1105.,stop_nm=1120.,step_nm=5.)
    assert '已过期' in answer(f'采用波长建议 {revision}')
    assert '确认探索性寻优' in answer(f"训练集内自动寻优 {record['revision']} 折数 2")
    assert base.study.latest(owner) is None
    assert '确认执行' in answer('把实验方案改为 1105–1115 nm')
    record = base._read(owner)
    assert base._config(record).wavelengths_nm == [1105.,1110.,1115.]
    from backend.database import connect_database
    cropped_owner = AgentStore(base.database).create_session()['id']
    with connect_database(base.database) as db:
        db.execute('INSERT INTO experiment_pairing(session_id,report_json) '
                   'SELECT ?,report_json FROM experiment_pairing WHERE session_id=?', (cropped_owner,owner))
    chat(application,cropped_owner,TRAIN_COMMAND)
    rejected_crop = chat(application,cropped_owner,'改为 1099–1115 nm')
    assert '共同范围' in rejected_crop[-1][1]['question']
    crop = chat(application,cropped_owner,'改为 1105–1115 nm')
    assert '确认执行' in crop[-1][1]['question']
    assert base._config(base._read(cropped_owner)).wavelengths_nm == [1105.,1110.,1115.]
    extraction = dict(kind='roi_images',mapping_window_nm=5.,nearest_tolerance_nm=3.)
    grid_update = dict(expected_revision=record['revision'],axis=dict(kind='grid',start_nm=1101.,stop_nm=1117.,step_nm=4.),
                       train=extraction, test={**extraction, 'wavelength_unit':'nm'})
    conflicting_update = {**grid_update, 'test':{**grid_update['test'], 'nearest_tolerance_nm':2.}}
    with pytest.raises(DataError) as conflict:
        base.update(owner,DraftUpdate.model_validate(conflicting_update))
    assert conflict.value.code == 'SPLIT_EXTRACTION_CONFLICT'
    assert base._read(owner)['revision'] == record['revision']
    model = ScriptedModel(tool('experiments.draft_update', grid_update))
    with monkeypatch.context() as m:
        m.setattr(inputs,'sha256',lambda *args,**kwargs: pytest.fail('review rehashed a source'))
        edited = list(machine_for(application,owner,model).message(content='把目标波长改为 1101 到 1117 nm，间隔 4 nm，映射窗口 5 nm，最近容差 3 nm'))
        assert '确认执行' in edited[-1][1]['question'] and model.requests
    config = base._config(base._read(owner))
    assert config.train.mapping_window_nm == config.test.mapping_window_nm == 5.
    assert config.train.wavelength_unit == config.test.wavelength_unit == 'nm'
    edited_sampling = base.update(owner,DraftUpdate(expected_revision=base._read(owner)['revision'],
                                                    train={'kind':'roi_images','sampling_stride':1,'max_per_class':1200}))
    changes = base.draft_presentation(owner,edited_sampling)['draft_changes']
    assert '训练采样步长 · 3 → 1' in changes and '每类上限 · 不限 → 1200' in changes
    limited = chat(application,owner,'寻优，折数 2，SG窗口：3；潜变量 1-1')
    limited_card = next(data['result_summary'] for kind,data in limited if kind=='step')
    assert limited_card['study_sampling']=='采样步长 1 像元 · 每类上限 1200 · 抽样种子 42'
    proposal = limited[-1][1]['question']
    assert 'SG1' in proposal and 'SG2' in proposal and '确认探索性寻优' in proposal
    answer('确认探索性寻优')
    sid = base.study.latest(owner)['study_id']
    assert until(base.study,owner,sid)['status']=='succeeded'
    assert base.study.result(owner,sid)['grouping']=='image'
    with np.load(base.study.folder(sid)/'training_cache.npz') as cache:
        for group in np.unique(cache['groups']):
            assert len(set(cache['fold_assignment'][cache['groups']==group]))==1
    hashes = []
    def track_hash(file, check=None):
        hashes.append(str(file))
        return real_hash(file, check)
    real_hash = inputs.sha256
    with monkeypatch.context() as m:
        m.setattr(inputs,'sha256',track_hash)
        assert '确认执行' in answer('采用推荐方案新建正式训练')
    assert sorted(hashes) == sorted(row[key] for row in manifest['rows'] if row['split']=='训练'
                                   for key in ('hdr','img','annotation'))
    answer('确认执行')
    task = wait_task(base.tasks,owner,base.tasks.latest(owner))
    assert task['status']=='succeeded', task
    result = base.service.get(task['experiment_id'])
    assert result['split_checks']['physical_sample_independence']=='unknown'
    assert (base.service.folder(task['experiment_id'])/'split_plan.json').read_bytes()==path.read_bytes()
    button = chat(application,owner,'基于此数据寻优 '+task['experiment_id'])
    card = next(data['result_summary'] for kind,data in button if kind=='step' and data['tool']=='experiments.study_preview')
    assert '2 折' in card['study_overview'] and card['study_confirm']=='确认探索性寻优'
    # Keep size and mtime fixed: only the execution-time byte hash catches this.
    img = Path(manifest['rows'][0]['img'])
    original = img.stat()
    with img.open('r+b') as stream:
        byte = stream.read(1)
        stream.seek(0)
        stream.write(bytes([byte[0] ^ 1]))
    os.utime(img, ns=(original.st_atime_ns, original.st_mtime_ns))
    sources, _ = base.review_sources(config)
    with pytest.raises(DataError) as changed:
        base.service.run(config, expected_sources=sources)
    assert changed.value.code == 'EXPERIMENT_INPUT_CHANGED'
    assert 'IMG 内容与配对清单不一致' in changed.value.payload.detail
