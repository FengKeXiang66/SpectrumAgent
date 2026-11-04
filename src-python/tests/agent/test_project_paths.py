"""TASK-25 C: configuration persists without activating either configured path."""
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from backend.database import connect_database
from spectrumagent.agent import llm
from cubes import cube
from .conftest import mock_client


def endpoint(case):
    project = case.client.get('/api/v1/projects').json()[0]['id']
    return project, f'/api/v1/settings/projects/{project}/paths'


def test_paths_defaults_round_trip_empty_values_identity_and_explicit_columns(settings_api):
    c = settings_api
    project, url = endpoint(c)
    response = c.client.get(url)
    expected = dict(source_path='', output_root='', data_root=str(c.paths.root), output_enabled=False)
    assert response.status_code == 200 and response.json() == expected
    assert response.headers['X-SpectrumAgent-Boot-Id'] == c.identity.boot_id
    assert response.headers['X-SpectrumAgent-Pid'] == str(c.identity.pid)
    values = dict(source_path=r'\\offline-nas\spectral\只读源', output_root=r'Z:\future-output')
    saved = c.client.put(url, json=values)
    assert saved.status_code == 200 and saved.json() == {**expected, **values}
    assert c.client.get(url).json() == saved.json()
    with connect_database(c.database) as db:
        row = db.execute('SELECT project_id,source_path,output_root,updated_at FROM project_path_settings').fetchone()
        assert row[:3] == (project, values['source_path'], values['output_root'])
        assert datetime.fromisoformat(row[3]).tzinfo is not None
        columns = db.execute('PRAGMA table_info(project_path_settings)').fetchall()
        assert [column[1] for column in columns] == ['project_id', 'source_path', 'output_root', 'updated_at']
        assert all(column[4] is None for column in columns)  # No DEFAULT supplying missing writes.
        assert ('project', 'project_id', 'id') in {(row[2], row[3], row[4]) for row in db.execute('PRAGMA foreign_key_list(project_path_settings)')}
    assert c.client.put(url, json=dict(source_path='', output_root='')).json() == expected


@pytest.mark.parametrize('body', [
    {}, {'source_path': ''}, {'source_path': None, 'output_root': ''}, {'source_path': '', 'output_root': 1},
    {'source_path': '', 'output_root': '', 'output_enabled': True},
    {'source_path': '', 'output_root': '', 'data_root': 'private'},
    {'source_path': '', 'output_root': '', 'project_id': 'private'},
])
def test_paths_unknown_fields_null_and_non_strings_fail_without_mutation_or_echo(settings_api, body):
    c = settings_api
    _, url = endpoint(c)
    before = c.client.get(url).json()
    response = c.client.put(url, json=body)
    assert response.status_code == 400 and response.json()['error'] == 'INVALID_REQUEST'
    assert 'private' not in response.text
    assert c.client.get(url).json() == before


@pytest.mark.parametrize('identifier,status', [('invalid-id', 400), (str(uuid4()), 404)])
@pytest.mark.parametrize('method', ['get', 'put'])
def test_paths_invalid_or_unknown_project_is_rejected(settings_api, identifier, status, method):
    c = settings_api
    response = c.client.request(method, f'/api/v1/settings/projects/{identifier}/paths',
                                **({'json': {'source_path': '', 'output_root': ''}} if method == 'put' else {}))
    assert response.status_code == status
    with connect_database(c.database) as db:
        assert db.execute('SELECT count(*) FROM project_path_settings').fetchone()[0] == 0


def test_smb_normalizes_strings_without_connectivity_checks_or_credentials_echo(settings_api):
    c = settings_api
    _, url = endpoint(c)
    response = c.client.put(url, json={'source_path': 'smb://offline-nas/share/批次%201', 'output_root': 'smb://offline-nas/out/future'})
    assert response.status_code == 200
    assert response.json()['source_path'] == '\\\\offline-nas\\share\\批次 1'
    assert response.json()['output_root'] == '\\\\offline-nas\\out\\future'
    for path in ('smb://user:private-password@offline-nas/share', 'smb://offline-nas', 'smb://offline-nas/share/../other'):
        rejected = c.client.put(url, json={'source_path': path, 'output_root': ''})
        assert rejected.status_code == 400
        assert path not in rejected.text and 'private-password' not in rejected.text


def test_saving_paths_does_not_change_payload_sources_files_or_guard_roots(settings_api, tmp_path):
    c = settings_api
    header, _, _ = cube(tmp_path / 'source')
    c.app.state.dataset_registry.import_path(str(header), raw=True)
    before = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
              for p in header.parent.iterdir() if p.is_file()}
    with connect_database(c.database) as db:
        payloads = db.execute('SELECT id,payload FROM dataset_registry ORDER BY id').fetchall()
        llm_settings = db.execute('SELECT key,value FROM llm_settings ORDER BY key').fetchall()
    _, url = endpoint(c)
    output = tmp_path / 'future-output-not-created'
    response = c.client.put(url, json={'source_path': str(header.parent), 'output_root': str(output)})
    assert response.status_code == 200
    assert response.json()['output_enabled'] is False and response.json()['data_root'] == str(c.paths.root)
    assert not output.exists()
    assert before == {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                      for p in header.parent.iterdir() if p.is_file()}
    with connect_database(c.database) as db:
        assert db.execute('SELECT id,payload FROM dataset_registry ORDER BY id').fetchall() == payloads
        assert db.execute('SELECT key,value FROM llm_settings ORDER BY key').fetchall() == llm_settings
    assert c.app.state.dataset_registry.storage_guard.output_root is None


def test_paths_survive_real_engine_process_restart(settings_api):
    c = settings_api
    project, url = endpoint(c)
    expected = c.client.put(url, json={'source_path': r'\\offline-nas\share', 'output_root': 'R:\\future'}).json()
    root = Path(__file__).resolve().parents[3]
    script = '''import json,sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.paths import AppPaths
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
identity=EngineIdentity()
app=create_app(AppPaths(Path(sys.argv[1])),identity)
with TestClient(app) as client:
    response=client.get('/api/v1/settings/projects/'+sys.argv[2]+'/paths',headers={'Authorization':'Bearer '+identity.token})
    assert response.status_code==200
    print(json.dumps(response.json()))
'''
    restarted = subprocess.run([sys.executable, '-c', script, str(c.paths.root), project], cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root / 'src-python')}, capture_output=True, text=True, check=True)
    assert json.loads(restarted.stdout) == expected


def test_paths_absent_from_logs_tools_and_real_llm_wire_body(settings_api, caplog, capsys):
    c = settings_api
    _, url = endpoint(c)
    values = {'source_path': r'\\private-nas-2531\private-source-2531', 'output_root': r'\\private-nas-2531\private-output-2531'}
    caplog.set_level(logging.DEBUG)
    assert c.client.put(url, json=values).status_code == 200
    registry = c.app.state.agent_tools
    summary = registry.invoke('datasets.list', {})
    assert all(value is None or type(value) in (str, int, float, bool) for value in summary.values())
    tools = registry.snapshot()
    assert not any('project_paths' in tool['function']['name'] or 'datasets.delete' == tool['function']['name'] for tool in tools)
    client, transport = mock_client(c)
    client.chat([{'role': 'user', 'content': json.dumps(summary)}], tools)
    body = transport.call_args.args[0].content.decode()
    captured = capsys.readouterr()
    for marker in ('private-nas-2531', 'private-source-2531', 'private-output-2531'):
        assert marker not in body + json.dumps(summary) + caplog.text + captured.out + captured.err
    denied, blocked = mock_client(c)
    with pytest.raises(llm.LLMError):
        denied.chat([{'role': 'user', 'content': values['source_path']}], tools)
    assert blocked.call_count == 0


def test_paths_require_authentication_before_saving(settings_api):
    c = settings_api
    _, url = endpoint(c)
    response = c.client.put(url, headers={'Authorization': 'Bearer wrong'}, json={'source_path': 'private', 'output_root': ''})
    assert response.status_code == 401 and 'X-SpectrumAgent-Boot-Id' not in response.headers
    with connect_database(c.database) as db:
        assert db.execute('SELECT count(*) FROM project_path_settings').fetchone()[0] == 0
