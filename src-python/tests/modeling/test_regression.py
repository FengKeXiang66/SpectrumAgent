import json
import sqlite3
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.data import DataError
from spectrumagent.modeling.cv import kennard_stone, plan_folds
from spectrumagent.modeling.dataset import build_sample_training_set
from spectrumagent.modeling.metrics import _regression, _gap, REGRESSION_METRICS
from spectrumagent.modeling.run import TrainingRuns


def seed(c):
    result = c.targets.import_csv(c.project, c.csv_text)
    assert not result['unmatched'] and not result['pending_confirmation']
    return c


def test_csv_68_unique_targets_conflicts_unmatched_and_annotation(regression_factory):
    c = regression_factory(68)
    result = c.targets.import_csv(c.project,c.csv_text)
    assert result['imported'] == len(c.targets.list(c.project)) == 68
    assert len(c.targets.import_csv(c.project,c.csv_text)['pending_confirmation']) == 68
    assert c.targets.import_csv(c.project,c.csv_text,overwrite=True)['imported'] == 68
    duplicate = '\n'.join(c.csv_text.splitlines()[:2]+[c.csv_text.splitlines()[1]])+'\n'
    assert len(c.targets.import_csv(c.project,duplicate)['pending_confirmation']) == 2
    bad = 'cube_name,schema,value\nmissing,含量,3\n'
    assert c.targets.import_csv(c.project,bad)['unmatched']
    item = c.targets.put(c.cubes[0],c.schema,1.25)
    assert item['value'] == 1.25 and item['source'] == 'annotation'
    with connect_database(c.paths.database) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO sample_target SELECT ?,project_id,cube_id,schema_id,value,source,created_at FROM sample_target LIMIT 1',(str(uuid4()),))


def test_sample_mean_bg_version_binding_snapshot_index_and_missing_y(regression_factory,monkeypatch):
    c = seed(regression_factory())
    result = build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    expected = c.values[0][c.maps[0] == 1].mean(axis=0)
    np.testing.assert_allclose(result['X_raw'][0],expected,atol=1e-15)
    assert not np.array_equal(expected,c.values[0][c.maps[0]>=0].mean(axis=0))
    assert result['meta']['n_pixels_used'] == 48
    # A historical snapshot with a different class index order must control BG.
    folder = c.paths.snapshots/c.cubes[0]/'v1'
    swapped = np.where(c.maps[0] == 0,1,np.where(c.maps[0] == 1,0,-1)).astype(np.int32)
    np.savez_compressed(folder/'label_map.npz',label_map=swapped)
    (folder/'label_index.json').write_text(json.dumps({'0':c.label_ids['PE'],'1':c.label_ids['BG']}),'utf-8')
    with connect_database(c.paths.database) as db:
        db.execute("INSERT INTO label (id,project_id,schema_id,code,name,tree_path,color_hex,sort_order,created_at) SELECT ?,project_id,schema_id,'ADDED','added','材料/塑料/ADDED','#112233',-1,'fixture' FROM label WHERE code='PE'",(str(uuid4()),))
    same = build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    np.testing.assert_array_equal(same['X_raw'],result['X_raw'])
    version = str(uuid4()); folder2=c.paths.snapshots/c.cubes[0]/'v2';folder2.mkdir()
    labels2=np.full((2,3),-1,np.int32); labels2[0,1]=0
    np.savez_compressed(folder2/'label_map.npz',label_map=labels2)
    (folder2/'label_index.json').write_text((folder/'label_index.json').read_text('utf-8'),'utf-8')
    with connect_database(c.paths.database) as db:
        db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) VALUES (?,?,2,?,6,1,'{}','fixture')",(version,c.cubes[0],f'{c.cubes[0]}/v2'))
    # Latest version by itself must not change a run-bound X.
    np.testing.assert_array_equal(build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)['X_raw'],result['X_raw'])
    with connect_database(c.paths.database) as db:
        db.execute('UPDATE preprocess_run SET annotation_version_id=? WHERE id=?',(version,c.runs[0]))
    changed=build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    assert not np.array_equal(changed['X_raw'][0],result['X_raw'][0])
    np.testing.assert_array_equal(changed['y'],result['y'])
    with connect_database(c.paths.database) as db:
        db.execute('DELETE FROM sample_target WHERE cube_id=?',(c.cubes[-1],))
    filtered=build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    assert len(filtered['y']) == 11 and filtered['meta']['excluded_without_target'] == 1
    assert len(filtered['preprocess_run_ids']) == len(filtered['groups']) == 11


def test_no_bg_fallback_and_all_background_error(regression_factory):
    c=seed(regression_factory())
    with connect_database(c.paths.database) as db:
        db.execute('UPDATE label SET is_background=0,shortcut_key=NULL')
    result=build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    np.testing.assert_allclose(result['X_raw'][0],c.values[0][c.maps[0]>=0].mean(axis=0))
    with connect_database(c.paths.database) as db:
        db.execute('UPDATE label SET is_background=1')
    with pytest.raises(DataError) as error:
        build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    assert error.value.code == 'NO_FOREGROUND_PIXELS'


def test_ks_deterministic_ties_ids_coverage_and_cv():
    X=np.array([[0,0],[1,0],[0,1],[1,1]],float)
    ids=['d','b','c','a'];y=np.array([0,1,2,3])
    first=kennard_stone(X,y,ids,test_ratio=.25)
    second=kennard_stone(X,y,ids,test_ratio=.25)
    np.testing.assert_array_equal(first['train_idx'],second['train_idx'])
    # Both diagonals tie; (a,d) wins, irrespective of input row order.
    assert {'a','d'} <= {ids[i] for i in first['train_idx']}
    for strategy,k in [('kfold',3),('loo',6)]:
        folds=plan_folds(np.arange(6),np.array(list('abcdef')),task='regression',strategy=strategy,folds=k,seed=17)
        assert len(folds) == k
        assert all(not set(f['train_groups']) & set(f['test_groups']) for f in folds)
    repair=kennard_stone(np.arange(12)[:,None], [1,2,3,4,-50,6,7,8,9,50,11,12],list('abcdefghijkl'))
    assert repair['coverage_repaired']
    train,test=repair['train_idx'],repair['test_idx'];values=np.array([1,2,3,4,-50,6,7,8,9,50,11,12])
    assert values[test].min()>=values[train].min() and values[test].max()<=values[train].max()


def test_seven_metrics_signed_bias_undefined_and_sample_gap_guard():
    metrics={**_regression([0,2,4],[0,1,5],'calibration'),**_regression([0,2,4],[1,3,5],'prediction')}
    assert set(metrics)==set(REGRESSION_METRICS)
    assert metrics['rmse']==pytest.approx(np.sqrt(2/3)) and metrics['r2']==.75
    assert metrics['rmsep']==1 and metrics['r2p']==.625
    assert metrics['rpd']==2 and metrics['rer']==4 and metrics['bias']==1
    assert _regression([2,2],[1,1],'prediction')['bias']==-1
    for true,pred in [([1],[1]),([1,1],[1,1])]:
        scores=_regression(true,pred,'prediction')
        assert all(scores[key] is None for key in ('r2p','rpd','rer'))
    _gap({'sample':metrics},'regression',{})


@pytest.mark.parametrize('strategy',['kfold','loo'])
def test_pls_curve_manual_metrics_artifacts_and_train_only_cv(regression_factory,monkeypatch,strategy):
    from spectrumagent.modeling.run import PLSRegression
    c=seed(regression_factory())
    data=build_sample_training_set(c.registry,c.paths,preprocess_run_ids=c.runs,target_schema_id=c.schema)
    split=kennard_stone(data['X'],data['y'],data['groups'].tolist())
    allowed={tuple(row) for row in data['X'][split['train_idx']]}
    original=PLSRegression.fit;seen=[]
    def fit(self,X,y):
        assert {tuple(row) for row in X}<=allowed
        seen.append(len(X));return original(self,X,y)
    monkeypatch.setattr(PLSRegression,'fit',fit)
    engine=TrainingRuns(c.registry,c.paths)
    result=engine.regress(**c.arguments,cv_strategy=strategy,n_components=1)
    assert result['status']=='succeeded' and result['selected_lv']==1
    sweep=engine.artifact(result['run_id'],'lv_sweep')
    assert sweep['manual_override'] and sweep['curve'] and sweep['elbow_lv']<=sweep['best_lv']
    assert sweep['by_cv_min'] == sweep['best_lv'] and sweep['by_elbow'] == sweep['elbow_lv']
    assert all(point['lv']==point['n_components'] for point in sweep['curve'])
    assert sweep['best_lv']==min(sweep['curve'],key=lambda row:(row['rmsecv'],row['n_components']))['n_components']
    assert set(result['metrics'])==set(REGRESSION_METRICS) and len(result['predictions'])==12
    assert seen and max(seen)==len(split['train_idx'])
    saved=engine.artifact(result['run_id'],'model')
    replay=(data['X']-np.asarray(saved['x_mean']))@np.asarray(saved['coef']).T+np.asarray(saved['intercept'])
    np.testing.assert_allclose(replay.ravel(),[row['y_pred'] for row in result['predictions']],atol=1e-12)
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT DISTINCT fold_index,scope FROM metric').fetchall()==[(None,'sample')]
        assert db.execute('SELECT count(*) FROM metric').fetchone()[0]==7
        assert db.execute('SELECT count(*) FROM training_fold').fetchone()[0]==(8 if strategy=='loo' else 3)
    with connect_database(c.paths.database) as db:
        db.execute("UPDATE metric SET value=2 WHERE name='rpd'")
    assert engine.get(result['run_id'])['quality_label']=='仅可做半定量'
    with connect_database(c.paths.database) as db:
        row=db.execute("SELECT relative_path FROM model_artifact WHERE kind='lv_sweep'").fetchone()[0]
    (c.paths.root/'models'/row).write_text('{}','utf-8')
    with pytest.raises(DataError,match='摘要'):
        engine.artifact(result['run_id'],'lv_sweep')


def test_near_duplicate_spectra_block_before_run(regression_factory):
    c=seed(regression_factory())
    first,_=c.registry.get(c.cubes[0]);second,_=c.registry.get(c.cubes[1])
    from pathlib import Path
    values=np.frombuffer(Path(first.data_path).read_bytes(),dtype=np.uint16).copy()+1
    Path(second.data_path).write_bytes(values.tobytes())
    with pytest.raises(DataError) as error:
        TrainingRuns(c.registry,c.paths).regress(**c.arguments)
    assert error.value.code=='LEAK_PREFLIGHT_FAILED'
    assert error.value.payload.context['leak_report']['near_duplicate_spectra']['pair_count']>0
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT count(*) FROM training_run').fetchone()[0]==0


def test_real_asgi_csv_annotation_pls_68_samples_and_lv_endpoint(regression_factory):
    c=regression_factory(68); identity=EngineIdentity()
    with TestClient(create_app(c.paths,identity)) as client:
        client.headers['Authorization']='Bearer '+identity.token
        response=client.post('/api/v1/models/sample-targets/import-csv',json={'project_id':c.project,'csv_text':c.csv_text})
        assert response.status_code==200 and response.json()['imported']==68
        value=client.put(f'/api/v1/models/sample-targets/{c.cubes[0]}/{c.schema}',json={'value':.5})
        assert value.status_code==200 and value.json()['source']=='annotation'
        response=client.post('/api/v1/models/runs',json={**c.arguments,'task':'regression'})
        assert response.status_code==200,response.text
        result=response.json();assert result['status']=='succeeded'
        assert result['n_samples']==68 and result['n_pixels_used']==272
        assert client.get('/api/v1/models/runs/'+result['run_id']+'/lv-sweep').json()['curve']
        assert len(client.get('/api/v1/models/sample-targets',params={'project_id':c.project}).json())==68
        assert set(result['metrics'])==set(REGRESSION_METRICS)
        assert all('residual' in row for row in result['predictions'])
        assert 'X-SpectrumAgent-Boot-Id' in response.headers
        print('PLS_E2E n_samples=68 n_pixels_used=272 targets=68 metrics=7 lv_sweep=pass')


def test_csv_schema_priority_ambiguity_unknown_type_and_range(regression_factory):
    from spectrumagent.annotation.labels import LabelStore, SchemaRequest
    c=regression_factory()
    store=LabelStore(c.paths.database)
    for name,path in [('重名','字段甲'),('重名','字段乙'),('唯一别名','唯一字段')]:
        store.add(SchemaRequest.model_validate({'project_id':c.project,'schema':{'name':name,'tree_path':path,'field_type':'continuous','config':{'min':0,'max':100}}}))
    name=c.registry.get(c.cubes[0])[0].name
    response=c.targets.import_csv(c.project,'cube_name,schema,value\n'+f'{name},重名,3\n{name},未知字段,3\n{name},材料,3\n{name},唯一字段,101\n')
    assert response['imported']==0 and len(c.targets.list(c.project))==0
    assert any(row['error']=='AMBIGUOUS_SCHEMA' and row['candidates']==['字段乙','字段甲'] for row in response['invalid'])
    assert any(row['error']=='NON_CONTINUOUS_SCHEMA' for row in response['invalid'])
    assert response['unknown_fields'] and response['out_of_range']
    assert c.targets.import_csv(c.project,'cube_name,schema,value\n'+f'{name},唯一别名,25\n')['imported']==1
    with connect_database(c.paths.database) as db:
        schema=db.execute("SELECT id FROM label_schema WHERE tree_path='唯一字段'").fetchone()[0]
    with pytest.raises(DataError) as error:
        c.targets.put(c.cubes[0],schema,-1)
    assert error.value.code=='TARGET_OUT_OF_RANGE'


@pytest.mark.parametrize('text', ['"unfinished header', 'cube_name,schema,value\n"unfinished row'])
def test_malformed_csv_header_or_row_refuses_without_writes(regression_factory,text):
    c=regression_factory()
    with pytest.raises(DataError) as error:
        c.targets.import_csv(c.project,text)
    assert error.value.code=='INVALID_TARGET_CSV'
    assert c.targets.list(c.project)==[]


@pytest.mark.parametrize('strategy',['group_kfold','random'])
def test_regression_cv_rejects_pixel_or_trivial_group_aliases(strategy):
    with pytest.raises(DataError) as error:
        plan_folds([0,1,2,3],list('abcd'),task='regression',strategy=strategy,folds=2,seed=17)
    assert error.value.code=='INVALID_CV_PARAMS'


def test_preflight_split_task_compatibility():
    from pydantic import ValidationError
    from spectrumagent.api.models import PreflightRequest
    body=dict(cube_ids=['c'],annotation_version_ids=['v'],preprocess_run_ids=['r'],task='classification',target='label',cv_strategy='random',cv_folds=2,seed=17)
    assert PreflightRequest(**body).split_strategy=='none'
    for change in [{'split_strategy':'ks'},{'task':'regression'}]:
        with pytest.raises(ValidationError):
            PreflightRequest(**{**body,**change})


def test_undefined_scores_persist_null_not_zero(regression_factory):
    c=seed(regression_factory())
    with connect_database(c.paths.database) as db:
        db.execute('UPDATE sample_target SET value=1')
    result=TrainingRuns(c.registry,c.paths).regress(**{**c.arguments,'max_components':1})
    assert result['status']=='succeeded'
    for name in ('r2','r2p','rpd','rer'):
        assert result['metrics'][name] is None
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT count(*) FROM metric WHERE value IS NULL').fetchone()[0]==4


def test_fit_failure_records_failed_run_without_model_or_metric(regression_factory,monkeypatch):
    from spectrumagent.modeling.run import PLSRegression
    c=seed(regression_factory())
    def fail(*args,**kwargs):
        raise RuntimeError('sensitive-local-path')
    monkeypatch.setattr(PLSRegression,'fit',fail)
    with pytest.raises(DataError) as error:
        TrainingRuns(c.registry,c.paths).regress(**c.arguments)
    assert error.value.code=='PLS_FIT_FAILED' and 'sensitive-local-path' not in str(error.value)
    with connect_database(c.paths.database) as db:
        assert db.execute('SELECT status FROM training_run').fetchone()[0]=='failed'
        assert db.execute('SELECT count(*) FROM metric').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM model_artifact').fetchone()[0]==0
