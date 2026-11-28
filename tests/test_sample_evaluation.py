"""Explicit physical semantics, strict truth, report-only replay and dialogue."""
from io import BytesIO
import json
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from test_experiment_conversation import application, workspace, machine_for, ScriptedModel, tool
from test_experiments import config_for
from spectrumagent.agent.state import AgentStore
from spectrumagent.agent.sample_evaluation import PREFIX
from spectrumagent.data import DataError
from spectrumagent.experiments.schema import ExperimentConfig
from spectrumagent.experiments.service import ExperimentModel
from spectrumagent.experiments.results import ExperimentResults
from spectrumagent.experiments.sample_evaluation import aggregate, origin_rows, source_ref, SampleEvaluations, report_html


def part(role, source, truth, predictions):
    return role, np.asarray(truth), np.asarray(predictions), [{'source':source} for _ in truth]


def definition(mode='IMAGE', minimum=100, mapping=None):
    return dict(mode=mode, minimum_valid=minimum, mapping=mapping or [])


def test_pool_views_before_vote_not_vote_of_image_votes(tmp_path):
    sources=[str(tmp_path/f'view{i}.hdr') for i in range(3)]
    # Two small wrong views must not outvote the much larger correct view.
    parts=[part('test',sources[0],[1]*200,[1]*200),
           part('test',sources[1],[1]*60,[2]*60),part('test',sources[2],[1]*60,[2]*60)]
    mapping=[dict(source_ref=source_ref(s),sample_id='egg-1') for s in sources]
    result=aggregate(parts,{1:'A',2:'B'},definition('MAPPED',mapping=mapping))
    score=result['roles']['test']; row=score['rows'][0]
    assert result['total_objects']==1 and score['included']==1
    assert row['image_count']==3 and row['valid']==320 and row['prediction']==1
    assert row['votes']=={1:200,2:120} and score['metrics']['accuracy']==1


def test_conflicting_truth_tie_insufficient_and_boundary_are_explicit(tmp_path):
    rows=[part('test',str(tmp_path/'conflict.hdr'),[1]*200+[2]*100,[1]*300),
          part('test',str(tmp_path/'tie.hdr'),[1]*100,[1]*50+[2]*50),
          part('test',str(tmp_path/'small.hdr'),[2]*99,[2]*99),
          part('test',str(tmp_path/'exact.hdr'),[2]*100,[2]*100)]
    result=aggregate(rows,{1:'A',2:'B'},definition())['roles']['test']
    lookup={r['display_id']:r for r in result['rows']}
    assert result['included']==1 and result['excluded']==3
    assert result['exclusion_counts']==dict(truth_conflict=1,tie=1,insufficient=1)
    assert lookup['conflict.hdr']['truth'] is None  # never vote truth
    assert lookup['tie.hdr']['prediction'] is None  # never choose smallest label
    assert lookup['small.hdr']['correct'] is None
    assert result['metrics']['n']==1 and result['metrics']['macro_f1']==1


def test_multiview_truth_conflict_split_overlap_and_zero_observations(tmp_path):
    a,b,c=[str(tmp_path/f'{x}.hdr') for x in 'abc']
    mapping=[dict(source_ref=source_ref(s),sample_id='object') for s in (a,b,c)]
    parts=[part('train',a,[1]*100,[1]*100),part('train',b,[2]*100,[2]*100),part('test',c,[1]*100,[1]*100)]
    result=aggregate(parts,{1:'A',2:'B'},definition('MAPPED',mapping=mapping))
    assert result['total_objects']==1
    assert result['roles']['train']['rows'][0]['reasons']==['truth_conflict','split_overlap','tie']
    assert result['roles']['test']['included']==0
    empty=str(tmp_path/'empty.hdr')
    result=aggregate([],{1:'A',2:'B'},definition(),{'train':[empty],'test':[]})
    assert result['roles']['train']['total']==1
    assert result['roles']['train']['rows'][0]['reasons']==['truth_unavailable','insufficient']
    cross=aggregate([part('train',a,[1]*100,[1]*100),part('test',b,[2]*100,[2]*100)],
        {1:'A',2:'B'},definition('MAPPED',mapping=mapping))
    assert 'truth_conflict' in cross['roles']['test']['rows'][0]['reasons']
    assert cross['roles']['test']['rows'][0]['truth'] is None


def test_mixed_not_applicable_and_bad_origin_alignment_rejected(tmp_path):
    mixed=aggregate([],{1:'A'},definition('MIXED'))
    assert mixed['status']=='not_applicable' and mixed['total_objects'] is None and not mixed['roles']
    with pytest.raises(ValueError): aggregate([('test',np.array([1]),np.array([1]),[])],{1:'A'},definition())
    with pytest.raises(ValueError):
        aggregate([part('test',str(tmp_path/'a.hdr'),[1],[1])],{1:'A'},definition(),{'test':[str(tmp_path/'b.hdr')]})


@pytest.mark.parametrize('wrapped',[False,True])
def test_origin_stream_handles_large_arrays_without_materializing_all_origins(tmp_path,wrapped):
    rows=[dict(source='x'*120,row=i,col=0) for i in range(2500)]
    body=dict(sampling={'eligible':3000},origins=rows) if wrapped else rows
    path=tmp_path/'origins.json';path.write_text(json.dumps(body),encoding='utf-8')
    assert list(origin_rows(path))==rows
    path.write_text(json.dumps(body)+' garbage',encoding='utf-8')
    with pytest.raises(ValueError):list(origin_rows(path))


def roi_config(tmp_path):
    body=config_for(tmp_path);rng=np.random.default_rng(48)
    for role in ('train','test'):
        members=[]
        for label in (1,2):
            header=tmp_path/f'{role}-{label}.hdr'
            profile=np.arange(9)*500 if label==1 else np.arange(9)[::-1]*500
            raw=(4000+profile+rng.integers(0,200,(12,12,9))).astype(np.uint16)
            header.with_suffix('.img').write_bytes(raw.tobytes())
            header.write_text('ENVI\nlines=12\nsamples=12\nbands=9\ndata type=12\ninterleave=bip\nbyte order=0\n'
                'reflectance scale factor=10000\nwavelength units=nm\nwavelength={'+','.join(map(str,body['wavelengths_nm']))+'}\n',encoding='utf-8')
            roi=header.with_suffix('.npz')
            np.savez(roi,region_map=np.ones((12,12),np.int32),label_map=np.full((12,12),label,np.int32))
            # These identifiers alone do not constitute an IMAGE declaration.
            members.append(dict(header_path=str(header),roi_path=str(roi),sample_id=role+str(label)))
        body[role]=dict(kind='roi_images',members=members,neighborhood=1,wavelength_unit='nm',
            mapping_window_nm=5.,nearest_tolerance_nm=5.,quality=dict(min_mean=.02,min_std=.002,max_zero_fraction=.05,saturation=65535.))
    return ExperimentConfig.model_validate(body)


def test_report_is_verified_persisted_exported_and_does_not_retrain(application,tmp_path,monkeypatch):
    dialogue=application.state.agent_tools.experiment_dialogue
    result=dialogue.service.run(roi_config(tmp_path));identifier=result['experiment_id']
    service=dialogue.service.sample_evaluations
    folder=dialogue.service.folder(identifier)
    original={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    def forbidden(*args):raise AssertionError('report generation must not fit')
    monkeypatch.setattr(ExperimentModel,'fit',forbidden)
    before=service.view(identifier)
    assert before['revision']==0 and before['definition'] is None and before['report'] is None
    assert str(tmp_path) not in json.dumps(before)
    view=service.update(identifier,0,'IMAGE',100,form_id='form')
    assert view['revision']==1 and view['report']['total_objects']==4
    for role in ('train','test'):
        assert view['report']['roles'][role]['included']==2
        assert view['report']['roles'][role]['metrics']['n']==2
        assert view['report']['pixel_metrics'][role]['n']==288
    assert SampleEvaluations(dialogue.service).view(identifier)==view
    with pytest.raises(DataError) as caught: service.update(identifier,0,'MIXED')
    assert caught.value.code=='SAMPLE_EVALUATION_CONFLICT'
    reader=ExperimentResults(dialogue)
    summary=reader.summary('owner',experiment_id=identifier)
    assert summary['metrics']==result['metrics'] and summary['sample_evaluation']==view
    html=reader.export('owner',None,'report',experiment_id=identifier).decode()
    assert '实物数 n=4' in html and 'n=288' in html and '有效观测阈值 N=100' in html
    assert '未计入实物指标的完整列表' in html
    bundle=reader.export('owner',None,'bundle',experiment_id=identifier)
    with ZipFile(BytesIO(bundle)) as archive:
        assert json.loads(archive.read('sample_evaluation.json'))==view
    assert {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}==original
    unsafe=[dict(source_ref=s['source_ref'],sample_id='<script>alert(1)</script>'+str(i)) for i,s in enumerate(view['sources'])]
    escaped=report_html(service.update(identifier,1,'MAPPED',mapping=unsafe),result['config']['classes'])
    assert '<script>' not in escaped and '&lt;script&gt;' in escaped
    (folder/'test_origins.json').write_text('[]',encoding='utf-8')
    with pytest.raises(DataError) as caught:service.view(identifier)
    assert caught.value.code=='EXPERIMENT_ARTIFACT_CHANGED'


def test_full_csv_mapping_conflicts_and_no_npz_group_guessing(application,tmp_path):
    dialogue=application.state.agent_tools.experiment_dialogue;service=dialogue.service.sample_evaluations
    config=roi_config(tmp_path);result=dialogue.service.run(config);identifier=result['experiment_id']
    csv=tmp_path/'groups.csv'
    csv.write_text('source,sample_id\n'+'\n'.join(f'{m.header_path},{role}-egg' for role in ('train','test') for m in getattr(config,role).members),encoding='utf-8-sig')
    mapping=service.csv_mapping(identifier,str(csv))
    view=service.update(identifier,0,'MAPPED',mapping=mapping)
    assert view['report']['total_objects']==2
    assert 'truth_conflict' in view['report']['roles']['test']['rows'][0]['reasons']
    with pytest.raises(ValueError):service.update(identifier,1,'MAPPED',mapping=mapping[:-1])
    csv.write_text('source,batch\nfoo,one',encoding='utf-8')
    with pytest.raises(ValueError,match='batch'):service.csv_mapping(identifier,str(csv))
    mixed=service.update(identifier,1,'MIXED')
    assert mixed['report']['status']=='not_applicable' and mixed['report']['roles']=={}
    assert '不存在唯一整图类别' in report_html(mixed,config.classes)
    npz=dialogue.service.run(ExperimentConfig.model_validate(config_for(tmp_path)))
    assert not service.view(npz['experiment_id'])['applicable']
    with pytest.raises(DataError) as caught:service.update(npz['experiment_id'],0,'IMAGE')
    assert caught.value.code=='SAMPLE_EVALUATION_UNAVAILABLE'


def test_form_works_offline_and_native_tools_open_same_persisted_report(application,tmp_path):
    dialogue=application.state.agent_tools.experiment_dialogue
    record=dialogue.service.run(roi_config(tmp_path));identifier=record['experiment_id']
    store=AgentStore(dialogue.database);sid=store.create_session()['id']
    def offline(*args):
        class Model:
            def chat(self,*args):raise AssertionError('local report form must not use model service')
        return Model()
    application.state.agent_llm_factory=offline
    payload=dict(experiment_id=identifier,expected_revision=0,mode='IMAGE',minimum_valid=100,mapping=[],form_id=str(uuid4()))
    client=TestClient(application,headers={'Authorization':'Bearer '+application.state.testing_identity.token})
    def submit(body):
        response=client.post(f'/api/v1/agent/sessions/{sid}/messages',json=dict(content=PREFIX+json.dumps(body),request_id=str(uuid4())))
        assert response.status_code==200,response.text
        return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    events=submit(payload)
    assert events[-1]['reply_status']=='replied',events
    assert dialogue.service.sample_evaluations.view(identifier)['form_id']==payload['form_id']
    assert submit({**payload,'form_id':str(uuid4())})[-1]['reply_status']=='needs_input'
    assert dialogue.service.sample_evaluations.view(identifier)['revision']==1
    model=ScriptedModel(tool('experiments.sample_evaluation_get',dict(experiment_id=identifier)))
    machine=machine_for(application,sid,model)
    events=list(machine.message(content='查看实验 '+identifier+' 的实物级报告'))
    assert any(kind=='step' and body.get('result_summary',{}).get('archived_experiment_id')==identifier for kind,body in events),events
    assert '未通过质量筛选' not in str(events)  # full rows stay local, scalar tool summaries only
    assert str(tmp_path) not in str(events)
    model=ScriptedModel(tool('experiments.sample_evaluation_update',dict(experiment_id=identifier,
        expected_revision=1,mode='MIXED',minimum_valid=100)))
    events=list(machine_for(application,sid,model).message(content='将实验 '+identifier+' 的实物评价声明为一图多物'))
    assert events[-1][0]=='done',events
    assert dialogue.service.sample_evaluations.view(identifier)['report']['status']=='not_applicable'


def test_history_without_origins_is_unavailable_instead_of_inventing_objects(application,tmp_path,monkeypatch):
    service=application.state.agent_tools.experiment_dialogue.service
    record=service.run(roi_config(tmp_path))
    old=service.get
    def missing(identifier):
        result=old(identifier)
        result['artifacts']={name:item for name,item in result['artifacts'].items() if name!='test_origins.json'}
        return result
    monkeypatch.setattr(service,'get',missing)
    view=service.sample_evaluations.view(record['experiment_id'])
    assert not view['applicable'] and '历史记录缺少' in view['unavailable_reason'] and view['report'] is None
    with pytest.raises(DataError) as caught:service.sample_evaluations.update(record['experiment_id'],0,'IMAGE')
    assert caught.value.code=='SAMPLE_EVALUATION_UNAVAILABLE'
