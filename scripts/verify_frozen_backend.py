"""Exercise real onedir imports, numerical outputs, PNG reports and package JSON."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]


def verify(executable,output):
    output.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'SPECTRUMAGENT_DATA_ROOT':str(output/'app'),
         'SPECTRUMAGENT_PERMANENT_ROOT':str(output/'app')}
    checks={}
    for diagnostic in ('geotiff','worker'):
        result=subprocess.run([str(executable),'--selfcheck-'+diagnostic],env=env,capture_output=True,text=True,encoding='utf-8',timeout=60)
        (output/(diagnostic+'.log')).write_text(result.stdout+result.stderr,'utf-8')
        assert result.returncode==0,(diagnostic,result.stderr[-2000:])
        checks[diagnostic]='passed'
    package=executable.parent/'_internal'/'spectrumagent'
    for original in (ROOT/'src-python'/'spectrumagent').rglob('*.json'):
        assert (package/original.relative_to(ROOT/'src-python'/'spectrumagent')).read_bytes()==original.read_bytes()
    checks['package_json']='identical'
    import numpy as np
    from spectral.io import envi
    from sklearn.cross_decomposition import PLSRegression
    from sklearn.preprocessing import StandardScaler
    source=output/'source';source.mkdir()
    waves=np.arange(1100,1145,5,dtype=float)
    rng=np.random.default_rng(123)
    rows={}
    for role,count in (('train',36),('test',18)):
        X=rng.normal(size=(count,len(waves)))+(0 if role=='train' else 20)
        y=np.tile([1,2],count//2)
        np.savez(source/(role+'.npz'),X=X,y=y,wavelengths_nm=waves)
        rows[role]=(X,y)
    header=source/'tiny.hdr'
    envi.save_image(str(header),rng.uniform(.1,.8,(8,8,8)).astype(np.float32),ext='.dat')
    log=(output/'engine.log').open('w',encoding='utf-8')
    started=time.perf_counter()
    process=subprocess.Popen([str(executable)],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        handshake=output/'app'/'run'/'handshake.json'
        deadline=time.perf_counter()+45
        while not handshake.exists():
            assert process.poll() is None,'frozen engine exited before handshake'
            if time.perf_counter()>deadline:raise TimeoutError('frozen handshake')
            time.sleep(.05)
        checks['fresh_process_ready_s']=time.perf_counter()-started
        identity=json.loads(handshake.read_text('utf-8'))
        def request(path,body=None):
            req=urllib.request.Request(f"http://127.0.0.1:{identity['port']}"+path,
                data=None if body is None else json.dumps(body).encode('utf-8'),
                headers={'Authorization':'Bearer '+identity['token'],'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=90) as response:return json.loads(response.read())
        config={'name':'Frozen numerical check',**{role:{'kind':'npz','paths':[str(source/(role+'.npz'))],
            'spectra_key':'X','labels_key':'y','wavelengths_key':'wavelengths_nm','input_stage':'spectra',
            'neighborhood':1,'evaluation_unit':'spectrum'} for role in ('train','test')},
            'wavelengths_nm':waves.tolist(),'classes':{1:'A',2:'B'},'preprocessing':[{'op':'standard_scale'}],
            'model':{'n_components':2,'scale':False,'max_iter':1000},'test_usage':'independent_test'}
        experiment=request('/api/v1/experiments/run',config)
        assert experiment['status']=='succeeded'
        model=PLSRegression(n_components=2,scale=False,max_iter=1000)
        scaler=StandardScaler().fit(rows['train'][0])
        model.fit(scaler.transform(rows['train'][0]),(rows['train'][1][:,None]==[1,2]).astype(float))
        expected=model.predict(scaler.transform(rows['test'][0]))
        folder=output/'app'/'experiments'/experiment['experiment_id']
        with np.load(folder/'test_predictions.npz') as archive:
            np.testing.assert_allclose(archive['responses'],expected,rtol=1e-12,atol=1e-12)
        assert (folder/'report.html').is_file() and list(folder.glob('*.png'))
        checks['frozen_pls_and_png_report']='passed'
        imported=request('/api/v1/datasets/import',{'path':str(header)})
        cube=imported['datasets'][0]['id']
        prepared=request(f'/api/v1/datasets/{cube}/superpixels',{'n_segments':8,'compactness':.5,'pca_components':5})
        assert prepared['superpixel_count']>0
        checks['frozen_pca_slic']='passed'
    finally:
        process.terminate()
        try:process.wait(10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
    checks['payload_bytes']=sum(p.stat().st_size for p in executable.parent.rglob('*') if p.is_file())
    (output/'checks.json').write_text(json.dumps(checks,indent=2),'utf-8')
    print(json.dumps(checks),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('executable',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();verify(args.executable.resolve(),args.output.resolve())
