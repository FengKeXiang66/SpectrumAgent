"""G1 fixtures: isolated SQLite, process credentials, synthetic HTTP only."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.database import connect_database
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.agent import llm
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.app import create_app


MESSAGES = [{"role": "user", "content": "数据集 cube-1，类 PP，指标 0.75，请选择工具。"}]
TOOLS = [{"type": "function", "function": {"name": "datasets.describe", "parameters": {
    "type": "object", "properties": {"dataset_id": {"type": "string"}}, "required": ["dataset_id"]}}}]
# Synthetic provider fixture. total deliberately differs from the two-item sum.
BODY = {"choices": [{"message": {"content": None, "tool_calls": [{"id": "call-1", "type": "function",
    "function": {"name": "datasets.describe", "arguments": '{"dataset_id":"cube-1"}'}}]},
    "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 17, "completion_tokens": 8, "total_tokens": 29}}


@pytest.fixture(autouse=True)
def isolated_key(monkeypatch):
    monkeypatch.setattr(llm, "_credentials", llm._Credentials())


@pytest.fixture
def gateway_case(tmp_path):
    paths = AppPaths(tmp_path)
    DatasetRegistry(paths.database)
    settings = llm.LLMSettings(base_url="https://provider.invalid/v1", model="mock-model",
                               temperature="0.25", max_tokens="128", timeout_ms="2500")
    llm.write_settings(paths.database, settings)
    return SimpleNamespace(paths=paths, database=paths.database, settings=settings)


@pytest.fixture
def settings_api(gateway_case):
    c = gateway_case
    identity = EngineIdentity()
    c.app = create_app(c.paths, identity)
    with TestClient(c.app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        c.client, c.identity = client, identity
        yield c


def mock_client(case, body=BODY, *, handler=None, session_id=None):
    handler = Mock(side_effect=handler) if handler else Mock(return_value=httpx.Response(200, json=body))
    client = llm.OpenAICompatibleClient(case.database, transport=httpx.MockTransport(handler), session_id=session_id)
    return client, handler


def audit_rows(case):
    with connect_database(case.database) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(llm_call)")]
        return [dict(zip(columns, row)) for row in db.execute("SELECT * FROM llm_call ORDER BY rowid")]
