import importlib.util
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import mimetypes
from pathlib import Path
import sys
from uuid import uuid4, UUID

ROOT = Path('E:/AI_Agent')
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from fastapi.testclient import TestClient
from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.annotation import projection_io

spec = importlib.util.spec_from_file_location('task13_case', ROOT / 'src-python/tests/annotation/conftest.py')
fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)
directory = ROOT / '.runtime/task13' / ('ui-data-' + uuid4().hex); directory.mkdir()
case = fixtures.annotation_case.__wrapped__(directory)
identity = EngineIdentity(); app = create_app(case.paths, identity)
client = TestClient(app); client.__enter__(); client.headers['Authorization'] = 'Bearer ' + identity.token
base = '/api/v1/datasets/' + case.identifier
assert client.post(base + '/superpixels', json={'n_segments': 24}).status_code == 200
sessions = app.state.annotation_sessions
state = sessions._state(case.identifier)
sessions.edit(case.identifier, state.segments == 0, action='confirm', label_id=case.labels['PE'])
projection_io.configure_project(case.paths, case.project, {'PE': 'PE_W0'})
record = client.get(base).json()
failure = True
last_save = None
save_calls = []
folder_calls = []
original_write = projection_io.write_projection
def controlled(*args, **kwargs):
    if failure:
        raise OSError('模拟投影写入失败')
    return original_write(*args, **kwargs)
projection_io.write_projection = controlled

def evidence():
    with connect_database(case.paths.database) as db:
        count = db.execute('SELECT count(*) FROM annotation_version WHERE cube_id=?', (case.identifier,)).fetchone()[0]
    value = {'cube_id': case.identifier, 'save_calls': save_calls, 'version_count': count, 'last_save': last_save,
             'folder_calls': folder_calls, 'path_exists': bool(last_save and last_save['export']['path'] and Path(last_save['export']['path']).exists())}
    (ROOT / '.runtime/task13/ui-evidence.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    return value

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def respond(self, value, status=200):
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.end_headers()
        self.wfile.write(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    def do_GET(self):
        if self.path == '/fixture': return self.respond(record)
        if self.path == '/evidence': return self.respond(evidence())
        folder = (ROOT / '.runtime/task13/ui-dist').resolve()
        path = (folder / self.path.removeprefix('/ui/')).resolve()
        if not self.path.startswith('/ui/') or not path.is_relative_to(folder) or not path.is_file():
            return self.send_error(404)
        self.send_response(200); self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream'); self.end_headers()
        self.wfile.write(path.read_bytes())
    def do_POST(self):
        global failure, last_save
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/fail':
            failure = body['enabled']; return self.respond({'enabled': failure})
        command, args = body['command'], body.get('args', {})
        if command == 'open_exports_directory':
            folder = case.paths.exports / str(UUID(args['cubeId']))
            assert folder.is_dir(); folder_calls.append(str(folder)); return self.respond(None)
        if command == 'datasets_test_preview':
            response = client.get(base + '/preview', params={'band': 0, 'size': 'full'})
        elif command == 'annotations_draft_forward':
            response = client.get('/api/v1/annotations/' + args['request']['cube_id'] + '/draft')
        else:
            request = args['request']; op = request['op']
            if op == 'projects': response = client.get('/api/v1/projects')
            elif op == 'catalog': response = client.get('/api/v1/catalog/plastic')
            elif op == 'labels': response = client.get('/api/v1/labels', params={'project_id': request['project_id']})
            elif op == 'versions': response = client.get(base + '/annotations')
            elif op == 'working': response = client.get(base + '/annotations/working')
            elif op in ('save', 'regions', 'undo', 'validate', 'superpixels'):
                payload = {k: v for k, v in request.items() if k not in ('op', 'id')}
                endpoint = base + ('/superpixels' if op == 'superpixels' else '/annotations/' + op)
                response = client.post(endpoint, **({'json': payload} if op in ('save', 'regions', 'superpixels') else {}))
                if op == 'save' and response.status_code == 200:
                    value = response.json(); save_calls.append(payload)
                    last_save = {'id': value['id'], 'export': value['export']}; evidence()
            else: raise ValueError(op)
        self.respond(response.json(), response.status_code)

print(json.dumps({'cube_id': case.identifier, 'data_root': str(case.paths.root)}, ensure_ascii=False), flush=True)
try: HTTPServer(('127.0.0.1', 1424), Handler).serve_forever()
finally: client.__exit__(None, None, None)
