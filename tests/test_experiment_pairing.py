"""Directory pairing is local and never assigns a sample to a new split."""
import json
from uuid import uuid4
from fastapi.testclient import TestClient

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
