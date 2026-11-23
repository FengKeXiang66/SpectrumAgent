"""Compare original ENVI values in CSV order; a rejected replay must never publish a partial dataset."""
import csv
import json
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient


from test_experiment_conversation import application, workspace
from backend.database import connect_database
from spectrumagent.experiments.center_replay import AXIS, VERSION, replay, verified_output
from spectrumagent.experiments.inputs import sha256
from spectrumagent.data import DataError


def make_release(folder):
    pairs, hashes = [], {}
    for role, name in [('训练','训练光谱.npz'),('测试','测试V2光谱.npz')]:
        hdr = folder / (role+'.hdr')
        img = hdr.with_suffix('.img')
        annotation = hdr.with_suffix('.json')
        hdr.write_text('ENVI\nsamples=5\nlines=5\nbands=112\ndata type=12\ninterleave=bip\nbyte order=0\n'
                       'reflectance scale factor=10000\nwavelength units=nm\nwavelength={'+
                       ','.join(map(str,AXIS))+'}\n')
        rr, cc, bands = np.indices((5,5,112))
        cube = (1000 + rr*20 + cc*5 + bands*10).astype('<u2')
        img.write_bytes(cube.tobytes())
        annotation.write_text(json.dumps(dict(source_hdr=str(hdr),imageWidth=5,imageHeight=5,
            source_signature=dict(img_bytes=img.stat().st_size,img_path=str(img),hdr_sha256=sha256(hdr)),
            shapes=[dict(label='PE',shape_type='rectangle',points=[[0,0],[4,4]])])),encoding='utf-8')
        pairs.append(dict(role=role,hdr=str(hdr),img=str(img),annotation=str(annotation)))
        coordinates = [(3,3),(1,1)]
        centers = folder/(role+'中心.csv')
        with centers.open('w',encoding='utf-8',newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['source','row','col','region','label'])
            for r,c in coordinates:
                writer.writerow([str(hdr),r,c,1,1])
        reference = np.stack([cube[r,c].astype(float)/10000 for r,c in coordinates]).astype(np.float32)
        np.savez(folder/name,X3=reference,y=np.array([1,1]),wavelengths_nm=AXIS)
        for f in (annotation, centers, folder/name):
            hashes[f.name] = sha256(f)
    (folder/'版本清单.json').write_text(json.dumps(dict(version=VERSION,files=hashes)),encoding='utf-8')
    return dict(pairs=pairs,issues=[])


def test_replay_atomic_and_exact_in_original_order(tmp_path, application):
    release = tmp_path/'release'
    release.mkdir()
    report = make_release(release)
    output = application.state.experiments.paths.exports/'center-replays'
    run, stats = replay(report, release, output)
    assert stats['训练']['exact'] == stats['测试']['exact'] == 2
    assert verified_output(run/'训练光谱.npz',sha256(run/'训练光谱.npz')) == run.name
    with pytest.raises(DataError):
        verified_output(run/'训练光谱.npz','wrong')
    # Train succeeds, then the test reference disagrees in just one channel.
    name = '测试V2光谱.npz'
    with np.load(release/name) as archive:
        data = dict(archive)
    data['X3'][0,0] += .001
    np.savez(release/name,**data)
    manifest_path = release/'版本清单.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['files'][name] = sha256(release/name)
    manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match='1/2 条 X3'):
        replay(report,release,output)
    assert list(output.iterdir()) == [run]


def test_chat_handoff_uses_verified_output_and_requires_review(tmp_path, application):
    release = tmp_path/'release'
    release.mkdir()
    report = make_release(release)
    report['manifest_path'] = str(release/'来源与标注清单.csv')
    service = application.state.experiments
    with TestClient(application) as client:
        client.headers['Authorization'] = 'Bearer ' + application.state.testing_identity.token
        sid = client.post('/api/v1/agent/sessions', json={}).json()['id']
        def message(content):
            response = client.post(f'/api/v1/agent/sessions/{sid}/messages',
                                   json={'content':content,'request_id':str(uuid4())})
            assert response.status_code == 200
            return response.text
        assert '还没有配对预览' in message('核验中心取谱')
        with connect_database(service.paths.database) as db:
            db.execute('INSERT INTO experiment_pairing(session_id,report_json) VALUES (?,?)',
                       (sid,json.dumps(report)))
        assert 'prepare_training' in message('核验中心取谱')
        assert '确认执行' in message('用本次取谱结果新建训练方案')
        assert not list(service.root.iterdir())
        dialogue = application.state.agent_tools.experiment_dialogue
        config = dialogue._config(dialogue._read(sid))
        assert config.test_usage == 'development_regression'
        assert all(str(service.paths.exports) in spec.paths[0] for spec in (config.train, config.test))
