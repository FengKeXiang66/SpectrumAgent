"""TASK-17 isolated browser acceptance bridge; never connects to the live app.

Run after npm run build: .venv/Scripts/python.exe milestone17/evidence/browser_server.py
Read-only real PE source cubes, separate runtime database, real API GETs.
No model calls or annotation edits. Engine status / navigation events are fixtures.
"""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from fastapi.testclient import TestClient
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app

PORT = 1427
run_dir = ROOT / '.runtime' / 'task17' / ('browser-' + uuid4().hex)
paths = AppPaths(run_dir)
identity = EngineIdentity()
app = create_app(paths, identity)
client = TestClient(app)
client.__enter__()
client.headers['Authorization'] = 'Bearer ' + identity.token
sources = [Path('E:/高光谱数据集/plastic/pe') / f'{name}.hdr'
           for name in ('20260804205214_64', '20260804205217_70')]
records = []
for source in sources:
    assert source.is_file(), source
    response = client.post('/api/v1/datasets/import', json={'path': str(source), 'raw': False})
    assert response.status_code == 200, response.text
    records.append(response.json()['datasets'][0])
requests = []
responses = []


def snapshot(phase):
    assert phase in ('Starting', 'Ready', 'Failed', 'Stopping')
    return {'generation_id': 1, 'phase': phase, 'pid': os.getpid(), 'port': PORT,
            'boot_id': str(identity.boot_id), 'cleanup_complete': True,
            'failure': {'kind': 'SpawnFailed', 'exit_reason': 'WorkerUnavailable', 'engine_error': None,
                        'handshake_path': str(run_dir / 'handshake.json'),
                        'log_path': str(paths.logs), 'data_directory': str(run_dir)} if phase == 'Failed' else None}


def forward(command, args, phase):
    if command == 'engine_status': return snapshot(phase), 200
    if command == 'plugin:dialog|open': return [str(source) for source in sources], 200
    request = args.get('request', {})
    op = request.get('op')
    requests.append({'command': command, 'op': op, 'id': request.get('id', request.get('cube_id'))})
    if command == 'datasets_forward':
        if op == 'import':
            assert request['path'] in [str(source) for source in sources]
            response = client.post('/api/v1/datasets/import', json={'path': request['path'], 'raw': request['raw']})
        elif op == 'get': response = client.get('/api/v1/datasets/' + request['id'])
        elif op == 'preview': response = client.get('/api/v1/datasets/' + request['id'] + '/preview',
                                                   params={k: v for k, v in request.items() if k not in ('op', 'id')})
        else: raise ValueError(request)
    elif command == 'annotations_forward':
        if op == 'projects': response = client.get('/api/v1/projects')
        elif op == 'catalog': response = client.get('/api/v1/catalog/plastic')
        elif op == 'labels': response = client.get('/api/v1/labels', params={'project_id': request['project_id']})
        elif op == 'working': response = client.get('/api/v1/datasets/' + request['id'] + '/annotations/working')
        elif op == 'versions': response = client.get('/api/v1/datasets/' + request['id'] + '/annotations')
        else: raise ValueError('Annotation writes are excluded from this smoke: ' + str(request))
    elif command == 'annotations_draft_forward':
        assert op == 'get_draft'
        response = client.get('/api/v1/annotations/' + request['cube_id'] + '/draft')
    elif command == 'preprocess_forward':
        if op == 'list_recipes': response = client.get('/api/v1/preprocess/recipes')
        elif op == 'list_runs': response = client.get('/api/v1/datasets/' + request['dataset_id'] + '/preprocess/runs')
        elif op == 'list_project_recipes': response = client.get('/api/v1/preprocess/projects/' + request['project_id'] + '/recipes')
        else: raise ValueError(request)
    elif command == 'models_forward':
        if op == 'list_runs': response = client.get('/api/v1/models/runs')
        elif op == 'list_targets': response = client.get('/api/v1/models/sample-targets', params={'project_id': request['project_id']})
        else: raise ValueError(request)
    elif command == 'settings_forward':
        assert op == 'get_llm'
        response = client.get('/api/v1/settings/llm')
    elif command == 'agent_forward':
        if op == 'get_runtime': response = client.get('/api/v1/agent/runtime')
        elif op == 'create_session': return {'id': 'task17-isolated-navigation'}, 200
        elif op == 'send_message':
            # Deterministic events exercise the real AssistantBar -> App route.
            content = request['body']['content']
            _, stage, number = content.split()
            record = records[int(number) - 1]
            data = {'cube_id': record['id'], 'display_name': record.get('display_name', record['dataset']['name'])}
            if stage != 'none': data['stage'] = stage
            return {'events': [{'event': 'workspace', 'data': data},
                               {'event': 'done', 'data': {'content': 'TASK17 本地导航事件已交付。', 'step_count': 0}}]}, 200
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
            return self.respond({'records': records, 'runtime': str(run_dir), 'requests': requests, 'responses': responses})
        if route == '/favicon.ico':
            self.send_response(204); self.end_headers(); return
        folder = ROOT / 'dist'
        if route == '/tauri-shim.js': path = ROOT / 'milestone17/evidence/tauri-shim.js'
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
            value, status = forward(body['command'], body.get('args', {}), body.get('phase', 'Ready'))
        except Exception as error:
            print(type(error).__name__, str(error), flush=True)
            value, status = {'detail': str(error)}, 500
        responses.append({'command': body['command'], 'op': body.get('args', {}).get('request', {}).get('op'), 'status': status})
        self.respond(value, status)


print(json.dumps({'url': f'http://127.0.0.1:{PORT}', 'runtime': str(run_dir),
                  'source_count': len(sources), 'mode': 'production frontend + isolated real API + controlled engine/navigation IPC'}, ensure_ascii=False), flush=True)
try: ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
finally: client.__exit__(None, None, None)
