"""Directory pairing is local and never assigns a sample to a new split."""
import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from test_experiment_conversation import application, workspace, AgentStore, ScriptedModel, machine_for
from spectrumagent.experiments.pairing import inventory, requested
from spectrumagent.experiments.conversation import PATHS


def inputs(tmp_path):
    roots = {}
    for role in ('训练', '测试'):
        hdr_dir = tmp_path / (role + ' 数据')
        ann_dir = tmp_path / (role + ' 标注')
        hdr_dir.mkdir()
        ann_dir.mkdir()
        hdr = hdr_dir / 'same.hdr'
        hdr.write_text('ENVI\nsamples=4\nlines=4\nbands=2\ninterleave=bip\ndata type=12\n'
                       'byte order=0\nwavelength={1100,1105}\n')
        hdr.with_suffix('.img').write_bytes(bytes(64))
        ann = dict(source_hdr=str(hdr), imageWidth=4, imageHeight=4, role='旧用途',
                   shapes=[dict(shape_type='rectangle', label='PE', points=[[0,0],[3,3]])])
        (ann_dir / 'unrelated.json').write_text(json.dumps(ann), encoding='utf8')
        roots[role+'原图'] = [hdr_dir]
        roots[role+'标注'] = [ann_dir]
    return roots


def test_standard_labelme_prefers_mirrored_relative_path_over_repeated_names(tmp_path):
    roots = inputs(tmp_path)
    raw = roots['训练原图'][0]
    labels = roots['训练标注'][0]
    scene = raw/'采集批次'
    scene.mkdir()
    for suffix in ('.hdr','.img'):
        (scene/('same'+suffix)).write_bytes((raw/('same'+suffix)).read_bytes())
    nested = labels/scene.name
    nested.mkdir()
    annotation = labels/'unrelated.json'
    doc = json.loads(annotation.read_text('utf8'))
    del doc['source_hdr']
    doc['imagePath'] = 'same.jpg'
    data = json.dumps(doc).encode()
    annotation.unlink()
    target = nested/'标注.json'
    target.write_bytes(data)
    report = inventory(roots)
    assert not report['issues'] and len(report['pairs'])==2
    assert next(row['hdr'] for row in report['pairs'] if row['role']=='训练')==str(scene/'same.hdr')
    assert target.read_bytes()==data
    doc['source_hdr'] = str(raw/'same.hdr')
    target.write_text(json.dumps(doc),'utf8')
    report = inventory(roots)
    assert not report['issues']
    assert next(row['hdr'] for row in report['pairs'] if row['role']=='训练')==str(raw/'same.hdr')


def test_labelme_reports_ambiguous_basename_and_allows_unique_fallback(tmp_path):
    roots = inputs(tmp_path)
    raw = roots['训练原图'][0]
    first, second = [raw/name for name in ('甲','乙')]
    for folder in (first,second):
        folder.mkdir()
        for suffix in ('.hdr','.img'):
            (folder/('same'+suffix)).write_bytes((raw/('same'+suffix)).read_bytes())
    for suffix in ('.hdr','.img'):
        (raw/('same'+suffix)).unlink()
    annotation = roots['训练标注'][0]/'unrelated.json'
    doc = json.loads(annotation.read_text('utf8'))
    del doc['source_hdr']
    doc['imagePath'] = r'迁移前的目录\same.tif'
    annotation.write_text(json.dumps(doc),'utf8')
    report = inventory(roots)
    assert any('配对歧义' in issue and str(first) in issue and str(second) in issue for issue in report['issues'])
    assert all(row['role']!='训练' for row in report['pairs'])
    (second/'same.hdr').unlink()
    report = inventory(roots)
    assert not report['issues'] and next(row['hdr'] for row in report['pairs'] if row['role']=='训练')==str(first/'same.hdr')


@pytest.mark.parametrize('mismatch',[None,'hdr_sha256','img_bytes','img_path_exact','imagePath_missing'])
def test_migrated_labelme_path_checks_signatures_without_requiring_old_drive(tmp_path,mismatch):
    roots = inputs(tmp_path)
    hdr = roots['训练原图'][0]/'same.hdr'
    annotation = roots['训练标注'][0]/'unrelated.json'
    doc = json.loads(annotation.read_text('utf8'))
    doc.update(source_hdr=r'X:\已迁移\same.hdr',imagePath='same.png',
               source_signature={'img_path':r'X:\已迁移\same.img','img_bytes':64,
                                 'hdr_sha256':hashlib.sha256(hdr.read_bytes()).hexdigest()})
    if mismatch in ('hdr_sha256','img_bytes'):
        doc['source_signature'][mismatch]='0'*64 if mismatch=='hdr_sha256' else 65
    elif mismatch=='img_path_exact':
        doc['source_hdr'] = str(hdr)
    elif mismatch=='imagePath_missing':
        del doc['imagePath']
    annotation.write_text(json.dumps(doc),'utf8')
    report = inventory(roots)
    if mismatch:
        expected = {'hdr_sha256':'绑定的HDR','img_bytes':'IMG 大小','img_path_exact':'IMG 路径',
                    'imagePath_missing':'提供可匹配的 source_hdr'}[mismatch]
        assert any(expected in issue for issue in report['issues'])
        assert all(row['role']!='训练' for row in report['pairs'])
    else:
        assert not report['issues'] and next(row['hdr'] for row in report['pairs'] if row['role']=='训练')==str(hdr)


@pytest.mark.parametrize('x,y,accepted',[(4,4,True),(4.00001,3,False),(3,4.00001,False),(-.00001,3,False)])
def test_labelme_exact_right_and_bottom_edges_are_clamped(tmp_path,x,y,accepted):
    from spectrumagent.data import DataError
    from spectrumagent.experiments.inputs import roi_maps

    roi = tmp_path/'labelme.json'
    roi.write_text(json.dumps({'imageHeight':4,'imageWidth':4,'shapes':[
        {'label':'PE','shape_type':'polygon','points':[[0,0],[x,0],[x,y],[0,y]]}]}),'utf8')
    if accepted:
        regions, labels = roi_maps(roi,(4,4),{1:'PE'})
        assert regions[3,3]==labels[3,3]==1
    else:
        with pytest.raises(DataError,match='越界'):
            roi_maps(roi,(4,4),{1:'PE'})


def test_local_preview_and_pages(tmp_path, application):
    roots = inputs(tmp_path)
    message = '配对预览；' + '；'.join(f'{k}：“{v[0]}”' for k,v in roots.items())
    store = AgentStore(application.state.experiments.paths.database)
    first, other = (store.create_session()['id'] for _ in range(2))
    def answer(sid, text):
        events = list(machine_for(application, sid, ScriptedModel()).message(content=text))
        assert events[-1][0] == 'done'
        return events[-1][1]['content']
    assert '异常记录 0 条' in answer(first, message)
    assert '共 2 条' in answer(first, '配对明细')
    assert '还没有' in answer(other, '配对明细')
    assert '有效页码' in answer(first, '配对明细 第2页')
    assert not requested('已有标注的训练与测试，原图 "D:/train.hdr"', PATHS)
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer ' + application.state.testing_identity.token
        sid = client.post('/api/v1/agent/sessions', json={}).json()['id']
        url = f'/api/v1/agent/sessions/{sid}/messages'
        for content, expected in ((message, '成功配对 1 幅原图'), ('配对明细', 'unrelated.json')):
            response = client.post(url, json={'content': content, 'request_id': str(uuid4())})
            assert response.status_code == 200 and expected in response.text, response.text
        history = machine_for(application, sid, ScriptedModel())._history_messages({})
        assert str(tmp_path) not in str(history) and 'unrelated.json' not in str(history)



def test_pairing_view_uses_session_snapshot_and_only_reads_paired_text(tmp_path, application):
    roots = inputs(tmp_path)
    unused = roots['训练原图'][0] / 'unused.hdr'
    unused.write_text('unlabelled', 'utf8')
    hdr = roots['测试原图'][0]/'same.hdr'
    hdr.write_bytes(hdr.read_bytes() + '\ndescription={中文描述}\n'.encode('gb18030'))
    message = '配对预览；' + '；'.join(f'{key}：“{value[0]}”' for key,value in roots.items())
    store = AgentStore(application.state.experiments.paths.database)
    owner, other = (store.create_session()['id'] for _ in range(2))
    def scan():
        events = list(machine_for(application,owner,ScriptedModel()).message(content=message))
        return next(step['result_summary']['pairing_preview_id'] for kind,step in events if kind=='step')
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer ' + application.state.testing_identity.token
        endpoint = f'/api/v1/agent/sessions/{owner}/pairing-view'
        preview = scan()
        query = dict(preview_id=preview,section='pairs',limit=1)
        first = client.get(endpoint,params=query).json()
        assert first['total']==2 and len(first['items'])==1 and first['counts']['unused']==1
        selected = client.get(endpoint,params={**query,'label':'PE','role':'测试','search':'same.hdr'}).json()
        assert selected['total']==1 and selected['items'][0]['role']=='测试'
        assert client.get(endpoint,params={**query,'offset':1}).json()['items'][0]['index'] != first['items'][0]['index']
        assert client.get(endpoint,params={**query,'section':'unused','search':'unused'}).json()['total']==1
        assert client.get(endpoint.replace(owner,other),params=query).json()['status']=='empty'
        row = selected['items'][0]
        files = f"{endpoint}/{preview}/files/{row['index']}"
        assert '中文描述' in client.get(files+'/hdr').json()['text']
        assert 'shapes' in client.get(files+'/annotation').json()['text']
        assert client.get(files+'/img').status_code==400
        annotation = roots['测试标注'][0]/'unrelated.json'
        annotation.write_text(annotation.read_text('utf8')+'\n', 'utf8')
        assert client.get(files+'/annotation').status_code==409
        assert scan()!=preview
        assert client.get(endpoint,params=query).json()['status']=='stale'
        assert client.get(files+'/hdr').status_code==409

def test_duplicate_wrong_split_corrupt_and_manifest(tmp_path):
    roots = inputs(tmp_path)
    train_ann = roots['训练标注'][0] / 'unrelated.json'
    test_ann = roots['测试标注'][0] / 'unrelated.json'
    test_hdr = roots['测试原图'][0] / 'same.hdr'
    doc = json.loads(train_ann.read_text())
    (train_ann.parent / 'duplicate.json').write_text(json.dumps(doc))
    (train_ann.parent / 'wrong.json').write_text(json.dumps({**doc,'source_hdr':str(test_hdr)}))
    test_hdr.with_suffix('.img').write_bytes(b'')
    (test_ann.parent / 'bad.json').write_text('{')
    manifest = tmp_path / 'manifest.csv'
    manifest.write_text(f'split,source,annotation\n测试V2,{test_hdr},{test_ann}\n', encoding='utf8')
    report = inventory({**roots,'清单':[manifest]})
    assert not report['pairs']
    for expected in ('重复绑定', '用途冲突', 'bad.json', '清单记录未通过', '大小'):
        assert any(expected in issue for issue in report['issues'])


def test_natural_directory_handoff(tmp_path, application):
    from spectrumagent.experiments import pairing_intake
    dialogue = application.state.agent_tools.experiment_dialogue
    store = AgentStore(dialogue.database)
    owner = store.create_session()['id']
    other = store.create_session()['id']
    def chat(text):
        events = list(machine_for(application,owner,ScriptedModel()).message(content=text))
        return events[-1][1].get('question') or events[-1][1]['content']
    roots = inputs(tmp_path)
    extra = []
    for index in range(3):
        folder = tmp_path / f'额外原图 {index}'
        folder.mkdir()
        extra.append(folder)
    assert 'source_hdr' in chat('人工标注这块我已经有了json标注，后面我把ENVI文件目录和json目录发给你，能用吗')
    message = (f'做5分类，具体训练和测试ENVI数据的目录，以及对应的标注文件JSON如下：训练数据：“{roots["训练原图"][0]}”、'
               f'“{extra[0]}”、“{extra[1]}”，对应标注：“{roots["训练标注"][0]}” '
               f'测试数据：“{roots["测试原图"][0]}”、“{extra[2]}”，对应标注：“{roots["测试标注"][0]}”')
    assert '对，先检查' in chat(message)
    fields = pairing_intake.draft(dialogue.database,owner)['fields']
    assert fields == {'训练原图':['S1','S2','S3'], '训练标注':['S4'], '测试原图':['S5','S6'], '测试标注':['S7']}
    assert pairing_intake.route(dialogue,other,'对，先检查') is None
    assert '请指出' in chat('调整目录用途')
    assert '训练标注：S4' in chat('第四个目录是训练标注')
    assert '异常记录 0 条' in chat('对，先检查')
    assert '共 2 条' in chat('配对明细')
    assert not pairing_intake.draft(dialogue.database,owner)
    history = str(machine_for(application,owner,ScriptedModel())._history_messages({},limit=20))
    assert str(tmp_path) not in history and '额外原图 0' not in history
    assert dialogue.tasks.latest(owner) is None


def test_collect_directories_across_turns_and_cancel(tmp_path,application):
    from spectrumagent.experiments import pairing_intake
    dialogue = application.state.agent_tools.experiment_dialogue
    owner = AgentStore(dialogue.database).create_session()['id']
    roots = inputs(tmp_path)
    def chat(text):
        events = list(machine_for(application,owner,ScriptedModel()).message(content=text))
        return events[-1][1].get('question') or events[-1][1]['content']
    assert 'source_hdr' in chat('我已有 ENVI 和 JSON 标注，能用吗')
    assert '还需指定' in chat(f'训练原图：“{roots["训练原图"][0]}”')
    assert '还需指定' in chat(f'训练标注：“{roots["训练标注"][0]}”')
    assert '还需指定' in chat(f'测试原图：“{roots["测试原图"][0]}”')
    assert '对，先检查' in chat(f'测试标注：“{roots["测试标注"][0]}”')
    assert '已取消' in chat('取消检查')
    assert pairing_intake.route(dialogue,owner,'对，先检查') is None


def test_recover_directory_roles_from_last_experiment_turn(tmp_path, application):
    dialogue = application.state.agent_tools.experiment_dialogue
    store = AgentStore(dialogue.database)
    owner = store.create_session()['id']
    roots = inputs(tmp_path)
    text = (f'ENVI 数据和 JSON 标注。训练数据：“{roots["训练原图"][0]}”，对应标注：“{roots["训练标注"][0]}”。'
            f'测试数据：“{roots["测试原图"][0]}”，对应标注：“{roots["测试标注"][0]}”')
    previous = store.new_round(owner, dialogue.capture(owner,text), [], 'running')
    store.save_answer(previous['id'],'请补充训练输入。')
    store.round_status(previous['id'],'done')
    def reply(message):
        events = list(machine_for(application,owner,ScriptedModel()).message(content=message))
        return events[-1][1].get('question') or events[-1][1]['content']
    assert '测试标注：S4' in reply('请检查之前给你的目录')
    assert '异常记录 0 条' in reply('按这个关系检查')
    assert '异常记录 0 条' in reply('请核对原图和标注。'+text)
