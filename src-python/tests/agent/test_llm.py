from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import logging
from unittest.mock import Mock

import httpx
import pytest

from backend.database import connect_database
from spectrumagent.agent import llm
from .conftest import BODY, MESSAGES, TOOLS, audit_rows, mock_client


def test_mock_chat_tool_calls_result_and_complete_audit(gateway_case, monkeypatch):
    c = gateway_case
    client, transport = mock_client(c)
    llm.set_api_key("synthetic-memory-key")
    ticks = iter([10_000_000, 47_900_000])  # Deterministic monotonic clock fixture.
    monkeypatch.setattr(llm, "perf_counter_ns", lambda: next(ticks))
    result = client.chat(MESSAGES, TOOLS)
    assert isinstance(client, llm.LLMClient)
    assert result.model_dump() == {"content": None, "tool_calls": [{"id": "call-1", "name": "datasets.describe",
        "arguments_json": '{"dataset_id":"cube-1"}'}], "usage": BODY["usage"], "finish_reason": "tool_calls"}
    transport.assert_called_once()
    request = transport.call_args.args[0]
    assert request.method == "POST" and str(request.url) == "https://provider.invalid/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer synthetic-memory-key"
    assert json.loads(request.content) == {"model": "mock-model", "messages": MESSAGES, "tools": TOOLS,
        "stream": False, "temperature": 0.25, "max_tokens": 128}
    assert request.extensions["timeout"] == dict.fromkeys(("connect", "read", "write", "pool"), 2.5)
    row, = audit_rows(c)
    assert row["session_id"] is None and row["model"] == "mock-model"
    canonical = json.dumps(MESSAGES, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert row["prompt_sha256"] == sha256(canonical.encode()).hexdigest()
    assert json.loads(row["tool_names"]) == ["datasets.describe"]
    assert [row[k] for k in BODY["usage"]] == [17, 8, 29]
    assert row["latency_ms"] == 37 and row["status"] == "ok" and row["error"] is None
    assert datetime.fromisoformat(row["created_at"]).tzinfo is not None
    assert "数据集" not in json.dumps(row, ensure_ascii=False)


@pytest.mark.parametrize("content", [
    "C:", "D:/private/cube", r"\\nas\share\cube", r"private\cube", "/nas/cube", "relative/cube",
    "./cube", "../cube", "cube.img", "CUBE.HDR", "training.MAT", "[[1,2],[3,4]]", "[ [1,2], [3,4]]",
    "label_map", {"points": [[1, 2], [3, 4]]}, {"label_map": [0, 1]},
])
def test_egress_blocked_before_any_transport_and_audited(gateway_case, content):
    client, transport = mock_client(gateway_case)
    with pytest.raises(llm.LLMError) as caught:
        client.chat([{"role": "user", "content": content}], TOOLS)
    assert caught.value.code == "EGRESS_BLOCKED" and caught.value.status == "blocked"
    transport.assert_not_called()
    row, = audit_rows(gateway_case)
    assert row["status"] == "blocked" and row["error"] == "EGRESS_BLOCKED"
    assert all(row[k] is None for k in ("prompt_tokens", "completion_tokens", "total_tokens"))


def test_tool_schema_scanned_and_multiline_unicode_text_allowed(gateway_case):
    client, transport = mock_client(gateway_case)
    tools = deepcopy(TOOLS)
    tools[0]["function"]["description"] = "example.img"
    with pytest.raises(llm.LLMError, match="EGRESS_BLOCKED"):
        client.chat(MESSAGES, tools)
    transport.assert_not_called()
    client.chat([{"role": "user", "content": "数据集 cube-1\n类 PP，指标 1.0"}], TOOLS)
    transport.assert_called_once()


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadError])
def test_transport_failures_distinguishable_no_silent_retry(gateway_case, failure):
    def failed(request):
        raise failure("sensitive exception text", request=request)
    client, transport = mock_client(gateway_case, handler=failed)
    with pytest.raises(llm.LLMError) as caught:
        client.chat(MESSAGES, TOOLS)
    assert caught.value.code == "LLM_TRANSPORT" and caught.value.status == "transport_error"
    transport.assert_called_once()
    row, = audit_rows(gateway_case)
    assert row["status"] == "transport_error" and row["error"] == "LLM_TRANSPORT"
    assert "sensitive" not in str(row)


@pytest.mark.parametrize("code", [302, 401, 429, 500])
def test_http_error_no_retry_or_redirect_and_no_body_in_audit(gateway_case, code):
    client, transport = mock_client(gateway_case, handler=lambda request: httpx.Response(
        code, text="sensitive provider response", headers={"Location": "https://elsewhere.invalid"}))
    with pytest.raises(llm.LLMError) as caught:
        client.chat(MESSAGES, TOOLS)
    assert caught.value.status == "http_error" and caught.value.code == "LLM_HTTP"
    transport.assert_called_once()
    row, = audit_rows(gateway_case)
    assert row["status"] == "http_error" and row["error"] == "LLM_HTTP"
    assert "sensitive" not in str(row)


@pytest.mark.parametrize("usage", ["absent", None, {}, {"prompt_tokens": 3}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}])
def test_usage_missing_fields_are_null_and_provider_zero_is_preserved(gateway_case, usage):
    body = deepcopy(BODY)
    if usage == "absent":
        del body["usage"]
    else:
        body["usage"] = usage
    client, _ = mock_client(gateway_case, body)
    result = client.chat(MESSAGES, [])
    row, = audit_rows(gateway_case)
    expected = usage if isinstance(usage, dict) else {}
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        assert row[name] == expected.get(name)
    if usage == "absent" or usage is None:
        assert result.usage is None
        assert row["prompt_tokens"] is None and row["completion_tokens"] is None and row["total_tokens"] is None
    assert row["tool_names"] is None


def test_reconfigure_same_client_without_code_changes_and_optional_settings_empty(gateway_case):
    c = gateway_case
    client, handler = mock_client(c)
    first = client.chat(MESSAGES, TOOLS).model_dump_json()
    llm.write_settings(c.database, llm.LLMSettings(base_url="http://localhost:11434/v1/", model="other-model"))
    second = client.chat(MESSAGES, TOOLS).model_dump_json()
    assert first == second
    request = handler.call_args.args[0]
    assert str(request.url) == "http://localhost:11434/v1/chat/completions"
    assert json.loads(request.content) == {"model": "other-model", "messages": MESSAGES, "tools": TOOLS, "stream": False}
    assert request.extensions["timeout"] == dict.fromkeys(("connect", "read", "write", "pool"), None)
    assert "Authorization" not in request.headers
    assert [row["model"] for row in audit_rows(c)] == ["mock-model", "other-model"]


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {"tool_calls": [{}]}}]}])
def test_malformed_provider_reply_is_audited(gateway_case, body):
    client, transport = mock_client(gateway_case, body)
    with pytest.raises(llm.LLMError) as error:
        client.chat(MESSAGES, TOOLS)
    assert error.value.code == "LLM_HTTP"
    assert "响应格式" in error.value.payload.detail
    transport.assert_called_once()
    assert len(audit_rows(gateway_case)) == 1


def test_unconfigured_call_does_not_send_and_is_audited(gateway_case):
    llm.write_settings(gateway_case.database, llm.LLMSettings())
    client, transport = mock_client(gateway_case)
    with pytest.raises(llm.LLMError, match="LLM_NOT_CONFIGURED") as caught:
        client.chat(MESSAGES, TOOLS)
    assert caught.value.code == "LLM_NOT_CONFIGURED" and caught.value.status == "http_error"
    transport.assert_not_called()
    row, = audit_rows(gateway_case)
    assert row["model"] == "" and row["status"] == "http_error"


@pytest.mark.parametrize("with_usage", [True, False])
def test_stream_delta_tool_arguments_and_usage_aggregate_into_single_result(gateway_case, with_usage):
    frames = [
        {"choices": [{"index": 0, "delta": {"content": "选择", "tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "datasets.describe", "arguments": '{"dataset_'}}]}}]},
        {"choices": [{"index": 0, "delta": {"content": "工具", "tool_calls": [{"index": 0, "function": {"arguments": 'id":"cube-1"}'}}]}, "finish_reason": "tool_calls"}]},
    ]
    if with_usage:
        frames.append({"choices": [], "usage": BODY["usage"]})
    data = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames) + "data: [DONE]\n\n"
    client, transport = mock_client(gateway_case, handler=lambda request: httpx.Response(
        200, text=data, headers={"Content-Type": "text/event-stream"}))
    result = client.chat(MESSAGES, TOOLS, stream=True)
    assert result.content == "选择工具" and result.finish_reason == "tool_calls"
    assert result.tool_calls[0].model_dump() == {"id": "call-1", "name": "datasets.describe", "arguments_json": '{"dataset_id":"cube-1"}'}
    row, = audit_rows(gateway_case)
    assert row["total_tokens"] == (29 if with_usage else None)
    assert json.loads(transport.call_args.args[0].content)["stream_options"] == {"include_usage": True}

@pytest.mark.parametrize("stream", [False, True])
def test_egress_disabled_never_transports_and_records_blocked_attempt(gateway_case, stream):
    c = gateway_case
    llm.write_settings(c.database, c.settings.model_copy(update={"egress_enabled": False}))
    client, transport = mock_client(c)
    with pytest.raises(llm.LLMError) as caught:
        client.chat(MESSAGES, TOOLS, stream=stream)
    assert caught.value.code == "LLM_EGRESS_DISABLED" and caught.value.status == "blocked"
    transport.assert_not_called()
    row, = audit_rows(c)
    assert row["model"] == c.settings.model
    assert row["status"] == "blocked" and row["error"] == "LLM_EGRESS_DISABLED"
    assert all(row[k] is None for k in ("prompt_tokens", "completion_tokens", "total_tokens"))


def test_disabled_switch_precedes_forbidden_content_scan(gateway_case):
    c = gateway_case
    llm.write_settings(c.database, c.settings.model_copy(update={"egress_enabled": False}))
    client, transport = mock_client(c)
    with pytest.raises(llm.LLMError) as caught:
        client.chat([{"role": "user", "content": "private.img"}], TOOLS)
    assert caught.value.code == "LLM_EGRESS_DISABLED" and caught.value.status == "blocked"
    transport.assert_not_called()
    row, = audit_rows(c)
    assert (row["status"], row["error"]) == ("blocked", "LLM_EGRESS_DISABLED")


def test_egress_boolean_storage_uses_explicit_text_encoding(gateway_case):
    c = gateway_case
    for enabled, encoded in [(False, "0"), (True, "1")]:
        llm.write_settings(c.database, c.settings.model_copy(update={"egress_enabled": enabled}))
        assert llm.read_settings(c.database).egress_enabled is enabled
        with connect_database(c.database) as db:
            assert db.execute("SELECT value,typeof(value) FROM llm_settings WHERE key='egress_enabled'").fetchone() == (encoded, "text")
