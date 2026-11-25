import csv
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from test_experiment_conversation import application, wait_task, workspace
from spectrumagent.experiments.group_split import BASELINE_COMMAND, propose, requested
from spectrumagent.experiments.conversation import PATHS


def demo_data(root):
    images = root/'原图'
    annotations = root/'标注'
    images.mkdir(parents=True)
    annotations.mkdir()
    mapping = root/'实物分组.csv'
    with mapping.open('w', encoding='utf-8-sig',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source','sample_id','batch'])
        for label,n in [('PE',4),('PP',4),('PET',1)]:
            for index in range(n):
                for repeat in range(2):
                    name = f'{label}-{index+1}-{repeat+1}'
                    hdr = images/(name+'.hdr')
                    hdr.write_text('ENVI\nsamples=4\nlines=4\nbands=2\ndata type=12\ninterleave=bip\nbyte order=0\nwavelength={1100,1105}\n')
                    hdr.with_suffix('.img').write_bytes(bytes([index+repeat,0])*32)
                    annotation = dict(source_hdr=str(hdr),imageWidth=4,imageHeight=4,
                                      shapes=[dict(label=label,shape_type='rectangle',points=[[0,0],[3,3]])])
                    (annotations/(name+'.json')).write_text(json.dumps(annotation),encoding='utf8')
                    writer.writerow([str(hdr),f'{label}-{index+1}',f'B{index+1}'])
    return f'原图在“{images}”，标注在“{annotations}”，我想识别新塑料样品，帮我划分训练集和测试集。',mapping


def test_preview_adjust_holdout_confirm_restart_and_stale(tmp_path, application):
    msg,mapping = demo_data(tmp_path/'样例')
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer ' + application.state.testing_identity.token
        create = lambda: client.post('/api/v1/agent/sessions',json={}).json()['id']
        sid = create()
        def chat(text, owner=None):
            response = client.post(f'/api/v1/agent/sessions/{owner or sid}/messages',
                                   json={'content':text,'request_id':str(uuid4())})
            assert response.status_code == 200
            return response.text
        assert '缺少实物编号' in chat(msg)
        assert '没有可保存' in chat('确认保存划分')
        assert '仅一件实物' in chat(f'提供分组表 “{mapping}”')
        assert '分组交叉 0' in chat('查看划分方案')
        assert '1/2 页' in chat('划分明细 第1页')
        assert '30%' in chat('调整划分，测试占30%，随机种子 9')
        assert '指定的测试实物：PE-2、PP-2' in chat('指定测试组：PE-2、PP-2')
        assert '未应用' in chat('调整划分，测试占120%')
        assert '请回复“查看划分方案”' in chat('确认保存划分')
        assert '指定的测试实物' in chat('查看划分方案')
        assert '请提供原图目录' in chat('确认保存划分',create())
        assert '已保存逐图划分清单' in chat('确认保存划分')
        assert '该版划分已保存' in chat('确认保存划分')
        folder = application.state.experiments.paths.exports/'split-plans'
        (path,) = list(folder.glob('*.json'))
        saved = json.loads(path.read_text(encoding='utf8'))
        assert saved['target_test_percent']==30 and saved['seed']==9
        rows = saved['rows']
        assert len(rows)==18 and len({p['hdr'] for p in rows})==18
        assert {r['group'] for r in rows if r['split']=='测试'} == {'PE-2','PP-2'}
        assert all(len({r['split'] for r in rows if r['sample_id']==key})==1 for key in {r['sample_id'] for r in rows})
        assert '留出批次' in chat('按批次划分')
        assert 'B3' in chat('指定测试批次：B3')
        hdr = Path(rows[0]['hdr'])
        hdr.write_text(hdr.read_text()+'\n')
        assert '已变化' in chat('确认保存划分')
        assert list(folder.glob('*.json')) == [path]


def test_known_sample_cannot_cross_batch_and_multilabel_group():
    rows = [dict(hdr=str(i),sample_id=g,batch=b,labels=labels) for i,(g,b,labels) in enumerate([
        ('a','B1',['PE','PP']),('a','B2',['PE','PP']),('b','B3',['PE','PP']),('only','B1',['PET'])])]
    state = dict(rows=rows,mode='batch',hold=['B2'],ratio=20,seed=42,individual=False)
    assert not propose(state)[0]
    state.update(hold=[])
    plan,_ = propose(state)
    assert {p['batch'] for p in plan if p['split']=='测试'} == {'B3'}
    state.update(mode='sample')
    first,_ = propose(state)
    assert first == propose(state)[0]
    assert all(p['split']=='训练' for p in first if 'PET' in p['labels'])
    assert not requested('训练原图：“D:/fixed”，测试原图：“D:/test”，标注已划分',PATHS)


def test_saved_split_to_baseline_http(tmp_path, application, monkeypatch):
    msg, mapping = demo_data(tmp_path/'baseline')
    for hdr in mapping.parent.joinpath('原图').glob('*.hdr'):
        hdr.write_text(hdr.read_text().replace('samples=4', 'samples=8').replace('lines=4', 'lines=8')
                       + 'wavelength units=nm\n')
        base = {'PE':[10,90], 'PP':[90,10], 'PET':[45,55]}[hdr.stem.split('-')[0]]
        data = np.broadcast_to(np.asarray(base, dtype='<u2'), (8,8,2)).copy()
        hdr.with_suffix('.img').write_bytes(data.tobytes())
        roi = mapping.parent/'标注'/(hdr.stem+'.json')
        annotation = json.loads(roi.read_text('utf-8'))
        annotation.update(imageHeight=8, imageWidth=8)
        annotation['shapes'][0]['points'][1] = [7,7]
        roi.write_text(json.dumps(annotation), encoding='utf-8')
    dialogue = application.state.agent_tools.experiment_dialogue
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer ' + application.state.testing_identity.token
        sid = client.post('/api/v1/agent/sessions', json={}).json()['id']
        def chat(content, owner=sid):
            return client.post(f'/api/v1/agent/sessions/{owner}/messages',
                               json={'content':content, 'request_id':str(uuid4())}).text
        assert '缺少实物编号' in chat(msg)
        assert '先确认保存划分' in chat(BASELINE_COMMAND)
        assert '分组交叉 0' in chat(f'提供分组表 “{mapping}”')
        assert 'split_saved' in chat('确认保存划分')
        (path,) = (dialogue.service.paths.exports/'split-plans').glob('*.json')
        reply = chat(BASELINE_COMMAND)
        assert 'split_baseline_ready' in reply and '采样步长：3' in reply and '测试侧未覆盖：PET' in reply
        assert dialogue.tasks.latest(sid) is None
        from spectrumagent.agent.execution import RequestCancelled, RequestControl
        from spectrumagent.experiments import inputs
        config = dialogue._config(dialogue._read(sid))
        control = RequestControl(str(uuid4()))
        real_hash = inputs.sha256
        def cancel_on_hash(file, check=None):
            control.cancel()
            return real_hash(file, check)
        with monkeypatch.context() as m:
            m.setattr(inputs, 'sha256', cancel_on_hash)
            with pytest.raises(RequestCancelled):
                dialogue.review_sources(config, check=control.check)
        assert 'experiment_task_id' in chat('确认执行')
        task = wait_task(dialogue.tasks, sid, dialogue.tasks.latest(sid))
        assert task['status'] == 'succeeded', task
        folder = dialogue.service.folder(task['experiment_id'])
        assert (folder/'split_plan.json').read_bytes() == path.read_bytes()
        rows = json.loads(path.read_bytes())['rows']
        for role, title in (('train','训练'), ('test','测试')):
            origins = json.loads((folder/(role+'_origins.json')).read_bytes())
            assert {row['source'] for row in origins} == {row['hdr'] for row in rows if row['split'] == title}
            assert len(origins) == sum(row['split'] == title for row in rows)*4
            assert {(row['row'],row['col']) for row in origins} == {(3,3),(3,6),(6,3),(6,6)}
            with np.load(folder/(role+'_prepared.npz')) as prepared:
                assert len(prepared['X']) == len(origins) == len(prepared['y'])
        assert dialogue.service.archive.load_model(task['experiment_id']).config.split_manifest.split_id == path.stem
        second = client.post('/api/v1/agent/sessions', json={}).json()['id']
        assert 'split_baseline_ready' in chat(f'{BASELINE_COMMAND} “{path}”', second)
        from spectrumagent.agent.tools.experiments import DraftUpdate
        revision = dialogue.view(second)['revision']
        updated = dialogue.update(second, DraftUpdate(expected_revision=revision,
                                  train={'kind':'roi_images', 'sampling_stride':2}))
        assert updated['plan'].count('采样步长：2') == 2
        assert '没有有效的待确认方案' in chat('确认执行', second)
        dialogue.presented(second, str(uuid4()))
        annotation = Path(rows[0]['annotation'])
        annotation.write_bytes(annotation.read_bytes() + b'\n')
        assert 'experiment_task_id' in chat('确认执行', second)
        failed = wait_task(dialogue.tasks, second, dialogue.tasks.latest(second))
        assert failed['error'] == 'EXPERIMENT_INPUT_CHANGED'
        assert '已变化' in chat(f'{BASELINE_COMMAND} “{path}”', second)


def test_explicit_one_image_per_object_and_preassigned_role(tmp_path, application):
    from spectrumagent.experiments.group_split import answer
    dialogue = application.state.agent_tools.experiment_dialogue
    from test_experiment_conversation import AgentStore
    owner = AgentStore(dialogue.database).create_session()['id']
    msg,_ = demo_data(tmp_path/'new')
    for hdr in (tmp_path/'new'/'原图').glob('*.hdr'):
        hdr.write_text(hdr.read_text()+'wavelength units=Nanometers\n')
    assert answer(dialogue,owner,msg,PATHS)[1] == 'needs_input'
    assert answer(dialogue,owner,'每张图都是独立样品',PATHS)[1] == 'ready'
    image = next((tmp_path/'new'/'原图').glob('PE-*.hdr'))
    text,status = answer(dialogue,owner,f'指定测试组：“{image}”',PATHS)
    assert status == 'ready' and str(image) in text
    assert answer(dialogue,owner,'确认保存划分',PATHS)[1] == 'saved'
    dialogue.prepare_split_baseline(owner,None)
    review = dialogue.presented(owner,'by-image')
    assert review['split_checks']['physical_sample_independence']=='declared_one_image_one_sample'
    assert '按用户声明每图独立实物无交叉' in review['plan'] and '实物独立性未知' not in review['plan']
    ann = next((tmp_path/'new'/'标注').glob('*.json'))
    doc = json.loads(ann.read_text(encoding='utf8'))
    ann.write_text(json.dumps(dict(doc,dataset_split='fiveclass_test')),encoding='utf8')
    with pytest.raises(ValueError,match='已有明确用途'):
        answer(dialogue,owner,msg,PATHS)
