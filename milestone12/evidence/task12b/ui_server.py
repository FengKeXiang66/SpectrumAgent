"""Disposable UI adapter: real existing APIs and isolated test databases only."""
import importlib.util
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import sys

import numpy as np

ROOT = Path('E:/AI_Agent')
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from fastapi.testclient import TestClient
from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
from spectrumagent.annotation.projection_io import configure_project

spec = importlib.util.spec_from_file_location('task12b_case', ROOT / 'src-python/tests/annotation/conftest.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = ROOT / '.runtime/task12b' / ('ui-data-' + uuid4().hex)
root.mkdir()
cases = {}
events = []
snapshots = {}
for name in ('A', 'B', 'C'):
    directory = root / name
    directory.mkdir()
    c = module.annotation_case.__wrapped__(directory)
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    client = TestClient(app)
    client.__enter__()
    client.headers['Authorization'] = 'Bearer ' + identity.token
    base = '/api/v1/datasets/' + c.identifier
    assert client.post(base + '/superpixels', json={'n_segments': 24}).status_code == 200
    sessions = app.state.annotation_sessions
    rows = np.indices((40, 12))[0]
    sessions.edit(c.identifier, rows < 10, action='confirm', label_id=c.labels['PP'])
    configure_project(c.paths, c.project, {'PP': 'PP_W0'})
    if name != 'C':
        sessions.save(c.identifier)
        with connect_database(c.paths.database) as db:
            db.execute('UPDATE annotation_version SET created_at=? WHERE cube_id=?', ('2026-11-01 17:30', c.identifier))
    if name == 'A':
        sessions.edit(c.identifier, (rows >= 10) & (rows < 20), action='confirm', label_id=c.labels['PP'])
        sessions.edit(c.identifier, (rows >= 20) & (rows < 25), action='uncertain')
    cases[c.identifier] = SimpleNamespace(name=name, c=c, sessions=sessions, client=client, base=base,
                                         record=client.get(base).json())

def state(case):
    with connect_database(case.c.paths.database) as db:
        versions = [dict(zip(('id', 'version_no', 'created_at', 'labeled_pixels'), row)) for row in db.execute('SELECT id,version_no,created_at,labeled_pixels FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC', (case.c.identifier,))]
        row = db.execute('SELECT revision FROM annotation_draft WHERE cube_id=?', (case.c.identifier,)).fetchone()
    return {'revision': row[0] if row else 0, 'versions': versions, 'version_count': len(versions)}

def evidence():
    value = {'cases': {case.name: state(case) for case in cases.values()}, 'events': events, 'snapshots': snapshots}
    (ROOT / '.runtime/task12b/ui-evidence.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')
    return value

snapshots['initial'] = {case.name: state(case) for case in cases.values()}
evidence()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def respond(self, value, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    def do_GET(self):
        if self.path == '/fixture':
            return self.respond([{'name': case.name, 'record': case.record} for case in cases.values()])
        if self.path == '/evidence': return self.respond(evidence())
        folder = (ROOT / '.runtime/task12b/ui-dist').resolve()
        path = (folder / self.path.removeprefix('/ui/')).resolve()
        if not self.path.startswith('/ui/') or not path.is_relative_to(folder) or not path.is_file():
            return self.send_error(404)
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.end_headers()
        self.wfile.write(path.read_bytes())
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        command, args = body['command'], body.get('args', {})
        if command == 'test_snapshot':
            snapshots[args['tag']] = {case.name: state(case) for case in cases.values()}
            evidence()
            return self.respond(snapshots[args['tag']])
        if command == 'test_external_overwrite':
            case = cases[args['id']]
            before = state(case)
            mask = np.zeros((40, 12), dtype=bool)
            mask[30, 0] = True
            case.sessions.edit(case.c.identifier, mask, action='uncertain')
            response = case.client.post(case.base + '/annotations/save', json={'overwrite': True, 'confirm': True})
            assert response.status_code == 200, response.text
            event = {'kind': 'external_overwrite', 'case': case.name, 'before': before, 'after': state(case)}
            events.append(event)
            evidence()
            return self.respond(event)
        if command == 'datasets_test_preview':
            case = cases[args['id']]
            response = case.client.get(case.base + '/preview', params={'band': 0, 'size': 'full'})
        elif command == 'annotations_draft_forward':
            case = cases[args['request']['cube_id']]
            response = case.client.get('/api/v1/annotations/' + case.c.identifier + '/draft')
        else:
            request = args['request']
            op = request['op']
            if op == 'projects':
                return self.respond([project for case in cases.values() for project in case.client.get('/api/v1/projects').json()])
            case = next(case for case in cases.values() if case.c.project == request['project_id']) if op == 'labels' else cases.get(request.get('id'), next(iter(cases.values())))
            if op == 'catalog': response = case.client.get('/api/v1/catalog/plastic')
            elif op == 'labels': response = case.client.get('/api/v1/labels', params={'project_id': request['project_id']})
            elif op == 'versions': response = case.client.get(case.base + '/annotations')
            elif op == 'working': response = case.client.get(case.base + '/annotations/working')
            elif op in ('save', 'regions', 'undo', 'validate', 'superpixels'):
                before = state(case)
                payload = {key: value for key, value in request.items() if key not in ('op', 'id')}
                endpoint = case.base + ('/superpixels' if op == 'superpixels' else '/annotations/' + op)
                response = case.client.post(endpoint, **({'json': payload} if op in ('save', 'regions', 'superpixels') else {}))
                if op in ('save', 'undo'):
                    events.append({'kind': op, 'case': case.name, 'payload': payload, 'before': before, 'after': state(case)})
                    evidence()
            else: raise ValueError(op)
        self.respond(response.json(), response.status_code)

print(json.dumps({'port': 1426, 'data_root': str(root)}, ensure_ascii=False), flush=True)
try: HTTPServer(('127.0.0.1', 1426), Handler).serve_forever()
finally:
    for case in cases.values(): case.client.__exit__(None, None, None)
