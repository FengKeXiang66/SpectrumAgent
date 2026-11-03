"""TASK-20 isolated browser acceptance bridge; never connects to the live app.

Run after npm run build: .venv/Scripts/python.exe milestone20/evidence/browser_server.py
Read-only real PE cubes plus 12 synthetic regression samples, separate runtime database, real API.
Real model training/read endpoints; isolated fixture snapshots only. No live annotation edits.
Engine phase is a controlled acceptance fixture. Regression inputs are synthetic test data.
"""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from fastapi.testclient import TestClient
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app

PORT = 1430
import importlib.util
fixture_dir = ROOT / '.runtime' / 'task20' / ('browser-' + uuid4().hex)
fixture_dir.mkdir(parents=True)
spec = importlib.util.spec_from_file_location('task20_fixtures', ROOT / 'src-python/tests/modeling/conftest.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
case = fixtures.regression_factory.__wrapped__(fixture_dir)(12)
paths = case.paths
run_dir = paths.root
identity = EngineIdentity()
app = create_app(paths, identity)
client = TestClient(app)
client.__enter__()
client.headers['Authorization'] = 'Bearer ' + identity.token
sources = [Path('E:/高光谱数据集/plastic/pe') / f'{name}.hdr'
           for name in ('20260804205214_64', '20260804205217_70')]
# Synthetic regression inputs use the repository's existing isolated test fixture.
# The UI still calls real training/run/sweep endpoints; no result is fabricated.
regression_sources = [Path(case.registry.get(cube)[0].header_path) for cube in case.cubes]
records = []
for source in sources:
    assert source.is_file(), source
    response = client.post('/api/v1/datasets/import', json={'path': str(source), 'raw': False})
    assert response.status_code == 200, response.text
    records.append(response.json()['datasets'][0])
response = client.post('/api/v1/models/sample-targets/import-csv', json={'project_id': case.project, 'csv_text': case.csv_text})
assert response.status_code == 200 and response.json()['imported'] == 12, response.text
# Populate a real run history through the unchanged model API.
training_results = []
for components in (1, 2, 3, 4):
    response = client.post('/api/v1/models/runs', json={
        'task': 'regression', 'preprocess_run_ids': case.runs, 'target_schema_id': case.schema,
        'cv_strategy': 'kfold', 'cv_folds': 3, 'test_ratio': 1/3, 'seed': 17, 'n_components': components})
    assert response.status_code == 200 and response.json()['status'] == 'succeeded', response.text
    training_results.append(response.json())
# A separate tiny sample has a real preprocess execution and real timestamps;
# it is not one of regression_factory's pre-inserted ready rows.
import shutil
import numpy as np
from backend.database import connect_database
from spectrumagent.preprocess.run import timestamp
source_header = Path(case.registry.get(case.cubes[0])[0].header_path)
ledger_header = fixture_dir / 'ledger-sample.hdr'
shutil.copyfile(source_header, ledger_header)
shutil.copyfile(source_header.with_suffix('.img'), ledger_header.with_suffix('.img'))
response = client.post('/api/v1/datasets/import', json={'path': str(ledger_header), 'raw': True})
assert response.status_code == 200, response.text
ledger_record = response.json()['datasets'][0]
ledger_cube = ledger_record['id']
ledger_version = str(uuid4())
folder = paths.snapshots / ledger_cube / 'v1'
folder.mkdir(parents=True)
source_snapshot = paths.snapshots / case.cubes[0] / 'v1'
for filename in ('label_map.npz', 'label_index.json'):
    shutil.copyfile(source_snapshot / filename, folder / filename)
with connect_database(paths.database) as db:
    db.execute("INSERT INTO annotation_version (id,cube_id,version_no,snapshot_ref,n_pixels,labeled_pixels,params,created_at) VALUES (?,?,1,?,6,5,'{}',?)", (ledger_version, ledger_cube, f'{ledger_cube}/v1', timestamp()))
recipe = case.runner.get(case.runs[0])['recipe_version_id']
response = client.post(f'/api/v1/datasets/{ledger_cube}/preprocess/runs', json={'annotation_version_id': ledger_version, 'recipe_version_id': recipe})
assert response.status_code == 200 and response.json()['status'] == 'succeeded', response.text
real_preprocess = response.json()
# A pending non-regression row checks the explicitly requested All/task filter.
with connect_database(paths.database) as db:
    fixtures.insert_run.__wrapped__()(db, identifier='p5-pending-classification')
empty_identity = EngineIdentity()
empty_client = TestClient(create_app(AppPaths(fixture_dir / 'empty'), empty_identity))
empty_client.__enter__()
empty_client.headers['Authorization'] = 'Bearer ' + empty_identity.token
requests = []
responses = []
sessions = []
messages = []
smoke_results = []


def snapshot(phase):
    assert phase in ('Starting', 'Ready', 'Failed', 'Stopping')
    return {'generation_id': 1, 'phase': phase, 'pid': os.getpid(), 'port': PORT,
            'boot_id': str(identity.boot_id), 'cleanup_complete': True,
            'failure': {'kind': 'SpawnFailed', 'exit_reason': 'WorkerUnavailable', 'engine_error': None,
                        'handshake_path': str(run_dir / 'handshake.json'),
                        'log_path': str(paths.logs), 'data_directory': str(run_dir)} if phase == 'Failed' else None}


def forward(command, args, phase, fixture):
    api_client = empty_client if fixture == 'empty' else client
    if command == 'engine_status': return snapshot(phase), 200
    if command == 'plugin:dialog|open': return [str(source) for source in sources], 200
    request = args.get('request', {})
    op = request.get('op')
    requests.append({'fixture': fixture, 'command': command, 'op': op, 'id': request.get('id', request.get('cube_id', request.get('dataset_id')))})
    if command == 'run_smoke':
        response = api_client.get('/smoke')
        smoke_results.append(response.json())
    elif command == 'datasets_forward':
        if op == 'import':
            assert request['path'] in [str(source) for source in sources + regression_sources]
            response = api_client.post('/api/v1/datasets/import', json={'path': request['path'], 'raw': request['raw']})
        elif op == 'get': response = api_client.get('/api/v1/datasets/' + request['id'])
        elif op == 'preview': response = api_client.get('/api/v1/datasets/' + request['id'] + '/preview',
                                                   params={k: v for k, v in request.items() if k not in ('op', 'id')})
        else: raise ValueError(request)
    elif command == 'annotations_forward':
        if op == 'projects': response = api_client.get('/api/v1/projects')
        elif op == 'catalog': response = api_client.get('/api/v1/catalog/plastic')
        elif op == 'labels': response = api_client.get('/api/v1/labels', params={'project_id': request['project_id']})
        elif op == 'working': response = api_client.get('/api/v1/datasets/' + request['id'] + '/annotations/working')
        elif op == 'versions': response = api_client.get('/api/v1/datasets/' + request['id'] + '/annotations')
        else: raise ValueError('Annotation writes are excluded from this smoke: ' + str(request))
    elif command == 'annotations_draft_forward':
        assert op == 'get_draft'
        response = api_client.get('/api/v1/annotations/' + request['cube_id'] + '/draft')
    elif command == 'preprocess_forward':
        if op == 'list_recipes': response = api_client.get('/api/v1/preprocess/recipes')
        elif op == 'list_runs': response = api_client.get('/api/v1/datasets/' + request['dataset_id'] + '/preprocess/runs')
        elif op == 'get_run': response = api_client.get('/api/v1/preprocess/runs/' + request['id'])
        elif op == 'list_project_recipes': response = api_client.get('/api/v1/preprocess/projects/' + request['project_id'] + '/recipes')
        else: raise ValueError(request)
    elif command == 'models_forward':
        if op == 'list_runs': response = api_client.get('/api/v1/models/runs')
        elif op == 'get_run': response = api_client.get('/api/v1/models/runs/' + request['id'])
        elif op == 'lv_sweep': response = api_client.get('/api/v1/models/runs/' + request['id'] + '/lv-sweep')
        elif op == 'list_targets': response = api_client.get('/api/v1/models/sample-targets', params={'project_id': request['project_id']})
        elif op == 'list_models': response = api_client.get('/api/v1/models/registry')
        elif op == 'create_run':
            response = api_client.post('/api/v1/models/runs', json=request['body'])
            training_results.append({'request': request['body'], 'response': response.json(), 'status': response.status_code})
        else: raise ValueError(request)
    elif command == 'settings_forward':
        assert op == 'get_llm'
        response = api_client.get('/api/v1/settings/llm')
    elif command == 'agent_forward':
        if op == 'get_runtime': response = api_client.get('/api/v1/agent/runtime')
        else: raise ValueError(request)
    else: raise ValueError(command)
    return response.json(), response.status_code


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def respond(self, value, status=200):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == '/__fixture':
            return self.respond({'records': records, 'runtime': str(run_dir), 'requests': requests, 'responses': responses,
                                 'sessions': sessions, 'messages': messages, 'smoke_results': smoke_results, 'training_results': training_results, 'ledger_record': ledger_record, 'real_preprocess': real_preprocess})
        if route == '/favicon.ico':
            self.send_response(204); self.end_headers(); return
        folder = ROOT / 'dist'
        if route == '/tauri-shim.js': path = ROOT / 'milestone20/evidence/tauri-shim.js'
        else:
            path = (folder / route.lstrip('/')).resolve() if route != '/' else folder / 'index.html'
            if not path.is_relative_to(folder.resolve()) or not path.is_file(): return self.send_error(404)
        data = path.read_bytes()
        if path.name == 'index.html':
            data = data.replace(b'<head>', b'<head><script src="/tauri-shim.js"></script>')
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        # Tauri's style-src is preserved. self permits only the local IPC bridge.
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; connect-src 'self'; style-src 'self'")
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != '/ipc': return self.send_error(404)
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        try:
            value, status = forward(body['command'], body.get('args', {}), body.get('phase', 'Ready'), body.get('fixture', 'populated'))
        except Exception as error:
            print(type(error).__name__, str(error), flush=True)
            value, status = {'detail': str(error)}, 500
        responses.append({'fixture': body.get('fixture', 'populated'), 'command': body['command'], 'op': body.get('args', {}).get('request', {}).get('op'), 'status': status})
        self.respond(value, status)


print(json.dumps({'url': f'http://127.0.0.1:{PORT}', 'runtime': str(run_dir), 'ledger_cube': ledger_cube, 'preprocess_created_at': real_preprocess['created_at'],
                  'source_count': len(sources), 'mode': 'production frontend + isolated real API + controlled engine/navigation IPC'}, ensure_ascii=False), flush=True)
try: ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
finally:
    client.__exit__(None, None, None)
    empty_client.__exit__(None, None, None)
