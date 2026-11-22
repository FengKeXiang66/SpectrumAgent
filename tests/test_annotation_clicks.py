"""Ordered block edits keep authoritative projections, undo and source guards."""
from pathlib import Path
import sys

import numpy as np
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]
from test_experiments import workspace


def test_block_clicks_project_once_preserve_undo_and_reject_changed_source(workspace,tmp_path,monkeypatch):
    from spectral.io import envi
    from backend.database import connect_database
    from backend.identity import EngineIdentity
    from spectrumagent.app import create_app
    from spectrumagent.annotation.labels import LabelStore,SimpleLabelRequest
    from spectrumagent.annotation.engines.superpixels import Parameters
    monkeypatch.setenv('SPECTRUMAGENT_PERMANENT_ROOT',str(workspace.root))
    identity=EngineIdentity();app=create_app(workspace,identity)
    source=tmp_path/'source';source.mkdir()
    envi.save_image(str(source/'cube.hdr'),np.random.default_rng(21).uniform(.1,.8,(24,32,8)).astype(np.float32),ext='.dat')
    registry=app.state.dataset_registry;sessions=app.state.annotation_sessions
    cube=str(registry.import_path(str(source/'cube.hdr')).datasets[0].id)
    with connect_database(workspace.database) as db:
        project=db.execute('SELECT project_id FROM dataset_registry WHERE id=?',(cube,)).fetchone()[0]
    labels=[LabelStore(workspace.database).add(SimpleLabelRequest(project_id=project,name=name,color_hex=color))
            for name,color in (('A','#3388cc'),('B','#22aa44'))]
    segmentation,_=app.state.segmentation_resources.prepare(cube,Parameters(n_segments=20,compactness=5))
    block_ids=np.unique(segmentation.segments).tolist()
    assert len(block_ids)>1
    original=sessions._working_snapshot;projections=[]
    def counted(identifier):
        projections.append(str(identifier));return original(identifier)
    monkeypatch.setattr(sessions,'_working_snapshot',counted)
    before=[]
    with TestClient(app,headers={'Authorization':'Bearer '+identity.token}) as client:
        prefix=f'/api/v1/datasets/{cube}/annotations'
        for index,action in enumerate(('confirm','confirm','uncertain','erase','confirm','confirm')):
            before.append(sessions._states[cube].label_map.copy())
            projections.clear()
            body={'geometry':{'superpixels':[block_ids[index%2]]},'action':action}
            if action=='confirm':body['label_id']=labels[index%2]['id']
            response=client.post(prefix+'/regions',json=body)
            assert response.status_code==200,response.text
            assert projections==[cube]  # The edit's exact snapshot is reused.
            posted=response.json();actual=client.get(prefix+'/working').json()
            assert posted=={key:value for key,value in actual.items() if key!='overlay'}
        assert len(sessions._states[cube].undo_stack)==len(before)
        for expected in reversed(before):
            assert client.post(prefix+'/undo').status_code==200
            np.testing.assert_array_equal(sessions._states[cube].label_map,expected)
        # Source changes between clicks still refuse stale superpixels; queuing
        # must never turn the fast stat signature into a long-lived identity.
        expected=sessions._states[cube].label_map.copy()
        data=source/'cube.dat';changed=bytearray(data.read_bytes());changed[-1]^=1;data.write_bytes(changed)
        rejected=client.post(prefix+'/regions',json={'geometry':{'superpixels':[block_ids[0]]},'action':'erase'})
        assert rejected.status_code>=400
        np.testing.assert_array_equal(sessions._states[cube].label_map,expected)
