"""12.3 state branches, durable continuation, complete audit and no history."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import sqlite3
from unittest.mock import Mock

import httpx
import pytest

from backend.database import connect_database
from spectrumagent.agent import llm, skill
from spectrumagent.agent.llm import ChatResult, LLMClient, LLMError, OpenAICompatibleClient, ToolCall, _json
from spectrumagent.agent.state import AgentStore, State, StateMachine
from spectrumagent.agent.tools import ConfirmArguments, NoArguments, ToolRegistry, build_registry
from spectrumagent.data import DataError


class FakeLLM(LLMClient):
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def chat(self, messages, tools, *, stream=False):
        self.calls.append((deepcopy(messages), deepcopy(tools), stream))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def call(name="datasets.list", arguments="{}", identifier="call-1"):
    return ToolCall(id=identifier, name=name, arguments_json=arguments)


def reply(content=None, calls=()):
    return ChatResult(content=content, tool_calls=list(calls), finish_reason="tool_calls" if calls else "stop")


def registry(*, confirm_ready=True):
    tools = ToolRegistry()
    normal = Mock(return_value={"count": 2})
    confirm = Mock(return_value={"version_id": "version-1"})
    tools.register("datasets.list", NoArguments, "数据集列表", normal)
    tools.register("annotations.draft_confirm", ConfirmArguments, "标注版本确认",
                   confirm if confirm_ready else None, human_check=True)
    return tools, normal, confirm


def rounds(database):
    with connect_database(database) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM agent_round ORDER BY seq")]


def machine(case, fake, tools=None):
    store = AgentStore(case.database)
    session = store.create_session()
    tools = tools if tools is not None else registry()[0]
    return StateMachine(store, session["id"], fake, tools)


def test_clarify_without_calls_never_executes_and_title_is_first_40_characters(gateway_case):
    tools, handler, _ = registry()
    fake = FakeLLM(reply("请说明数据集"))
    state = machine(gateway_case, fake, tools)
    content = "首条用户消息" * 12
    assert list(state.message(content=content)) == [("clarify", {"question": "请说明数据集"})]
    handler.assert_not_called()
    assert state.store.steps(state.session_id) == [] and state.state == State.IDLE
    assert state.store.session(state.session_id)["title"] == content[:40]
    row, = rounds(gateway_case.database)
    assert row["user_message"] == content and row["status"] == "done" and row["calls_json"] == "[]"


def test_error_transport_branch_resets_idle_no_retry_and_persists_round(gateway_case):
    tools, handler, _ = registry()
    fake = FakeLLM(LLMError("LLM_TRANSPORT", "transport_error"))
    state = machine(gateway_case, fake, tools)
    events = list(state.message(content="当前数据集"))
    assert events == [("error", {"code": "LLM_TRANSPORT", "detail": "LLM_TRANSPORT"})]
    assert state.state == State.IDLE and len(fake.calls) == 1
    handler.assert_not_called()
    assert rounds(gateway_case.database)[0]["status"] == "error"


def test_normal_steps_digest_interpret_tools_none_and_second_turn_has_no_history(gateway_case):
    fake = FakeLLM(reply(calls=[call()]), reply("第一轮结论"), reply(calls=[call(identifier="call-2")]), reply("第二轮结论"))
    state = machine(gateway_case, fake)
    first = list(state.message(content="第一轮专有文字"))
    first_title = state.store.session(state.session_id)["title"]
    second = list(state.message(content="第二轮专有文字"))
    assert [event for event, _ in first] == ["step", "done"]
    assert second[-1] == ("done", {"content": "第二轮结论", "step_count": 1})
    rows = state.store.steps(state.session_id)
    assert [row["seq"] for row in rows] == [1, 2]
    assert rows[0]["round_id"] != rows[1]["round_id"]
    for row in rows:
        assert row["status"] == "ok" and json.loads(row["arguments_json"]) == {}
        assert row["result_digest"] == sha256(_json({"count": 2}).encode()).hexdigest()
        assert row["latency_ms"] >= 0
    assert fake.calls[1][1] is None and fake.calls[3][1] is None
    assert "第一轮专有文字" not in _json(fake.calls[2][0]) + _json(fake.calls[3][0])
    assert "第二轮专有文字" in _json(fake.calls[3][0])
    assert state.store.session(state.session_id)["title"] == first_title
    assert [row["seq"] for row in rounds(gateway_case.database)] == [1, 2]


def test_schema_rejection_audit_is_bounded_and_raw_arguments_never_reach_interpret(gateway_case):
    tools, handler, _ = registry()
    raw = '{"points":[[1,2]],"private":"' + "中文" * 3000 + '"}'
    fake = FakeLLM(reply(calls=[call(arguments=raw)]), reply("请补充合法参数"))
    state = machine(gateway_case, fake, tools)
    events = list(state.message(content="查询"))
    assert [event for event, _ in events] == ["step", "done"]
    step, = state.store.steps(state.session_id)
    arguments = json.loads(step["arguments_json"])
    assert set(arguments) == {"_raw_sha256", "_raw_truncated"}
    assert arguments["_raw_sha256"] == sha256(raw.encode()).hexdigest()
    assert 0 < len(arguments["_raw_truncated"].encode()) <= 4096
    assert step["status"] == "rejected" and step["result_digest"] is None
    assert json.loads(step["result_summary"]) == {"error": "TOOL_ARGS_INVALID"}
    assert rounds(gateway_case.database)[0]["calls_json"] == "[]"
    assert "points" not in _json(fake.calls[1][0]) and "[[" not in _json(fake.calls[1][0])
    handler.assert_not_called()


@pytest.mark.parametrize("count", [8, 9, 11])
def test_sequence_limit_first_eight_execute_rest_are_all_rejected(gateway_case, count):
    tools, handler, _ = registry()
    fake = FakeLLM(reply(calls=[call(identifier=f"call-{index}") for index in range(count)]), reply("完成"))
    state = machine(gateway_case, fake, tools)
    events = list(state.message(content="执行已注册工具"))
    rows = state.store.steps(state.session_id)
    assert len(rows) == count and handler.call_count == min(count, 8)
    assert [row["seq"] for row in rows] == list(range(1, count + 1))
    rejected = [row for row in rows if row["status"] == "rejected"]
    assert len(rejected) == max(0, count - 8)
    assert all(json.loads(row["result_summary"]) == {"error": "TOOL_SEQUENCE_LIMIT"} and row["result_digest"] is None for row in rejected)
    assert events[-1] == ("done", {"content": "完成", "step_count": count})
    assert len(json.loads(rounds(gateway_case.database)[0]["calls_json"])) == min(count, 8)


def test_human_check_recovers_original_message_and_remaining_calls_after_restart(gateway_case):
    tools, normal, confirm = registry()
    original = "本轮用户原文" * 20
    calls = [call(identifier="before"), call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}', "check"), call(identifier="after")]
    parsing = FakeLLM(reply(calls=calls))
    state = machine(gateway_case, parsing, tools)
    events = list(state.message(content=original))
    assert [event for event, _ in events] == ["step", "human_check"]
    confirm.assert_not_called()
    assert normal.call_count == 1
    check = events[-1][1]
    assert check["tool"] == "annotations.draft_confirm" and check["summary"] == {"cube_id": "cube-1", "revision": 1}
    pending = state.store.steps(state.session_id)[-1]
    assert check["check_id"] == pending["id"] and pending["status"] == "human_check_pending"
    with pytest.raises(DataError) as caught:
        state.message(content="不允许插入的新消息")
    assert caught.value.code == "INVALID_REQUEST"
    interpretation = FakeLLM(reply("确认后完成"))
    restarted = StateMachine(AgentStore(gateway_case.database), state.session_id, interpretation, tools)
    resumed = list(restarted.message(check_id=check["check_id"], decision="approve"))
    assert [event for event, _ in resumed] == ["step", "step", "done"]
    confirm.assert_called_once()
    assert normal.call_count == 2 and len(parsing.calls) == len(interpretation.calls) == 1
    messages, requested_tools, _ = interpretation.calls[0]
    assert requested_tools is None and messages[1] == {"role": "user", "content": original}
    assert [message["tool_call_id"] for message in messages if message["role"] == "tool"] == ["before", "check", "after"]
    assert any("version-1" in message.get("content", "") for message in messages if message["role"] == "tool")
    rows = restarted.store.steps(state.session_id)
    assert len(rows) == 3 and rows[1]["id"] == pending["id"] and all(row["status"] == "ok" for row in rows)
    assert rounds(gateway_case.database)[0]["status"] == "done"


def test_human_reject_executes_nothing_and_closes_round_without_llm(gateway_case):
    tools, normal, confirm = registry()
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}'), call(identifier="later")]))
    state = machine(gateway_case, fake, tools)
    pending = list(state.message(content="确认当前版本"))[-1][1]
    events = list(state.message(check_id=pending["check_id"], decision="reject"))
    normal.assert_not_called()
    confirm.assert_not_called()
    assert len(fake.calls) == 1 and events[-1] == ("done", {"content": "已拒绝、未执行", "step_count": 1})
    row, = state.store.steps(state.session_id)
    assert row["status"] == "rejected" and row["result_digest"] is None
    assert rounds(gateway_case.database)[0]["status"] == "done"
    with pytest.raises(DataError):
        state.message(check_id=pending["check_id"], decision="approve")


def test_approve_unready_tool_errors_after_gate_and_resets_idle(gateway_case):
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}')]))
    state = machine(gateway_case, fake, build_registry())
    events = list(state.message(content="确认"))
    assert [event for event, _ in events] == ["human_check"]
    resumed = list(state.message(check_id=events[0][1]["check_id"], decision="approve"))
    assert [event for event, _ in resumed] == ["step", "error"]
    assert resumed[-1][1]["code"] == "TOOL_NOT_IMPLEMENTED" and state.state == State.IDLE
    row, = state.store.steps(state.session_id)
    assert row["status"] == "error" and json.loads(row["result_summary"]) == {"error": "TOOL_NOT_IMPLEMENTED"}
    assert rounds(gateway_case.database)[0]["status"] == "error"


def test_reject_closes_round_before_first_event_even_if_stream_is_disconnected(gateway_case):
    tools, _, confirm = registry()
    state = machine(gateway_case, FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}')])), tools)
    check = list(state.message(content="确认"))[0][1]
    events = state.message(check_id=check["check_id"], decision="reject")
    assert next(events)[0] == "step"
    events.close()
    assert rounds(gateway_case.database)[0]["status"] == "done"
    state.store.preflight(state.session_id)
    confirm.assert_not_called()


@pytest.mark.parametrize("tool_failed", [False, True])
def test_interrupted_running_stream_releases_session_without_retry(gateway_case, tool_failed):
    tools, handler, _ = registry()
    if tool_failed:
        handler.side_effect = RuntimeError("fixture failure")
    state = machine(gateway_case, FakeLLM(reply(calls=[call()])), tools)
    events = state.message(content="执行")
    assert next(events)[0] == "step"
    events.close()
    assert rounds(gateway_case.database)[0]["status"] == "error" and state.state == State.IDLE
    state.store.preflight(state.session_id)
    handler.assert_called_once()


def test_closing_human_check_event_preserves_durable_pending_round(gateway_case):
    tools, _, confirm = registry()
    state = machine(gateway_case, FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}')])), tools)
    events = state.message(content="确认")
    kind, check = next(events)
    assert kind == "human_check"
    events.close()
    assert rounds(gateway_case.database)[0]["status"] == "human_check"
    restored = StateMachine(AgentStore(gateway_case.database), state.session_id, FakeLLM(), tools)
    assert list(restored.message(check_id=check["check_id"], decision="reject"))[-1][0] == "done"
    confirm.assert_not_called()


def test_stale_approval_stream_cannot_execute_again_or_corrupt_completed_round(gateway_case):
    tools, _, confirm = registry()
    state = machine(gateway_case, FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}')]), reply("完成")), tools)
    check = list(state.message(content="确认"))[0][1]
    first = state.message(check_id=check["check_id"], decision="approve")
    concurrent = StateMachine(state.store, state.session_id, FakeLLM(), tools)
    stale = concurrent.message(check_id=check["check_id"], decision="approve")
    assert list(first)[-1][0] == "done"
    assert list(stale)[-1][1]["code"] == "INVALID_REQUEST"
    confirm.assert_called_once()
    assert rounds(gateway_case.database)[0]["status"] == "done"


def test_step_sequence_allocation_is_serialized_in_database(gateway_case):
    store = AgentStore(gateway_case.database)
    session = store.create_session()
    round_ = store.new_round(session["id"], "并发记账测试", [])
    def append(index):
        return AgentStore(gateway_case.database).add_step(round_, "datasets.list", {}, "ok", {"count": index}, 0)["seq"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        seqs = list(pool.map(append, range(12)))
    assert sorted(seqs) == list(range(1, 13))
    assert [row["seq"] for row in store.steps(session["id"])] == list(range(1, 13))


def test_schema_validation_precedes_human_gate(gateway_case):
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1"}')]), reply("缺少 revision"))
    state = machine(gateway_case, fake, build_registry())
    assert [event for event, _ in state.message(content="确认")] == ["step", "done"]
    assert state.store.steps(state.session_id)[0]["status"] == "rejected"


def test_tool_runtime_error_is_audited_and_sensitive_details_are_not_emitted(gateway_case):
    tools, handler, _ = registry()
    handler.side_effect = RuntimeError("private.img SECRET")
    fake = FakeLLM(reply(calls=[call()]))
    state = machine(gateway_case, fake, tools)
    events = list(state.message(content="执行"))
    assert [event for event, _ in events] == ["step", "error"] and events[-1][1]["code"] == "TOOL_FAILED"
    assert "SECRET" not in _json(events) + _json(state.store.steps(state.session_id))
    assert state.state == State.IDLE and len(fake.calls) == 1


def test_interpret_cannot_call_tools_again(gateway_case):
    tools, handler, _ = registry()
    fake = FakeLLM(reply(calls=[call()]), reply(calls=[call(identifier="loop")]))
    state = machine(gateway_case, fake, tools)
    assert list(state.message(content="查询"))[-1][1]["code"] == "LLM_UNEXPECTED_TOOL_CALL"
    assert handler.call_count == 1 and state.state == State.IDLE


def test_real_gateway_with_mock_provider_audits_both_calls_with_session_id(gateway_case):
    def provider(request):
        body = json.loads(request.content)
        message = {"content": "已查询"}
        if "tools" in body:
            message = {"content": None, "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "datasets.list", "arguments": "{}"}}]}
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})
    store = AgentStore(gateway_case.database)
    session = store.create_session()
    fake_provider = Mock(side_effect=provider)
    client = OpenAICompatibleClient(gateway_case.database, session_id=session["id"], transport=httpx.MockTransport(fake_provider))
    state = StateMachine(store, session["id"], client, registry()[0])
    assert list(state.message(content="查询数据集"))[-1][0] == "done"
    assert fake_provider.call_count == 2
    with connect_database(gateway_case.database) as db:
        assert db.execute("SELECT session_id,status,prompt_tokens,completion_tokens,total_tokens FROM llm_call").fetchall() == [
            (session["id"], "ok", None, None, None), (session["id"], "ok", None, None, None)]


def test_session_skill_snapshot_and_metadata_immutability(gateway_case):
    fake = FakeLLM(reply("请补充"))
    state = machine(gateway_case, fake)
    original = state.store.session(state.session_id)
    with connect_database(gateway_case.database) as db:
        old = skill.active_skill(db)
        new = skill.append_draft(db, name="explicit-next", system_prompt="新版本正文", tools_json=old["tools_json"], examples_json="[]")
        skill.switch(db, new["id"])
    list(state.message(content="首条消息"))
    assert fake.calls[0][0][0]["content"] == old["system_prompt"]
    with connect_database(gateway_case.database) as db:
        for sql, args in [("UPDATE agent_session SET title='再次修改' WHERE id=?", (state.session_id,)),
                          ("UPDATE agent_session SET skill_version_id=? WHERE id=?", (new["id"], state.session_id)),
                          ("UPDATE agent_session SET created_at='changed' WHERE id=?", (state.session_id,))]:
            with pytest.raises(sqlite3.IntegrityError, match="AGENT_IMMUTABLE"):
                db.execute(sql, args)
    after = state.store.session(state.session_id)
    assert after["created_at"] == original["created_at"] and after["skill_version_id"] == old["id"]
    assert after["updated_at"] >= original["updated_at"]

def test_egress_disabled_error_resets_idle_and_persists_failed_round(gateway_case):
    tools, handler, _ = registry()
    fake = FakeLLM(LLMError("LLM_EGRESS_DISABLED", "blocked"))
    state = machine(gateway_case, fake, tools)
    assert list(state.message(content="查询数据集")) == [
        ("error", {"code": "LLM_EGRESS_DISABLED", "detail": "LLM_EGRESS_DISABLED"})]
    assert state.state == State.IDLE and len(fake.calls) == 1
    handler.assert_not_called()
    assert rounds(gateway_case.database)[0]["status"] == "error"


@pytest.mark.parametrize("disable_during_parse", [False, True])
def test_real_gateway_master_switch_controls_parse_and_interpret(gateway_case, disable_during_parse):
    c = gateway_case
    llm.write_settings(c.database, c.settings.model_copy(update={"egress_enabled": disable_during_parse}))
    def provider(request):
        assert json.loads(request.content)["tools"]
        # This already-admitted request completes normally after the persisted
        # switch changes; only the next chat() is rejected.
        llm.write_settings(c.database, c.settings.model_copy(update={"egress_enabled": False}))
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [{
            "id": "call-1", "type": "function",
            "function": {"name": "datasets.list", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}]})
    store = AgentStore(c.database)
    session = store.create_session()
    transport = Mock(side_effect=provider)
    client = OpenAICompatibleClient(c.database, session_id=session["id"], transport=httpx.MockTransport(transport))
    tools, handler, _ = registry()
    state = StateMachine(store, session["id"], client, tools)
    events = list(state.message(content="查询数据集"))
    assert events[-1] == ("error", {"code": "LLM_EGRESS_DISABLED", "detail": "LLM_EGRESS_DISABLED"})
    assert [event for event, _ in events] == (["step", "error"] if disable_during_parse else ["error"])
    assert state.state == State.IDLE and rounds(c.database)[0]["status"] == "error"
    assert transport.call_count == handler.call_count == int(disable_during_parse)
    if not disable_during_parse:
        transport.assert_not_called()
    with connect_database(c.database) as db:
        rows = db.execute("SELECT session_id,model,status,error,prompt_tokens,completion_tokens,total_tokens FROM llm_call ORDER BY rowid").fetchall()
    blocked = (session["id"], c.settings.model, "blocked", "LLM_EGRESS_DISABLED", None, None, None)
    assert rows == ([(session["id"], c.settings.model, "ok", None, None, None, None), blocked]
                    if disable_during_parse else [blocked])
