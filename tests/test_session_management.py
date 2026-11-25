"""S01 session management keeps audit records and shared numerical artifacts."""
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.database import connect_database
from spectrumagent.agent.session_history import SessionHistory
from spectrumagent.agent.state import AgentStore
from spectrumagent.experiments.inference import InferenceConfig
from test_experiment_conversation import application, workspace
from test_experiment_inference import train, wait
from test_experiment_study import envi_scene


URL = '/api/v1/agent/sessions'


def authorize(client, app):
    client.headers['Authorization'] = 'Bearer '+app.state.testing_identity.token


def test_sessions_order_title_and_cursor(application):
    database = application.state.experiments.paths.database
    store = AgentStore(database)
    old, remote, other, pending, newest = [store.create_session()['id'] for _ in range(5)]
    with connect_database(database) as db:
        db.execute("UPDATE agent_session SET updated_at='2025-01-01T00:00:00+00:00'")
        db.execute("UPDATE agent_session SET updated_at='2025-01-02T00:00:00+00:00' WHERE id=?", (newest,))
    request_log = SessionHistory(application.state.agent_sessions)
    request,_ = request_log.start(remote,{'content':'本机会话操作'})
    request_log.append(remote,'user',{'content':'本机会话操作'},request,request+':input')
    request_log.finish(remote,request,'completed',True)
    assert application.state.agent_sessions.list()['sessions'][0]['id']==remote
    with connect_database(database) as db:
        db.execute("UPDATE agent_session SET updated_at='2025-01-01T00:00:00+00:00' WHERE id=?", (remote,))
    text = '   旧会话第一句\n继续\t观察    光谱  ' + '长'*45
    store.new_round(old,text,[],status='done')
    store.new_round(pending,'需要核对的操作',[],status='plan_check')
    with TestClient(application) as client:
        authorize(client,application)
        collected, cursor = [], None
        while True:
            params = {'kind':'global','limit':2}
            if cursor:
                params['cursor'] = cursor
            response = client.get(URL,params=params)
            assert response.status_code==200,response.text
            page = response.json()
            collected.extend(page['sessions'])
            cursor = page['next_cursor']
            if not cursor:
                break
        assert [row['id'] for row in collected]==[pending,old,newest,*sorted((other,remote),reverse=True)]
        by_id = {row['id']:row for row in collected}
        assert by_id[old]['title']==' '.join(text.split())[:40]
        assert store.rounds(old)[0]['user_message']==text
        assert by_id[pending]['pending'] is True and by_id[other]['pending'] is False
        assert by_id[remote]['history_watermark']==1 and by_id[remote]['request']['status']=='completed'
        assert all(set(row)=={'id','title','created_at','updated_at','pending','request','history_watermark'} for row in collected)


@pytest.mark.parametrize('kind',['training','study','inference'])
def test_archive_rejects_active_numerical_task_for_its_owner(application,kind):
    store = AgentStore(application.state.experiments.paths.database)
    owner, other = [store.create_session()['id'] for _ in range(2)]
    dialogue = application.state.agent_tools.experiment_dialogue
    identifier = str(uuid4())
    if kind=='training':
        table, key = dialogue.tasks.rows, identifier
        table[key] = {'task_id':identifier,'session_id':owner,'status':'queued'}
    elif kind=='study':
        table, key = dialogue.study.active, identifier
        table[key] = (owner,Event())
    else:
        table, key = dialogue.inference.service.active, (str(uuid4()),identifier)
        table[key] = (owner,Event())
    try:
        with TestClient(application) as client:
            authorize(client,application)
            assert client.post(f'{URL}/{other}/archive').status_code==200
            response = client.post(f'{URL}/{owner}/archive')
            assert response.status_code==409 and response.json()['error']=='SESSION_BUSY'
            assert client.get(f'{URL}/{owner}').status_code==200
            if kind=='training':
                table[key]['status']='running'
                assert client.post(f'{URL}/{owner}/archive').status_code==409
                table[key]['status']='succeeded'
            else:
                table.pop(key)
            assert client.post(f'{URL}/{owner}/archive').status_code==200
    finally:
        table.pop(key,None)


def test_soft_archive_preserves_audit_model_and_inference_report(application,tmp_path):
    model, inference = train(application,tmp_path,image=True)
    store = AgentStore(inference.database)
    owner, other = [store.create_session()['id'] for _ in range(2)]
    header = tmp_path/'scene.hdr'
    envi_scene(header,np.arange(1100,1145,5))
    config = InferenceConfig(model_id=model,input={
        'kind':'envi','paths':[str(header)],'wavelength_unit':'nm','mapping_window_nm':5.,
        'nearest_tolerance_nm':5.,'quality':{'min_mean':0.,'min_std':0.,'max_zero_fraction':1.,'saturation':None},
    })
    run = inference.service.submit(owner,config,inference.service.inspect(config))['inference_run_id']
    assert wait(inference.service,model,run)['status']=='succeeded'
    report = inference.service.folder(model,run)/'report.html'
    model_file = application.state.experiments.artifact(model,'model.joblib')
    before = model_file.read_bytes(),report.read_bytes()
    store.new_round(owner,'原始会话审计内容',[],status='done')
    log = SessionHistory(application.state.agent_sessions)
    request,_ = log.start(owner,{'content':'待结束的请求'})
    log.append(owner,'user',{'content':'待结束的请求'},request,request+':input')

    with TestClient(application) as client:
        authorize(client,application)
        assert client.post(f'{URL}/{owner}/archive').status_code==409
        log.finish(owner,request,'completed',True)
        assert client.post(f'{URL}/{owner}/archive').json()=={'session_id':owner,'archived':True}
        archived = client.get(f'{URL}/{owner}')
        assert archived.status_code==404 and archived.json()['error']=='SESSION_ARCHIVED'
        assert [row['id'] for row in client.get(URL).json()['sessions']]==[other]
        history = f'{URL}/{other}/experiment-history/{model}'
        assert client.get(history+'/result').status_code==200
        assert client.post(history+f'/inferences/{run}/report').json()=={'ready':True}

    with connect_database(inference.database) as db:
        for table,field in (('agent_session','id'),('agent_round','session_id'),('agent_session_request','session_id'),
                            ('agent_session_event','session_id'),('agent_session_archive','session_id')):
            assert db.execute(f'SELECT COUNT(*) FROM {table} WHERE {field}=?',(owner,)).fetchone()[0]==1
    assert before==(model_file.read_bytes(),report.read_bytes())
