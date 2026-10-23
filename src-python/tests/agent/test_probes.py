"""TASK-07 §2.3 seven independent mock probes, R12 audit/order decisions."""
from hashlib import sha256
import json
import re
from unittest.mock import Mock

import httpx
import pytest

from backend.database import connect_database
from spectrumagent.agent.llm import LLMError, OpenAICompatibleClient, _json
from spectrumagent.agent.tools import ConfirmArguments, CubeArguments, ToolRegistry
from .conftest import audit_rows
from .test_agent_api import BASE, configure, stream
from .test_state import FakeLLM, call, registry, reply, rounds


def steps(case, session):
    return case.client.get(f"{BASE}/{session['id']}/steps").json()["steps"]


def test_probe_1_gateway_tool_interpret_and_two_audited_calls(settings_api):
    case = settings_api
    requests = []

    def provider(request):
        body = json.loads(request.content)
        requests.append(body)
        message = {"content": "已完成查询"}
        if len(requests) == 1:
            assert body["tools"]
            message = {"content": None, "tool_calls": [{"id": "list-1", "type": "function",
                "function": {"name": "datasets.list", "arguments": "{}"}}]}
        else:
            assert "tools" not in body
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 8, "total_tokens": 29}})

    session = configure(case, FakeLLM())
    case.app.state.agent_llm_factory = lambda session_id: OpenAICompatibleClient(
        case.database, session_id=session_id, transport=httpx.MockTransport(provider))
    events = stream(case, session["id"], {"content": "查询数据集"})
    assert [name for name, _ in events] == ["step", "done"]
    step, = steps(case, session)
    assert step["status"] == "ok" and json.loads(step["result_summary"]) == {"count": 2}
    assert step["result_digest"] == sha256(_json({"count": 2}).encode()).hexdigest()
    rows = audit_rows(case)
    assert len(requests) == len(rows) == 2
    for row in rows:
        assert (row["session_id"], row["status"], row["prompt_tokens"], row["completion_tokens"], row["total_tokens"]) == (
            session["id"], "ok", 17, 8, 29)
        assert len(row["prompt_sha256"]) == 64 and row["latency_ms"] >= 0


def test_probe_2_missing_parameters_clarify_without_execution(settings_api):
    tools, handler, _ = registry()
    session = configure(settings_api, FakeLLM(reply("请指定数据集 id")), tools)
    assert stream(settings_api, session["id"], {"content": "查看数据"}) == [
        ("clarify", {"question": "请指定数据集 id"})]
    handler.assert_not_called()
    assert steps(settings_api, session) == []


def test_probe_3_geometry_schema_rejection_is_audited(settings_api):
    raw = _json({"points": [[1, 2]], "extra": "坐标" * 2000})
    tools, handler, _ = registry()
    session = configure(settings_api, FakeLLM(reply(calls=[call(arguments=raw)]), reply("参数已拒绝")), tools)
    events = stream(settings_api, session["id"], {"content": "查询"})
    assert [name for name, _ in events] == ["step", "done"]
    row, = steps(settings_api, session)
    assert row["status"] == "rejected" and row["result_digest"] is None
    assert json.loads(row["result_summary"]) == {"error": "TOOL_ARGS_INVALID"}
    arguments = json.loads(row["arguments_json"])
    assert set(arguments) == {"_raw_sha256", "_raw_truncated"}
    assert arguments["_raw_sha256"] == sha256(raw.encode()).hexdigest()
    assert len(arguments["_raw_truncated"].encode()) <= 4096
    assert raw.startswith(arguments["_raw_truncated"])
    handler.assert_not_called()


def test_probe_4_overwrite_waits_for_human_check(settings_api):
    tools, _, handler = registry()
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1,"overwrite":true}')]))
    session = configure(settings_api, fake, tools)
    events = stream(settings_api, session["id"], {"content": "确认覆写"})
    assert [name for name, _ in events] == ["human_check"]
    handler.assert_not_called()
    with connect_database(settings_api.database) as db:
        pending, = db.execute("SELECT id,status FROM agent_step WHERE session_id=?", (session["id"],)).fetchall()
    assert pending == (events[0][1]["check_id"], "human_check_pending")


@pytest.mark.parametrize("content", ['[[1,2],[3,4]]', 'E:/nas/source.img'])
def test_probe_5_gateway_egress_blocked_without_transport(gateway_case, content):
    transport = Mock()
    client = OpenAICompatibleClient(gateway_case.database, transport=httpx.MockTransport(transport))
    with pytest.raises(LLMError) as error:
        client.chat([{"role": "user", "content": content}], None)
    assert error.value.code == "EGRESS_BLOCKED"
    transport.assert_not_called()
    row, = audit_rows(gateway_case)
    assert row["status"] == "blocked" and row["error"] == "EGRESS_BLOCKED"


def test_probe_6_ten_calls_keep_parse_rejections_first(settings_api):
    tools, handler, _ = registry()
    fake = FakeLLM(reply(calls=[call(identifier=f"call-{i}") for i in range(1, 11)]), reply("完成"))
    session = configure(settings_api, fake, tools)
    events = stream(settings_api, session["id"], {"content": "依序查询"})
    assert [name for name, _ in events] == ["step"] * 10 + ["done"]
    rows = steps(settings_api, session)
    assert [row["seq"] for row in rows] == list(range(1, 11))
    assert [row["status"] for row in rows] == ["rejected"] * 2 + ["ok"] * 8
    assert all(row["result_digest"] is None and json.loads(row["result_summary"]) == {
        "error": "TOOL_SEQUENCE_LIMIT"} for row in rows[:2])
    assert handler.call_count == 8
    calls = json.loads(rounds(settings_api.database)[0]["calls_json"])
    assert [call["id"] for call in calls] == [f"call-{i}" for i in range(1, 9)]


@pytest.mark.parametrize("tool", ["annotations.draft_confirm", "annotations.draft_get"])
def test_probe_7_only_scalar_summaries_enter_interpret(settings_api, tool):
    tools = ToolRegistry()
    confirm = {"version_id": "version-1", "conflict_count": 3, "detail": "存在 3 处跨类重叠，请在画布上处理"}
    draft = {"cube_id": "cube-1", "revision": 2, "n_regions": 5, "n_classes": 3,
             "updated_at": "2026-10-23T00:00:00+00:00", "estimated_mat_bytes": 118000000}
    tools.register("annotations.draft_confirm", ConfirmArguments, "确认", Mock(return_value=confirm), human_check=True)
    # 12.2's actual draft_get schema is CubeArguments (no new schema/version).
    tools.register("annotations.draft_get", CubeArguments, "摘要", Mock(return_value=draft))
    arguments = {"cube_id": "cube-1"}
    if tool.endswith("confirm"):
        arguments["revision"] = 2
    fake = FakeLLM(reply(calls=[call(tool, _json(arguments))]), reply("已收到摘要"))
    session = configure(settings_api, fake, tools)
    events = stream(settings_api, session["id"], {"content": "处理标注"})
    if tool.endswith("confirm"):
        assert events[0][0] == "human_check"
        events = stream(settings_api, session["id"], {"check_id": events[0][1]["check_id"], "decision": "approve"})
    assert [name for name, _ in events] == ["step", "done"]
    messages, requested_tools, _ = fake.calls[-1]
    assert requested_tools is None
    text = _json(messages)
    assert "[[" not in text and not re.search(r'\b(?:points|polygon|sample_pixels|bbox|document)\b', text)
    summary = json.loads(next(message["content"] for message in messages if message["role"] == "tool"))
    assert summary == (confirm if tool.endswith("confirm") else draft)
    if tool.endswith("get"):
        assert summary["estimated_mat_bytes"] == 118000000
