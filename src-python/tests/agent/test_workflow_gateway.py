"""Workflow gateway contract: portable tools, safe diagnostics, no network.

These tests exercise the real HTTP adapter and, for rejected replies, the real
workflow state machine. The provider is always an injected MockTransport.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
from unittest.mock import Mock

import httpx
import pytest

from backend.database import connect_database
from spectrumagent.agent import llm, skill
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.tools import build_registry
from .conftest import audit_rows, mock_client


SYNTHETIC_KEY = "synthetic-gateway-test-key"
BODY_MARKER = "synthetic-private-provider-body"


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("workflow gateway tests must never use a real HTTP transport")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)


def workflow_tools():
    return build_registry(catalogue_version=2).snapshot()


def response_message(content=None, *, calls=None, finish="stop"):
    message = {"content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return {"choices": [{"message": message, "finish_reason": finish}]}


def native_call(name="sa_annotations__prepare", identifier="next-call"):
    return {"id": identifier, "type": "function", "function": {
        "name": name, "arguments": '{"cube_id":"cube-1"}'}}


def assert_private_audit(case):
    text = json.dumps(audit_rows(case), ensure_ascii=False, sort_keys=True)
    for private in (SYNTHETIC_KEY, BODY_MARKER, "Authorization", "Bearer", "user-private-text"):
        assert private not in text
    return audit_rows(case)


@pytest.mark.parametrize("stream", [False, True])
def test_v2_tools_and_historical_calls_use_portable_names_and_decode_locally(gateway_case, stream):
    tools = workflow_tools()
    messages = [
        {"role": "user", "content": "user-private-text"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "prior-call", "type": "function",
            "function": {"name": "datasets.resolve", "arguments": '{"query":"cube-1"}'}}]},
        {"role": "tool", "tool_call_id": "prior-call", "content": '{"cube_id":"cube-1","status":"resolved"}'},
        {"role": "assistant", "content": "已选择合成样品"},
        {"role": "user", "content": "使用默认参数准备标注"},
    ]
    original_messages, original_tools = deepcopy(messages), deepcopy(tools)
    captured = []

    def provider(request):
        body = json.loads(request.content)
        captured.append(body)
        assert request.headers["Authorization"] == "Bearer " + SYNTHETIC_KEY
        names = [tool["function"]["name"] for tool in body["tools"]]
        assert len(set(names)) == len(names) == len(tools)
        assert all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name) for name in names)
        assert "sa_annotations__prepare" in names and "annotations.prepare" not in names
        for local, wire in zip(tools, body["tools"]):
            assert wire["function"]["parameters"] == local["function"]["parameters"]
            assert wire["function"]["description"] == local["function"]["description"]
        prior = body["messages"][1]["tool_calls"][0]
        assert prior["id"] == "prior-call" and prior["function"] == {
            "name": "sa_datasets__resolve", "arguments": '{"query":"cube-1"}'}
        assert body["messages"][2] == original_messages[2]
        assert body["messages"][3] == original_messages[3]
        if not stream:
            return httpx.Response(200, json=response_message(calls=[native_call()], finish="tool_calls"))
        frames = [
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "next-call",
                "function": {"name": "sa_annotations__prepare", "arguments": '{"cube_id":'}}]}}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0,
                "function": {"arguments": '"cube-1"}'}}]}, "finish_reason": "tool_calls"}]},
        ]
        text = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames) + "data: [DONE]\n\n"
        return httpx.Response(200, text=text, headers={"Content-Type": "text/event-stream"})

    llm.set_api_key(SYNTHETIC_KEY)
    client, handler = mock_client(gateway_case, handler=provider)
    result = client.chat(messages, tools, stream=stream)
    assert result.tool_calls[0].model_dump() == {"id": "next-call", "name": "annotations.prepare",
        "arguments_json": '{"cube_id":"cube-1"}'}
    assert messages == original_messages and tools == original_tools
    handler.assert_called_once()
    row, = assert_private_audit(gateway_case)
    assert row["status"] == "ok" and row["http_status"] == 200 and row["error_stage"] is None
    assert row["prompt_sha256"] == sha256(llm._json(original_messages).encode()).hexdigest()
    assert json.loads(row["tool_names"]) == [tool["function"]["name"] for tool in tools]
    assert len(captured) == 1


@pytest.mark.parametrize("body, expected", [
    (response_message('<｜DSML｜tool_calls><｜DSML｜invoke name="tools.list">' + BODY_MARKER
        + '</｜DSML｜invoke></｜DSML｜tool_calls>'), "LLM_TOOL_PROTOCOL"),
    (response_message('<tool_calls><invoke name="annotations.prepare">' + BODY_MARKER
        + '</invoke></tool_calls>', calls=[native_call()], finish="tool_calls"), "LLM_TOOL_PROTOCOL"),
    (response_message(BODY_MARKER, calls=[native_call()], finish="length"), "LLM_OUTPUT_TRUNCATED"),
    (response_message(BODY_MARKER, finish="max_tokens"), "LLM_OUTPUT_TRUNCATED"),
    (response_message(None, calls=[], finish="tool_calls"), "LLM_TOOL_PROTOCOL"),
    (response_message(None, calls=[native_call(identifier="duplicate"), native_call(identifier="duplicate")],
        finish="tool_calls"), "LLM_TOOL_PROTOCOL"),
])
def test_bad_tool_protocol_never_reaches_a_workflow_executor(gateway_case, body, expected):
    registry = build_registry(catalogue_version=2)
    registry.invoke = Mock(side_effect=AssertionError("provider prose must never execute"))
    with connect_database(gateway_case.database) as db:
        skill.ensure_workflow_skill(db, registry)
    store = AgentStore(gateway_case.database)
    session = store.create_session()
    llm.set_api_key(SYNTHETIC_KEY)
    client, transport = mock_client(gateway_case, body, session_id=session["id"])
    events = list(StateMachine(store, session["id"], client, registry).message(content="user-private-text"))
    assert [event for event, _ in events] == ["error"]
    assert events[0][1]["code"] == expected
    assert BODY_MARKER not in llm._json(events)
    registry.invoke.assert_not_called()
    assert store.steps(session["id"]) == []
    transport.assert_called_once()
    row, = assert_private_audit(gateway_case)
    assert (row["error"], row["status"], row["http_status"], row["error_stage"]) == (
        expected, "http_error", 200, "protocol")


@pytest.mark.parametrize("status, explanation", [(401, "鉴权"), (429, "限流"), (500, "暂时不可用")])
def test_http_error_has_safe_actionable_detail_and_classified_audit(gateway_case, status, explanation):
    llm.set_api_key(SYNTHETIC_KEY)
    client, transport = mock_client(gateway_case, handler=lambda request: httpx.Response(
        status, text=BODY_MARKER + SYNTHETIC_KEY, headers={"Authorization": SYNTHETIC_KEY}))
    with pytest.raises(llm.LLMError) as error:
        client.chat([{"role": "user", "content": "user-private-text"}], workflow_tools())
    assert error.value.code == "LLM_HTTP" and error.value.status == "http_error"
    assert explanation in error.value.payload.detail and str(status) in error.value.payload.detail
    assert BODY_MARKER not in str(error.value) and SYNTHETIC_KEY not in str(error.value)
    transport.assert_called_once()
    row, = assert_private_audit(gateway_case)
    assert (row["http_status"], row["error_stage"], row["error"]) == (status, "http", "LLM_HTTP")


@pytest.mark.parametrize("response", [
    lambda: httpx.Response(200, text=BODY_MARKER + SYNTHETIC_KEY, headers={"Content-Type": "text/html"}),
    lambda: httpx.Response(200, json={"choices": [], "private": BODY_MARKER}),
    lambda: httpx.Response(200, json={"choices": [{"message": None}], "private": BODY_MARKER}),
    lambda: httpx.Response(200, json={"choices": [{"message": []}], "private": BODY_MARKER}),
    lambda: httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{}]}}], "private": BODY_MARKER}),
])
def test_bad_response_is_distinct_from_http_failure_without_body_leak(gateway_case, response):
    llm.set_api_key(SYNTHETIC_KEY)
    client, transport = mock_client(gateway_case, handler=lambda request: response())
    with pytest.raises(llm.LLMError) as error:
        client.chat([{"role": "user", "content": "user-private-text"}], workflow_tools())
    assert error.value.code == "LLM_HTTP" and "响应格式" in error.value.payload.detail
    assert BODY_MARKER not in str(error.value) and SYNTHETIC_KEY not in str(error.value)
    transport.assert_called_once()
    row, = assert_private_audit(gateway_case)
    assert (row["http_status"], row["error_stage"], row["error"], row["status"]) == (
        200, "response", "LLM_HTTP", "http_error")
