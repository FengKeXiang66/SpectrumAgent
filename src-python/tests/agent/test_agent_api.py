"""R9/R10 finite SSE streams and preflight HTTP errors, with fake LLMs only."""
import json
from uuid import uuid4

import pytest

from backend.database import connect_database
from spectrumagent.agent import skill
from spectrumagent.agent.llm import LLMError
from spectrumagent.agent.state import AgentStore
from .test_state import FakeLLM, call, registry, reply, rounds


BASE = "/api/v1/agent/sessions"


def configure(case, fake, tools=None):
    case.app.state.agent_llm_factory = lambda session_id: fake
    case.app.state.agent_tools = tools if tools is not None else registry()[0]
    response = case.client.post(BASE, json={})
    assert response.status_code == 200
    return response.json()


def stream(case, session_id, body):
    with case.client.stream("POST", f"{BASE}/{session_id}/messages", json=body) as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        events, event = [], None
        for line in response.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                events.append((event, json.loads(line[6:])))
        return events


def test_create_session_snapshots_active_skill_and_get_steps(settings_api):
    c = settings_api
    session = configure(c, FakeLLM())
    assert set(session) == {"id", "title", "skill_version_id", "created_at",
                             "skill_name", "skill_version_no", "runtime"} and session["title"] == ""
    with connect_database(c.database) as db:
        assert session["skill_version_id"] == skill.active_skill(db)["id"]
    # The runtime block reports which orchestration actually runs, so the version is
    # verifiable instead of inferred from file timestamps.
    assert session["skill_name"]
    assert session["runtime"]["tool_catalogue_version"] >= 1
    assert session["runtime"]["tool_count"] >= 1
    response = c.client.get(f"{BASE}/{session['id']}/steps")
    assert response.json() == {"session_id": session["id"], "steps": []}
    assert response.headers["X-SpectrumAgent-Boot-Id"] == c.identity.boot_id


def test_runtime_endpoint_reports_active_skill_and_session_distribution(settings_api):
    c = settings_api
    session = configure(c, FakeLLM())
    runtime = c.client.get("/api/v1/agent/runtime").json()
    assert runtime["skill_name"] == session["skill_name"]
    assert runtime["skill_version_id"] == session["skill_version_id"]
    assert runtime["tool_catalogue_version"] >= 1
    assert runtime["sessions_by_skill"][runtime["skill_name"]] >= 1


def test_sse_step_done_and_get_step_fields(settings_api):
    c = settings_api
    fake = FakeLLM(reply(calls=[call()]), reply("已完成查询"))
    session = configure(c, fake)
    events = stream(c, session["id"], {"content": "查询"})
    assert [event for event, _ in events] == ["step", "done"]
    assert set(events[0][1]) == {"seq", "tool", "status", "result_summary"}
    assert events[-1][1] == {"content": "已完成查询", "step_count": 1}
    response = c.client.get(f"{BASE}/{session['id']}/steps").json()
    row, = response["steps"]
    assert set(row) == {"seq", "tool", "status", "arguments_json", "result_digest", "result_summary", "latency_ms", "created_at"}
    assert json.loads(row["arguments_json"]) == {} and json.loads(row["result_summary"]) == {"count": 2}
    assert len(row["result_digest"]) == 64


def test_sse_clarify_and_error_have_exact_fields_and_close_stream(settings_api):
    c = settings_api
    session = configure(c, FakeLLM(reply("哪个数据集？"), LLMError("LLM_TRANSPORT", "transport_error")))
    assert stream(c, session["id"], {"content": "查询"}) == [("clarify", {"question": "哪个数据集？"})]
    assert stream(c, session["id"], {"content": "继续"}) == [("error", {"code": "LLM_TRANSPORT", "detail": "LLM_TRANSPORT"})]


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_sse_human_check_original_stream_closes_answer_uses_new_stream(settings_api, decision):
    c = settings_api
    tools, normal, confirm = registry()
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}')]), reply("确认完成"))
    session = configure(c, fake, tools)
    original = stream(c, session["id"], {"content": "确认标注"})
    assert [event for event, _ in original] == ["human_check"]
    check = original[0][1]
    assert set(check) == {"check_id", "tool", "summary", "reason"}
    confirm.assert_not_called()
    pending = c.client.post(f"{BASE}/{session['id']}/messages", json={"content": "确认期间的新消息"})
    assert pending.status_code == 400 and pending.json()["error"] == "INVALID_REQUEST"
    # A fresh router request creates a fresh StateMachine; SQLite carries state.
    answer = stream(c, session["id"], {"check_id": check["check_id"], "decision": decision})
    assert [event for event, _ in answer] == ["step", "done"]
    assert confirm.call_count == (1 if decision == "approve" else 0)
    assert rounds(c.database)[0]["status"] == "done"
    assert c.client.post(f"{BASE}/{session['id']}/messages", json={"check_id": check["check_id"], "decision": decision}).status_code == 400


def test_approve_unready_tool_reports_step_then_error_with_http_200(settings_api):
    c = settings_api
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}')]))
    from spectrumagent.agent.tools import build_registry
    session = configure(c, fake, build_registry())
    check = stream(c, session["id"], {"content": "确认"})[0][1]
    events = stream(c, session["id"], {"check_id": check["check_id"], "decision": "approve"})
    assert [event for event, _ in events] == ["step", "error"] and events[-1][1]["code"] == "TOOL_NOT_IMPLEMENTED"


@pytest.mark.parametrize("body", [{}, {"content": ""}, {"content": 1}, {"check_id": "x"}, {"decision": "approve"},
    {"check_id": "x", "decision": "invalid"}, {"content": "x", "check_id": "y", "decision": "approve"},
    {"content": "x", "extra": "y"}, {"content": None}, {"check_id": "x", "decision": "approve", "extra": "y"}])
def test_invalid_body_shapes_are_http_400_before_stream(settings_api, body):
    c = settings_api
    fake = FakeLLM()
    session = configure(c, fake)
    response = c.client.post(f"{BASE}/{session['id']}/messages", json=body)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"
    assert fake.calls == [] and rounds(c.database) == []


@pytest.mark.parametrize("method,suffix,body", [("get", "/steps", None), ("post", "/messages", {"content": "查询"})])
def test_unknown_session_http_404(settings_api, method, suffix, body):
    c = settings_api
    c.app.state.agent_llm_factory = lambda session_id: FakeLLM()
    response = c.client.request(method, BASE + "/" + str(uuid4()) + suffix, json=body)
    assert response.status_code == 404 and response.json()["error"] == "SESSION_NOT_FOUND"


def test_no_active_http_409_and_no_session_inserted(settings_api):
    c = settings_api
    with connect_database(c.database) as db:
        skill.transition(db, skill.active_skill(db)["id"], "retired")
    response = c.client.post(BASE, json={})
    assert response.status_code == 409 and response.json()["error"] == "SKILL_NOT_ACTIVE"
    with connect_database(c.database) as db:
        assert db.execute("SELECT COUNT(*) FROM agent_session").fetchone()[0] == 0


@pytest.mark.parametrize("body", [{"title": "not accepted"}, None])
def test_create_session_only_accepts_empty_object(settings_api, body):
    response = settings_api.client.post(BASE, json=body)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"


@pytest.mark.parametrize("method,path,body", [("post", BASE, {}), ("get", BASE + "/unknown/steps", None), ("post", BASE + "/unknown/messages", {"content": "x"})])
def test_identity_authentication_precedes_agent_operations(settings_api, method, path, body):
    response = settings_api.client.request(method, path, json=body, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401 and "X-SpectrumAgent-Boot-Id" not in response.headers


@pytest.mark.parametrize("action", ["approve", "reject", "skip", "rollback"])
def test_plan_stream_and_new_answer_preserve_step_columns(settings_api, action):
    c = settings_api
    fake = FakeLLM(reply(calls=[call(identifier="a"), call(identifier="b")]), reply("完成"))
    tools, handler, _ = registry()
    session = configure(c, fake, tools)
    events = stream(c, session["id"], {"content": "多步查询"})
    assert [kind for kind, _ in events] == ["plan"]
    plan = events[0][1]
    assert set(plan) == {"plan_id", "steps", "reason"}
    assert all(set(step) == {"seq", "tool", "summary", "gpu", "estimate_ms"} for step in plan["steps"])
    assert len(fake.calls) == 1 and handler.call_count == 0
    body = {"plan_id": plan["plan_id"], "action": action}
    if action != "approve":
        body["reason"] = "用户原因"
    if action in {"skip", "rollback"}:
        body["step_ref"] = 2
    assert c.client.post(f"{BASE}/{session['id']}/messages", json={"content": "暂停期间"}).status_code == 400
    result = stream(c, session["id"], body)
    assert result[-1][0] == "done"
    expected = 2 if action == "approve" else 0 if action == "reject" else 1
    assert handler.call_count == expected
    rows = c.client.get(f"{BASE}/{session['id']}/steps").json()["steps"]
    assert len(rows) == expected
    for row in rows:
        assert set(row) == {"seq", "tool", "status", "arguments_json", "result_digest", "result_summary", "latency_ms", "created_at"}
    assert c.client.post(f"{BASE}/{session['id']}/messages", json=body).status_code == 400


@pytest.mark.parametrize("body", [{"action": "skip", "step_ref": 2}, {"action": "reject"},
    {"action": "skip", "step_ref": "2", "reason": "原因"}, {"action": "skip", "step_ref": True, "reason": "原因"},
    {"action": "skip", "step_ref": 0, "reason": "原因"}, {"action": "rollback", "step_ref": 3, "reason": "原因"},
    {"action": "skip", "step_ref": 1, "reason": ""}, {"action": "reject", "reason": " "},
    {"action": "maybe"}, {"action": "approve", "step_ref": 1}, {"action": "approve", "reason": "原因"},
    {"action": "approve", "reason": None}, {"action": "reject", "step_ref": 1, "reason": "原因"},
    {"action": "approve", "content": "混合消息"}, {"action": "approve", "check_id": "x", "decision": "approve"}])
def test_plan_invalid_body_is_http_400_without_claim_or_execution(settings_api, body):
    c = settings_api
    fake = FakeLLM(reply(calls=[call(identifier="a"), call(identifier="b")]))
    tools, handler, _ = registry()
    session = configure(c, fake, tools)
    plan = stream(c, session["id"], {"content": "多步"})[0][1]
    body = {"plan_id": plan["plan_id"], **body}
    response = c.client.post(f"{BASE}/{session['id']}/messages", json=body)
    assert response.status_code == 400 and response.json()["error"] == "INVALID_REQUEST"
    other = c.client.post(BASE, json={}).json()["id"]
    assert c.client.post(f"{BASE}/{other}/messages", json={"plan_id": plan["plan_id"], "action": "approve"}).status_code == 400
    assert rounds(c.database)[0]["status"] == "plan_check"
    handler.assert_not_called()
    assert len(fake.calls) == 1
