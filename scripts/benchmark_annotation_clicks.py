"""Real block edit protocol timings and byte comparisons; input files stay read-only."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def run(args):
    code=args.code_root or ROOT
    sys.path[:0]=[str(code),str(code/'src-python')]
    import structlog
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
    import numpy as np
    from fastapi.testclient import TestClient
    from threadpoolctl import threadpool_limits
    from backend.database import connect_database
    from backend.identity import EngineIdentity
    from backend.paths import AppPaths
    from spectrumagent.app import create_app
    from spectrumagent.annotation.labels import LabelStore,SimpleLabelRequest
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'temp').mkdir();tempfile.tempdir=str(args.output/'temp')
    os.environ['SPECTRUMAGENT_PERMANENT_ROOT']=str(args.output/'app')
    paths=AppPaths(args.output/'app');paths.create_directories()
    identity=EngineIdentity();app=create_app(paths,identity)
    record=app.state.dataset_registry.import_path(str(args.source)).datasets[0]
    cube=str(record.id);sessions=app.state.annotation_sessions
    with connect_database(paths.database) as db:
        project=db.execute('SELECT project_id FROM dataset_registry WHERE id=?',(cube,)).fetchone()[0]
    labels=[LabelStore(paths.database).add(SimpleLabelRequest(project_id=project,name=name,color_hex=color))
            for name,color in (('A','#3388cc'),('B','#22aa44'))]
    with threadpool_limits(limits=2):segmentation,_=app.state.segmentation_resources.prepare(cube)
    ids=np.unique(segmentation.segments).tolist()
    prefix=f'/api/v1/datasets/{cube}/annotations'
    digest=lambda value:hashlib.sha256(value.tobytes(order='C')).hexdigest()
    with TestClient(app,headers={'Authorization':'Bearer '+identity.token}) as client:
        def get(path,**kwargs):
            response=client.get(path,**kwargs);response.raise_for_status();return response.json()
        fixture={'record':record.model_dump(mode='json'),
                 'superpixels':get(f'/api/v1/datasets/{cube}/superpixels'),
                 'working':get(prefix+'/working'),
                 'labels':get('/api/v1/labels',params={'project_id':project}),
                 'projects':get('/api/v1/projects')}
        (args.output/'ui-fixture.json').write_text(json.dumps(fixture,ensure_ascii=False),'utf-8')
        step_maps=[];edits=[];gets=0;post_seconds=[]
        started=time.perf_counter()
        for index in range(12):
            action=('confirm','confirm','uncertain','erase')[index%4]
            body={'geometry':{'superpixels':[ids[index%len(ids)]]},'action':action}
            if action=='confirm':body['label_id']=labels[index%2]['id']
            tick=time.perf_counter();response=client.post(prefix+'/regions',json=body)
            response.raise_for_status();post_seconds.append(time.perf_counter()-tick)
            step_maps.append(digest(sessions._states[cube].label_map));edits.append(body)
            if args.refresh_every==1 or (index+1)%args.refresh_every==0 or index==11:
                get(prefix+'/working');gets+=1
        elapsed=time.perf_counter()-started
        state=sessions._states[cube]
        undo=[digest(array) for _,array in state.undo_stack]
        saved=sessions.save(cube);frozen=sessions.read_version(saved['id'])
        result={'shape':list(record.dataset.shape),'clicks':12,'post_requests':12,'working_gets':gets,
                'protocol_s':elapsed,'post_mean_s':sum(post_seconds)/len(post_seconds),
                'step_label_maps':step_maps,'undo_label_maps':undo,'label_map':digest(frozen['label_map']),
                'spectra':{key:digest(value) for key,value in frozen['spectra'].items()},
                'undo_steps':len(undo),'source_changed':False,
                'scope':'Real synchronous HTTP service timings; excludes Tauri IPC, user pacing and browser rendering.'}
        (args.output/'results.json').write_text(json.dumps(result,indent=2),'utf-8')
        print(json.dumps({key:value for key,value in result.items() if key not in ('step_label_maps','undo_label_maps','spectra')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--code-root',type=Path)
    parser.add_argument('--refresh-every',type=int,choices=(1,4),default=4)
    run(parser.parse_args())
