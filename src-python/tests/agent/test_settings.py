import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from backend.database import connect_database
from spectrumagent.agent import llm
from .conftest import MESSAGES, TOOLS, audit_rows, mock_client

import pytest


BASE = "/api/v1/settings/llm"


def test_get_put_empty_defaults_typed_configuration_and_identity(settings_api):
    c = settings_api
    llm.write_settings(c.database, llm.LLMSettings())
    response = c.client.get(BASE)
    assert response.json() == {**llm.LLMSettings().model_dump(), "has_key": False}
    assert response.headers["X-SpectrumAgent-Boot-Id"] == c.identity.boot_id
    assert response.headers["X-SpectrumAgent-Pid"] == str(c.identity.pid)
    updated = c.client.put(BASE, json={"base_url": "https://example.invalid/v1", "model": "test",
        "temperature": 0.5, "max_tokens": 256, "timeout_ms": 1000})
    assert updated.status_code == 200
    assert updated.json() == {"base_url": "https://example.invalid/v1", "model": "test", "temperature": "0.5",
        "max_tokens": "256", "timeout_ms": "1000", "has_key": False}
    assert c.client.get(BASE).json() == updated.json()
    with connect_database(c.database) as db:
        assert dict(db.execute("SELECT key,value FROM llm_settings")) == {k: v for k, v in updated.json().items() if k != "has_key"}


@pytest.mark.parametrize("method,path,body", [("get", BASE, None), ("put", BASE, {}), ("put", BASE + "/key", {"key": "untrusted"})])
def test_settings_requires_sidecar_identity_before_mutation(settings_api, method, path, body):
    c = settings_api
    before = llm.read_settings(c.database)
    response = c.client.request(method, path, json=body, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401 and "X-SpectrumAgent-Boot-Id" not in response.headers
    assert not llm.has_api_key() and llm.read_settings(c.database) == before


@pytest.mark.parametrize("body", [
    {"base_url": "ftp://example.invalid"}, {"base_url": "https://user:password@example.invalid"},
    {"base_url": "https://example.invalid?key=sensitive"}, {"max_tokens": -1}, {"max_tokens": True},
    {"max_tokens": 1.5}, {"timeout_ms": 0}, {"temperature": "nan"}, {"extra": "x"}, {"model": None},
])
def test_invalid_settings_do_not_write(settings_api, body):
    c = settings_api
    before = llm.read_settings(c.database)
    response = c.client.put(BASE, json=body)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"
    assert llm.read_settings(c.database) == before


def test_key_write_only_clear_and_validation_never_echoes_input(settings_api):
    c = settings_api
    key = "sk-" + uuid4().hex
    for body in ({"key": key}, {"api_key": key}, {"model": "test", "extra": key}):
        response = c.client.put(BASE, json=body)
        assert response.status_code == 400 and key not in response.text
    assert c.client.put(BASE + "/key", json={"key": key}).json() == {"has_key": True}
    assert c.client.get(BASE).json()["has_key"] is True
    assert key not in c.client.get(BASE).text
    for body in ({"key": key, "extra": key}, {"key": {"nested": key}}, {}):
        response = c.client.put(BASE + "/key", json=body)
        assert response.status_code == 400 and key not in response.text
    response = c.client.put(BASE + "/key", content='{"key":"' + key, headers={"Content-Type": "application/json"})
    assert response.status_code == 400 and key not in response.text
    assert c.client.put(BASE + "/key", json={"key": ""}).json() == {"has_key": False}


def test_key_never_persisted_full_flow_errors_logs_artifacts_exports_and_process_restart(settings_api, caplog, capsys):
    c = settings_api
    key = "sk-" + uuid4().hex  # Generated in memory; no credential literal fixture on disk.
    caplog.set_level(logging.DEBUG)
    responses = [c.client.put(BASE + "/key", json={"key": key}), c.client.get(BASE)]
    client, transport = mock_client(c)
    client.chat(MESSAGES, TOOLS)
    assert transport.call_args.args[0].headers["Authorization"] == "Bearer " + key
    # Provider/transport exceptions containing the secret must not leak to audit.
    for kind in ("http", "transport", "blocked"):
        def fail(request):
            if kind == "transport":
                import httpx
                raise httpx.ReadTimeout(key, request=request)
            import httpx
            return httpx.Response(500, text=key)
        failed, handler = mock_client(c, handler=fail)
        with pytest.raises(llm.LLMError):
            failed.chat([{"role": "user", "content": "private.img"}] if kind == "blocked" else MESSAGES, TOOLS)
        assert handler.call_count == (0 if kind == "blocked" else 1)
    assert [r["status"] for r in audit_rows(c)] == ["ok", "http_error", "transport_error", "blocked"]
    assert all(key not in response.text for response in responses)
    with connect_database(c.database) as db:
        assert key not in "\n".join(db.iterdump())
    for directory in (c.paths.logs, c.paths.root / "artifacts", c.paths.root / "exports"):
        directory.mkdir(exist_ok=True)
        for path in directory.rglob("*"):
            if path.is_file():
                assert key.encode() not in path.read_bytes()
    assert key not in caplog.text
    captured = capsys.readouterr()
    assert key not in captured.out + captured.err
    # A new interpreter is a real process restart, not create_app() in the same
    # process (which must retain the memory key).
    root = Path(__file__).resolve().parents[3]
    script = '''import json, sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.paths import AppPaths
from backend.identity import EngineIdentity
from spectrumagent.app import create_app
identity = EngineIdentity()
app = create_app(AppPaths(Path(sys.argv[1])), identity)
with TestClient(app) as client:
    print(json.dumps(client.get("/api/v1/settings/llm", headers={"Authorization": "Bearer " + identity.token}).json()))
'''
    restarted = subprocess.run([sys.executable, "-c", script, str(c.paths.root)], cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src-python")}, capture_output=True, text=True, check=True)
    assert json.loads(restarted.stdout) == {**c.settings.model_dump(), "has_key": False}
    assert key not in restarted.stdout + restarted.stderr
    assert llm.has_api_key()  # Parent process is still alive.
