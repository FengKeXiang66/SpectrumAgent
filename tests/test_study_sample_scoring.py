"""Small three-fold oracles before a real, training-only conversation round trip."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.metrics import f1_score

from test_sample_evaluation import application, workspace, roi_config
from test_experiment_conversation import machine_for, ScriptedModel
from test_experiment_study import until, grouped_draft
from spectrumagent.agent.state import AgentStore
from spectrumagent.data import DataError
from spectrumagent.experiments import study
from spectrumagent.experiments.inputs import Samples
from spectrumagent.experiments.schema import ExperimentConfig, SampleDefinition
from spectrumagent.experiments.study_metrics import SampleScorer, physical_ids
from spectrumagent.experiments.service import write_json, sha256


def synthetic(tmp_path, minimum=1):
    config=roi_config(tmp_path)
    # Each fold has three objects per class, very unequal object sizes.
    # Candidate 1 classifies large objects; candidate 2 classifies more objects.
    members=[];truth=[];features=[];origins=[];fold_of=[]
    for fold in range(3):
        for label in (1,2):
            for obj,count in enumerate((20,2,2)):
                source=str(tmp_path/f'{fold}-{label}-{obj}.hdr')
                members.append(config.train.members[0].model_copy(update={'header_path':source,'sample_id':f'obj-{fold}-{label}-{obj}'}))
                for i in range(count):
                    truth.append(label);fold_of.append(fold);origins.append({'source':source,'sample_id':source})
                    features.append([label,obj,fold,i,i*i,fold*obj,label*obj,i*label,1.])
    config.train=config.train.model_copy(update={'members':members})
    config.sample_evaluation=SampleDefinition(mode='IMAGE',minimum_valid=minimum)
    data=Samples(np.asarray(features,dtype=float),np.asarray(truth),origins,{},'center_pixel')
    assignment=np.asarray(fold_of)
    folds=[(np.flatnonzero(assignment!=i),np.flatnonzero(assignment==i)) for i in range(3)]
    opts=dict(evaluation_target='sample',folds=3,seed=42,grouping='auto',components=[1,2],preparations=[dict(name='原谱',steps=[])])
    return config,data,folds,opts


class RuleEstimator:
    def __init__(self,n_components,**_):self.lv=n_components
    def fit(self,*_):return self
    def predict(self,X):
        correct=(X[:,1]==0) if self.lv==1 else (X[:,1]!=0)
        pred=np.where(correct,X[:,0],3-X[:,0]).astype(int)
        return np.column_stack((pred==1,pred==2)).astype(float)


def test_same_candidates_dual_ranks_and_pooled_oof_match_hand_calculation(tmp_path,monkeypatch):
    from sklearn import cross_decomposition
    config,data,folds,opts=synthetic(tmp_path)
    monkeypatch.setattr(cross_decomposition,'PLSRegression',RuleEstimator)
    result=study.evaluate(config,data,folds,opts,lambda **_:None,groups=physical_ids(config,data.origins))
    one,two=({row['id']:row for row in result['candidates']}[i] for i in (1,2))
    assert result['best']==result['recommended']==2 and result['one_se_threshold'] is None
    assert result['evaluation_target']=='sample' and result['scoring']=='pooled_oof_sample_macro_f1'
    assert one['pixel_rank']==1 and one['sample_rank']==2 and one['rank_change']==-1
    assert two['pixel_rank']==2 and two['sample_rank']==1
    assert one['pixel_oof_f1']==pytest.approx(20/24)
    assert two['pixel_oof_f1']==pytest.approx(4/24)
    assert one['cv_f1']==pytest.approx(1/3) and two['cv_f1']==pytest.approx(2/3)
    assert two['sample_oof']['metrics']['n']==18 and two['sample_oof']['metrics']['correct']==12
    assert two['sample_oof']['metrics']['evaluation_unit']=='sample'
    assert two['sample_oof']['metrics']['purpose']=='training_oof_validation'
    assert all(fold['included']==6 for fold in two['sample_folds'])
    assert 'cv_f1_sd' not in two and two['fold_f1_sd']==0
    # Both rankings must use exactly these folds and the same candidate predictions.
    pixel=study.evaluate(config,data,folds,{**opts,'evaluation_target':'pixel'},lambda **_:None)
    assert pixel['best']==1
    assert pixel['candidates'][0]['cv_f1']==one['pixel_fold_f1']


def test_pooled_oof_is_not_mean_of_fold_sample_scores(tmp_path,monkeypatch):
    from sklearn import cross_decomposition
    config,data,folds,opts=synthetic(tmp_path)
    class Unequal(RuleEstimator):
        def predict(self,X):
            pred=X[:,0].astype(int).copy()
            pred[(X[:,2]==0)&(X[:,0]==2)]=1
            pred[(X[:,2]==1)&(X[:,0]==1)&(X[:,1]==2)]=2
            return np.column_stack((pred==1,pred==2)).astype(float)
    monkeypatch.setattr(cross_decomposition,'PLSRegression',Unequal)
    result=study.evaluate(config,data,folds,{**opts,'components':[1]},lambda **_:None,groups=physical_ids(config,data.origins))
    row=result['candidates'][0]
    included=row['sample_oof']['rows']
    expected=f1_score([r['truth'] for r in included],[r['prediction'] for r in included],labels=[1,2],average='macro')
    assert row['cv_f1']==pytest.approx(expected)
    assert row['cv_f1']!=pytest.approx(row['fold_f1_mean'])


def test_missing_class_after_ties_invalidates_candidate_without_pixel_fallback(tmp_path,monkeypatch):
    from sklearn import cross_decomposition
    config,data,folds,opts=synthetic(tmp_path)
    class Ties(RuleEstimator):
        def predict(self,X):
            pred=X[:,0].astype(int).copy()
            # All class-2 objects in the first validation fold tie exactly.
            mask=(X[:,2]==0)&(X[:,0]==2)
            pred[mask]=1+(X[mask,3].astype(int)%2)
            return np.column_stack((pred==1,pred==2)).astype(float)
    monkeypatch.setattr(cross_decomposition,'PLSRegression',Ties)
    result=study.evaluate(config,data,folds,{**opts,'components':[1]},lambda **_:None,groups=physical_ids(config,data.origins))
    row=result['candidates'][0]
    assert result['best'] is None and result['recommended'] is None
    assert row['error_code']=='sample_metric_undefined' and 'cv_f1' not in row
    assert row['pixel_rank']==1 and row['pixel_oof_f1']>0  # auxiliary only, cannot adopt
    assert row['sample_folds'][0]['missing_classes']==[2]
    assert row['sample_folds'][0]['exclusion_counts']['tie']==3
    assert row['sample_oof']['included']==15


def test_fold_count_support_and_group_identity_are_strict(tmp_path):
    config,data,folds,opts=synthetic(tmp_path)
    opts['folds']=10
    with pytest.raises(ValueError,match='不会自动降折'):study.make_folds(data,'image',opts,config)
    config.sample_evaluation=SampleDefinition(mode='IMAGE',minimum_valid=100)
    with pytest.raises(ValueError,match='观测不足'):study.make_folds(data,'image',{**opts,'folds':3},config)
    config.sample_evaluation=SampleDefinition(mode='IMAGE',minimum_valid=1)
    with pytest.raises(ValueError,match='不一致'):
        study.evaluate(config,data,folds,{**opts,'evaluation_target':'sample'},lambda **_:None,groups=np.array(['wrong']*len(data.y)))


def test_mapped_views_are_one_object_in_folds_scoring_and_saved_votes(tmp_path,monkeypatch):
    from sklearn import cross_decomposition
    config,data,folds,opts=synthetic(tmp_path)
    members=[]
    for member in config.train.members:
        members.extend([member,member.model_copy(update={'header_path':member.header_path+'.other.hdr'})])
    config.train=config.train.model_copy(update={'members':members})
    for origin,x in zip(data.origins,data.X):
        if int(x[3])%2:origin['source']+='.other.hdr'
    config.sample_evaluation=SampleDefinition(mode='MAPPED',minimum_valid=1)
    monkeypatch.setattr(cross_decomposition,'PLSRegression',RuleEstimator)
    groups,generated,_,_=study.make_folds(data,'sample',opts,config)
    assert len(set(groups))==18
    assert all(not set(groups[t])&set(groups[v]) for t,v in generated)
    result=study.evaluate(config,data,folds,opts,lambda **_:None,groups=groups)
    assert result['best']==2
    rows=result['candidates'][0]['sample_oof']['rows']
    assert len(rows)==18 and all(row['image_count']==2 for row in rows)


def test_mixed_npz_and_batch_cannot_be_object_ranking(application,tmp_path):
    base,owner,*_=grouped_draft(application,tmp_path)
    with pytest.raises(ValueError,match='NPZ'):base.study.prepare(owner,'prepare','寻优，按实物评分')
    config=roi_config(tmp_path)
    config.sample_evaluation=SampleDefinition(mode='MIXED')
    with pytest.raises(ValueError,match='MIXED'):study.group_kind(config,{'evaluation_target':'sample','grouping':'auto'})
    config.sample_evaluation=SampleDefinition(mode='IMAGE')
    with pytest.raises(ValueError,match='批次'):study.group_kind(config,{'evaluation_target':'sample','grouping':'batch'})


def test_threshold_adjustment_creates_new_review_and_no_silent_fold_reduction(application,tmp_path):
    base,owner,record=image_draft(application,tmp_path)
    text=f'基于此数据寻优 {record["experiment_id"]}，按实物评分，一图一物，折数 3，潜变量 1-1；预处理候选：原谱；归一化候选：无'
    _,card=base.study.prepare(owner,'first',text,structured=True)
    _,updated=base.study.prepare(owner,'second','调整寻优，有效观测阈值 120',structured=True)
    assert updated['study_preview_id']!=card['study_preview_id']
    with pytest.raises(ValueError,match='分组不足'):base.study.prepare(owner,'third','调整寻优，折数 4')
    assert base.confirmation(owner)[2]==updated['study_preview_id']


def image_draft(app,tmp_path):
    config=roi_config(tmp_path)
    # Three independent training images per class, full explicit single-object masks.
    original=config.train.members
    members=[]
    rng=np.random.default_rng(91)
    for m in original:
        for repeat in range(3):
            path=tmp_path/f'object-{m.sample_id}-{repeat}.hdr'
            path.write_bytes(Path(m.header_path).read_bytes())
            raw=np.fromfile(Path(m.header_path).with_suffix('.img'),dtype=np.uint16)
            (raw+rng.integers(0,30,len(raw),dtype=np.uint16)).tofile(path.with_suffix('.img'))
            members.append(m.model_copy(update={'header_path':str(path),'sample_id':f'{m.sample_id}-{repeat}'}))
    config.train=config.train.model_copy(update={'members':members})
    record=app.state.experiments.run(config)
    base=app.state.agent_tools.experiment_dialogue
    owner=AgentStore(base.database).create_session()['id']
    return base,owner,record


@pytest.mark.parametrize('declaration,mode',[('一图一物','IMAGE'),('多图一物，复用已确认sample_id完整表','MAPPED')])
def test_three_fold_conversation_adopt_report_inherit_restart_and_no_holdout(application,tmp_path,monkeypatch,declaration,mode):
    base,owner,record=image_draft(application,tmp_path)
    manager=base.study
    actual=np.load
    holdouts={str(m['roi_path']) for m in record['config']['test']['members']}  # selected ROIs, never opened in Study
    def load(path,*args,**kw):
        if str(path) in holdouts:raise AssertionError('holdout was opened during Study')
        return actual(path,*args,**kw)
    monkeypatch.setattr(np,'load',load)
    events=list(machine_for(application,owner,ScriptedModel()).message(content=f'基于此数据寻优 {record["experiment_id"]}，按实物评分，{declaration}，折数 3，潜变量 1-2；预处理候选：原谱；归一化候选：无'))
    assert 'pooled OOF' in events[-1][1]['question'],events
    assert '有效观测阈值 N=100' in events[-1][1]['question']
    identifier=base.confirmation(owner)[2]
    assert manager.latest(owner) is None  # review does not start training
    list(machine_for(application,owner,ScriptedModel()).message(content='确认寻优'))
    state=until(manager,owner,identifier)
    assert state['status']=='succeeded',state
    result=manager.result(owner,identifier)
    assert result['evaluation_target']=='sample' and result['group_count']==6
    assert result['best'] is not None and len(result['candidates'])==2
    folder=manager.folder(identifier)
    with actual(folder/'training_cache.npz') as cache:
        for group in np.unique(cache['groups']):assert len(np.unique(cache['fold_assignment'][cache['groups']==group]))==1
    manager.adopt(owner,identifier,result['best'])
    monkeypatch.setattr(np,'load',actual)
    adopted=base._config(base._read(owner))
    assert adopted.sample_evaluation.mode==mode
    assert adopted.study_selection.evaluation_target=='sample' and adopted.study_selection.grouping==('image' if mode=='IMAGE' else 'sample')
    trained=base.service.run(adopted)
    view=base.service.sample_evaluations.view(trained['experiment_id'])
    assert view['definition']['mode']==mode and view['selection_warning'] is None
    # Source declarations inherited later do not require reading test predictions.
    before={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    assert study.StudyService(base).result(owner,identifier)==result
    assert {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}==before


def test_legacy_result_gets_pixel_projection_without_rewriting_archive(application,tmp_path):
    base=application.state.agent_tools.experiment_dialogue
    owner=AgentStore(base.database).create_session()['id'];identifier=str(uuid4());folder=base.study.folder(identifier)
    from spectrumagent.storage import guard
    guard.mkdir(folder,parents=True)
    original=dict(study_id=identifier,candidates=[],best=1,recommended=1,one_se_threshold=.9)
    write_json(folder/'result.json',original)
    write_json(folder/'status.json',dict(session_id=owner,status='succeeded',result_sha256=sha256(folder/'result.json')))
    content=(folder/'result.json').read_bytes()
    projected=base.study.result(owner,identifier)
    assert projected['evaluation_target']=='pixel' and projected['scoring']=='fold_mean_macro_f1'
    assert (folder/'result.json').read_bytes()==content


def test_invalid_physical_config_has_clear_http_error_before_training(application,tmp_path,monkeypatch):
    from spectrumagent.experiments.service import ExperimentModel
    config=roi_config(tmp_path)
    config.sample_evaluation=SampleDefinition(mode='MAPPED',mapping=[])
    config.train.members[0].sample_id=config.train.members[0].header_path
    def forbidden(*args):raise AssertionError('invalid physical config reached fitting')
    monkeypatch.setattr(ExperimentModel,'fit',forbidden)
    client=TestClient(application,headers={'Authorization':'Bearer '+application.state.testing_identity.token})
    response=client.post('/api/v1/experiments/run',json=config.model_dump(mode='json'))
    assert response.status_code==400,response.text
    assert response.json()['error']=='EXPERIMENT_EVALUATION_INVALID'
