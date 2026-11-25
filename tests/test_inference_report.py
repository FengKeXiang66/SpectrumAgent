"""Internal foreground bands, offline comparison and one-pass export integrity."""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import base64
import json
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from test_experiment_conversation import application, workspace
from spectrumagent.agent.state import AgentStore
from spectrumagent.data import DataError
from spectrumagent.experiments import inference_report
from spectrumagent.experiments.foreground_probe import suggest
from spectrumagent.experiments.inference import ENVIInference


def test_probe_ignores_bright_spectral_endpoints_on_conveyor(tmp_path):
    waves = np.arange(1100,1310,10,dtype=float)
    header = tmp_path/'conveyor.hdr'
    header.write_text('ENVI\nsamples=40\nlines=24\nbands=21\ninterleave=bip\ndata type=12\nbyte order=0\n'
                      'reflectance scale factor=10000\nwavelength units=nm\nwavelength={'
                      +','.join(map(str,waves))+'}\n',encoding='ascii')
    signal = np.full((24,40,21),200,dtype='<u2')
    signal[:,10:18,:] = 3500
    signal[:,22:24,[0,-1]] = 2800
    signal.tofile(header.with_suffix('.img'))
    assert np.median(signal[12,22,[0,10,20]])/10000 > .11
    config = ENVIInference(kind='envi',paths=[str(header)],wavelength_unit='nm',mapping_window_nm=10.,
                           nearest_tolerance_nm=5.,quality=dict(min_mean=0.,min_std=0.,
                                                               max_zero_fraction=1.,saturation=None))
    result = suggest(config, waves)
    bands = result['suggestion']['wavelengths_nm']
    assert len(bands)==6 and min(bands)>waves[0] and max(bands)<waves[-1]
    indices = [np.where(waves==wave)[0][0] for wave in bands]
    assert np.median(signal[12,22,indices])/10000 < .11
    image = np.asarray(Image.open(BytesIO(base64.b64decode(result['png_base64']))))
    assert np.all(image[:,22:24]==0)
    assert np.all(image[:,12]>0)


def test_backfill_report_matches_files_caches_and_exports_in_one_pass(application,tmp_path,monkeypatch):
    service = application.state.agent_tools.experiment_dialogue.inference.service
    model, run = str(uuid4()),str(uuid4())
    folder = service.folder(model,run).resolve()
    folder.mkdir(parents=True)
    root = tmp_path/'原图'
    group = root/'晚班'
    group.mkdir(parents=True)
    names = ['pe&物料.hdr','no-companion.hdr']
    sources = {}
    for name in names:
        path = group/name
        path.write_text('ENVI',encoding='utf8')
        sources[str(path)] = {'sha256':sha256(b'ENVI').hexdigest(),'size':4}
    image = Image.new('RGB',(4,6),(20,130,200))
    stem = Path(names[0]).stem
    for name in (stem+'.png',stem+'-染色.png',stem+'_标签.png',stem+'other.png','unrelated.png',stem+'.jpg'):
        image.save(group/name)
    (group/(stem+'-invalid.png')).write_text('<script>alert(1)</script>',encoding='ascii')
    originals = {path.name:sha256(path.read_bytes()).hexdigest() for path in group.iterdir()}

    serial = {
        'config.json':dict(model_id=model,input={'kind':'envi','paths':[str(root)],'foreground':{'mode':'none'}}),
        'sources.json':sources,
        'status.json':dict(run_id=run,model_id=model,started_at=1.,finished_at=2.,status='succeeded'),
    }
    for name,value in serial.items():
        (folder/name).write_text(json.dumps(value),encoding='utf8')
    for index in range(2):
        image.save(folder/f'{index}.png')
        image.save(folder/f'{index}_input.png')
        np.savez_compressed(folder/f'{index}.npz',prediction_map=np.ones((4,6)))
    artifacts = {path.name:{'sha256':sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
                 for path in folder.iterdir() if path.name!='status.json'}
    result = dict(kind='envi',model_id=model,run_id=run,model_sha256='a'*64,classes={'1':'PE','2':'PP'},
                  colors={'1':'#ff3e3e','2':'#26d14f'},artifacts=artifacts,
                  files=[dict(file_index=i,name=name,counts={'1':12,'2':8},classified=20,excluded=4,total=24,
                              exclusion_counts={'brightness':4}) for i,name in enumerate(names)])
    (folder/'result.json').write_text(json.dumps(result),encoding='utf8')
    assert service.result(model,run)['files'][0]['relative_path']=='晚班/'+names[0]
    assert not (folder/'report.html').exists()
    with ZipFile(BytesIO(service.export(model,run))) as archive:
        assert 'report.html' not in archive.namelist()
        assert archive.testzip() is None
    assert not (folder/'report.html').exists()
    owner = AgentStore(service.experiments.paths.database).create_session()['id']
    url = f'/api/v1/agent/sessions/{owner}/experiment-history/{model}/inferences/{run}/report'
    with TestClient(application) as client:
        assert client.post(url).status_code==401
        client.headers['Authorization']='Bearer '+application.state.testing_identity.token
        assert client.post(url).json()=={'ready':True}
    html = (folder/'report.html').read_text('utf8')
    assert 'pe&amp;物料' in html and str(root) not in html
    assert 'loading="lazy"' in html and '按目录统计的多数票' in html
    assert '未找到配套染色图' in html and '保留原图配色' in html
    assert '准确率' not in html
    assert {path.name for path in (folder/'companions/0').iterdir()}=={
        stem+'.png',stem+'-染色.png',stem+'_标签.png',stem+'.jpg'}
    assert not (folder/'companions/1').exists()
    assert {path.name:sha256(path.read_bytes()).hexdigest() for path in group.iterdir()}==originals

    def unexpected_rescan(*args,**kwargs):
        pytest.fail('cached report rescanned the source directory')
    monkeypatch.setattr(inference_report,'companion_artifacts',unexpected_rescan)
    opened = Counter()
    original_open = Path.open
    def track(path,*args,**kwargs):
        if path.is_relative_to(folder):
            opened[path.relative_to(folder).as_posix()] += 1
        return original_open(path,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'open',track)
        bundle = service.export(model,run)
    with ZipFile(BytesIO(bundle)) as archive:
        assert archive.getinfo('0.npz').compress_type==ZIP_STORED
        assert archive.getinfo('0.png').compress_type==ZIP_STORED
        assert archive.getinfo('config.json').compress_type==ZIP_DEFLATED
        assert archive.getinfo('report.html').compress_type==ZIP_DEFLATED
        assert archive.getinfo(f'companions/0/{stem}.jpg').compress_type==ZIP_STORED
        assert archive.read('report.html').decode()==html
        assert all(opened[name]==1 for name in archive.namelist())
    assert opened['status.json']==1
    target = folder/'0.png'
    data = target.read_bytes()
    target.write_bytes(data[:-1]+bytes([data[-1]^1]))
    with pytest.raises(DataError) as error:
        service.export(model,run)
    assert error.value.code=='INFERENCE_ARTIFACT_CHANGED'
    target.write_bytes(data)
    for name in ('../private.png','companions/0/../../private.png','companions/0/C:private.png'):
        with pytest.raises(DataError) as error:
            list(inference_report.export_paths(folder,[name]))
        assert error.value.code=='INFERENCE_ARTIFACT_CHANGED'
    (folder/'report.html').write_text('modified',encoding='utf8')
    with pytest.raises(DataError) as error:
        service.prepare_report(model,run)
    assert error.value.code=='INFERENCE_ARTIFACT_CHANGED'
