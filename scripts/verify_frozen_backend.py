"""Exercise the frozen Windows engine through its loopback API in an isolated data root."""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
SESSIONS = '/api/v1/agent/sessions'
SETTINGS = '/api/v1/settings/llm'


@contextmanager
def inference_provider():
    """A loopback-only fixture for the router and inference tool call."""
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == '/v1/chat/completions'
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if request['model'] == 'smoke-router':
                assert not request.get('tools')
                answer = {'content': json.dumps({'intent': 'inference', 'explain_result': False, 'confidence': 'high'})}
                finish = 'stop'
            else:
                name = 'sa_experiments__inference_update'
                assert name in {tool['function']['name'] for tool in request['tools']}
                draft = next(json.loads(message['content'])['draft'] for message in request['messages']
                             if message['role'] == 'system' and message['content'].startswith('{"draft"'))
                patch = {
                    'expected_revision': draft['revision'],
                    'input': {
                        'kind': 'envi', 'source_refs': ['I1'], 'wavelength_unit': 'nm',
                        'mapping_window_nm': 5.0, 'nearest_tolerance_nm': 5.0,
                        'quality': {'min_mean': 0.0, 'min_std': 0.0, 'max_zero_fraction': 1.0, 'saturation': None},
                        'foreground': {'mode': 'none'},
                    },
                }
                answer = {'tool_calls': [{'index': 0, 'id': 'smoke-inference', 'type': 'function',
                                          'function': {'name': name, 'arguments': json.dumps(patch)}}]}
                finish = 'tool_calls'
            if request['stream']:
                payload = {'choices': [{'index': 0, 'delta': answer, 'finish_reason': finish}]}
                message = ('data: ' + json.dumps(payload) + '\n\ndata: [DONE]\n\n').encode()
                content_type = 'text/event-stream'
            else:
                message = json.dumps({'choices': [{'message': answer, 'finish_reason': finish}]}).encode()
                content_type = 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(message)))
            self.end_headers()
            self.wfile.write(message)

        def log_message(self, *_):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/v1'
        finally:
            server.shutdown()
            worker.join()


def wait_for_task(request, url):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = request(url)
        if state['status'] not in {'queued', 'running'}:
            assert state['status'] == 'succeeded', state
            return
        time.sleep(0.05)
    raise TimeoutError(url)


def verify_sessions(request):
    owner, archived = (request(SESSIONS, {})['id'] for _ in range(2))
    def listed():
        return {item['id'] for item in request(SESSIONS + '?kind=global')['sessions']}
    assert owner != archived and {owner, archived} <= listed()
    receipt = request(f'{SESSIONS}/{archived}/archive', {})
    assert receipt['archived'] is True and receipt['session_id'] == archived
    assert owner in listed() and archived not in listed()
    return owner


def verify_inference(request, chat, owner, model, header, experiment_folder):
    with inference_provider() as base_url:
        request(SETTINGS, {'base_url': base_url, 'model': 'smoke-inference', 'router_model': 'smoke-router',
                           'timeout_ms': '10000'}, method='PUT')
        _, plan = chat(owner, f'使用模型 {model} 推理 ENVI "{header}"')
        assert '确认推理' in plan, plan
        identifier = chat(owner, '确认推理')[0]['inference_run_id']
        request(SETTINGS, {}, method='PUT')
    url = f'{SESSIONS}/{owner}/experiment-history/{model}/inferences/{identifier}'
    wait_for_task(request, url)
    result = request(url + '/result')
    assert result['kind'] == 'envi' and len(result['files']) == 1, result
    assert result['files'][0]['classified'] > 0
    assert request(url + '/report', {}) == {'ready': True}
    folder = experiment_folder / 'inferences' / identifier
    html = (folder / 'report.html').read_text('utf-8')
    assert header.name in html and '逐像元' in html and '准确率' not in html
    for name in ('0.png', '0_input.png'):
        assert name in html and (folder / name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def verify_study(request, chat, owner, model):
    preview, reply = chat(owner, f'基于此数据寻优 {model}')
    assert '确认寻优' in reply and preview.get('study_preview_id'), reply
    chat(owner, '调整寻优，折数 2，潜变量 1-2；预处理候选：原谱；归一化候选：无')
    identifier = chat(owner, '确认寻优')[0]['study_id']
    url = f'{SESSIONS}/{owner}/studies/{identifier}'
    wait_for_task(request, url)
    report = request(url + '/result')
    assert report['folds'] == 2 and report['group_count'] == 6, report
    assert report['recommended'] in {candidate['id'] for candidate in report['candidates'] if 'cv_f1' in candidate}


def verify_milp(chat, owner, source, header):
    images, labels = source / 'images', source / 'labels'
    images.mkdir()
    labels.mkdir()
    for index, label in enumerate(('PE', 'PE', 'PP', 'PP')):
        stem = f'group-{index}'
        copy = images / (stem + '.hdr')
        copy.write_bytes(header.read_bytes())
        copy.with_suffix('.img').write_bytes(header.with_suffix('.img').read_bytes())
        annotation = {'source_hdr': str(copy), 'sample_id': stem, 'imageWidth': 8, 'imageHeight': 8,
                      'shapes': [{'label': label, 'shape_type': 'rectangle', 'points': [[0, 0], [7, 7]]}]}
        (labels / (stem + '.json')).write_text(json.dumps(annotation), 'utf-8')
    _, reply = chat(owner, f'原图在“{images}”，标注在“{labels}”，帮我划分训练集和测试集。')
    assert '分组交叉 0' in reply, reply
    _, reply = chat(owner, '确认保存划分')
    assert '已保存逐图划分清单' in reply, reply


def verify_startup_log(path):
    stages = ('import_app', 'create_app', 'uvicorn_bind', 'publish_handshake')
    events = [json.loads(line) for line in path.read_text('utf-8', errors='replace').splitlines()
              if line.startswith('{') and '"startup_stage_' in line]
    expected = [(stage, f'startup_stage_{event}') for stage in stages for event in ('started', 'finished')]
    assert [(entry['stage'], entry['event']) for entry in events] == expected, events
    elapsed = {}
    for entry in events[1::2]:
        assert entry['status'] == 'ok' and entry['elapsed_ms'] >= 0, entry
        elapsed[entry['stage']] = entry['elapsed_ms']
    return elapsed


def verify(executable,output):
    output.mkdir(parents=True,exist_ok=False)
    env={**os.environ,'SPECTRUMAGENT_DATA_ROOT':str(output/'app'),
         'SPECTRUMAGENT_PERMANENT_ROOT':str(output/'app'), 'PYTHONIOENCODING':'utf-8'}
    checks={}
    for diagnostic in ('geotiff','worker'):
        result=subprocess.run([str(executable),'--selfcheck-'+diagnostic],env=env,capture_output=True,
                              text=True,encoding='utf-8',errors='replace',timeout=60)
        (output/(diagnostic+'.log')).write_text(result.stdout+result.stderr,'utf-8')
        assert result.returncode==0,(diagnostic,(result.stdout+result.stderr)[-2000:])
        checks[diagnostic]='passed'
    package=executable.parent/'_internal'/'spectrumagent'
    source_package = ROOT / 'src-python' / 'spectrumagent'
    resources = list(source_package.rglob('*.json'))
    assert any(original.name == 'plastic.json' for original in resources)
    for original in resources:
        assert (package/original.relative_to(source_package)).read_bytes()==original.read_bytes()
    checks['package_json']='passed'
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
        groups = {'objects': np.repeat(np.arange(6), 6)} if role == 'train' else {}
        np.savez(source/(role+'.npz'),X=X,y=y,wavelengths_nm=waves,**groups)
        rows[role]=(X,y)
    header=source/'tiny.hdr'
    envi.save_image(str(header),rng.uniform(.1,.8,(8,8,len(waves))).astype(np.float32),
                    metadata={'wavelength': waves.tolist(), 'wavelength units': 'Nanometers'}, ext='.img')
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
        def read_response(path, body=None, method=None):
            req=urllib.request.Request(f"http://127.0.0.1:{identity['port']}"+path,
                data=None if body is None else json.dumps(body).encode('utf-8'),
                headers={'Authorization':'Bearer '+identity['token'],'Content-Type':'application/json'}, method=method)
            try:
                with urllib.request.urlopen(req,timeout=90) as response:
                    return response.read().decode('utf-8')
            except urllib.error.HTTPError as error:
                raise RuntimeError(f'{path}: HTTP {error.code}: {error.read().decode("utf-8")}') from error

        def request(path, body=None, method=None):
            return json.loads(read_response(path, body, method))

        def chat(session, content):
            raw = read_response(f'{SESSIONS}/{session}/messages', {'content': content, 'request_id': str(uuid4())})
            summary, reply = {}, ''
            for block in raw.split('\n\n'):
                if not block.strip():
                    continue
                event, data = block.split('\n', 1)
                data = json.loads(data.removeprefix('data: '))
                assert event != 'event: error', data
                if event == 'event: step':
                    summary.update(data['result_summary'])
                elif event in {'event: done', 'event: clarify'}:
                    reply = data.get('content', data.get('question', ''))
            assert reply, raw
            return summary, reply

        assert request('/health')['boot_id'] == identity['boot_id']
        checks['startup_stage_ms'] = verify_startup_log(output / 'engine.log')
        checks['startup_logging'] = 'passed'
        assert request('/smoke')['bands'] == 8
        checks['deferred_smoke_sample'] = 'passed'
        owner = verify_sessions(request)
        checks['multi_session'] = 'passed'
        config={'name':'Frozen numerical check',**{role:{'kind':'npz','paths':[str(source/(role+'.npz'))],
            'spectra_key':'X','labels_key':'y','wavelengths_key':'wavelengths_nm','input_stage':'neighborhood_mean',
            'neighborhood':3,'evaluation_unit':'center_pixel'} for role in ('train','test')},
            'wavelengths_nm':waves.tolist(),'classes':{1:'A',2:'B'},'preprocessing':[{'op':'standard_scale'}],
            'model':{'n_components':2,'scale':False,'max_iter':1000},'test_usage':'independent_test'}
        config['train']['groups_key'] = 'objects'
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
        verify_inference(request, chat, owner, experiment['experiment_id'], header, folder)
        checks['frozen_envi_inference_and_offline_report'] = 'passed'
        verify_study(request, chat, owner, experiment['experiment_id'])
        checks['frozen_study'] = 'passed'
        verify_milp(chat, owner, source, header)
        checks['frozen_group_split_milp'] = 'passed'
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
