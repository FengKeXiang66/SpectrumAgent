import hashlib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path('E:/AI_Agent')
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
import numpy as np
from fastapi.testclient import TestClient
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app

identity = EngineIdentity()
app = create_app(AppPaths(ROOT / '.runtime/task12' / ('browser-data-' + uuid4().hex)), identity)
client = TestClient(app)
client.__enter__()
client.headers['Authorization'] = 'Bearer ' + identity.token
cube = client.post('/api/v1/datasets/import', json={'path': 'E:/高光谱数据集/plastic/pe/20260804205214_64.hdr'}).json()['datasets'][0]['id']
base = '/api/v1/datasets/' + cube
report = client.post(base + '/superpixels', json={'n_segments': 800}).json()
assert 'segments_png' in report, report
state = app.state.annotation_sessions._state(cube)
labels = [label for schema in client.get('/api/v1/labels', params={'project_id': client.get(base + '/annotations/working').json()['project_id']}).json() for label in schema['labels']]
labels.sort(key=lambda label: (label['sort_order'], label['code']))
rng = np.random.default_rng(12)
probes = [[int(r), int(c), int(state.segments[r, c])] for r, c in zip(rng.integers(0, 231, 200), rng.integers(0, 640, 200))]
fixture = {'report': report, 'working': client.get(base + '/annotations/working').json(), 'labels': labels,
           'probes': probes, 'shape': [*state.segments.shape, 200]}
counts = {}
baseline = {}
def snapshot():
    current = app.state.annotation_sessions._state(cube)
    return {'revision': current.revision, 'sha256': hashlib.sha256(current.label_map.tobytes()).hexdigest(), 'counts': dict(counts)}
def reset():
    counts.clear()
    counts.update({'POST /regions': 0, 'GET /working': 0, 'png_base64': 0, 'segments_png': 0})
    baseline.clear()
    baseline.update(snapshot())
def collect(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('png_base64', 'segments_png'):
                counts[key] += 1
            collect(item)
    elif isinstance(value, list):
        for item in value:
            collect(item)
reset()
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_OPTIONS(self):
        self.send_response(204)
        self.headers_out()
        self.end_headers()
    def headers_out(self):
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:1421')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    def handle_request(self, method):
        if self.path == '/fixture':
            value = fixture
        elif self.path == '/snapshot':
            value = {**snapshot(), 'baseline': baseline}
        elif self.path == '/reset':
            reset()
            value = snapshot()
        else:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))) or b'{}')
            suffix = {'/regions': '/annotations/regions', '/working': '/annotations/working', '/undo': '/annotations/undo'}[self.path]
            response = client.request(method, base + suffix, **({'json': body} if method == 'POST' else {}))
            assert response.status_code == 200, response.text
            value = response.json()
            if self.path in ('/regions', '/working'):
                counts[method + ' ' + self.path] += 1
                collect(value)
        self.send_response(200)
        self.headers_out()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    def do_GET(self):
        if self.path.startswith('/ui/'):
            folder = (ROOT / '.runtime/task12/browser-dist').resolve()
            path = (folder / self.path.removeprefix('/ui/')).resolve()
            if not path.is_relative_to(folder) or not path.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.end_headers()
            self.wfile.write(path.read_bytes())
            return
        if self.path not in ('/fixture', '/snapshot', '/working'):
            self.send_error(404)
            return
        self.handle_request('GET')
    def do_POST(self):
        self.handle_request('POST')
print(json.dumps({'blocks': report['superpixel_count'], 'shape': report['segments_shape'], 'base64_bytes': len(report['segments_png'])}), flush=True)
try:
    HTTPServer(('127.0.0.1', 1422), Handler).serve_forever()
finally:
    client.__exit__(None, None, None)
