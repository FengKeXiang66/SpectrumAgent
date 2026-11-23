import csv
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from test_experiment_conversation import application, workspace
from spectrumagent.experiments.group_split import propose, requested
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


def test_explicit_one_image_per_object_and_preassigned_role(tmp_path, application):
    from spectrumagent.experiments.group_split import answer
    dialogue = application.state.agent_tools.experiment_dialogue
    from test_experiment_conversation import AgentStore
    owner = AgentStore(dialogue.database).create_session()['id']
    msg,_ = demo_data(tmp_path/'new')
    assert answer(dialogue,owner,msg,PATHS)[1] == 'needs_input'
    assert answer(dialogue,owner,'每张图都是独立样品',PATHS)[1] == 'ready'
    image = next((tmp_path/'new'/'原图').glob('PE-*.hdr'))
    text,status = answer(dialogue,owner,f'指定测试组：“{image}”',PATHS)
    assert status == 'ready' and str(image) in text
    ann = next((tmp_path/'new'/'标注').glob('*.json'))
    doc = json.loads(ann.read_text(encoding='utf8'))
    ann.write_text(json.dumps(dict(doc,dataset_split='fiveclass_test')),encoding='utf8')
    import pytest
    with pytest.raises(ValueError,match='已有明确用途'):
        answer(dialogue,owner,msg,PATHS)
