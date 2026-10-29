"""Conversation acceptance: real local services, synthetic cubes, no provider IO.

The provider below is observation-driven: it takes every business identifier and
revision from tool results or the trusted task state. It never fabricates service
results, injects annotations, or advances through a prewritten response queue.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.database import connect_database
from backend.identity import EngineIdentity
from spectrumagent.agent import context as task_memory
from spectrumagent.agent.llm import ChatResult, LLMClient, OpenAICompatibleClient, ToolCall
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.tools import build_registry
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.app import create_app
from .test_state import FakeLLM, call, registry as simple_registry, reply


BASE = "/api/v1/agent/sessions"


def _events(client, session_id, content=None, **body):
    if content is not None:
        body["content"] = content
    response = client.post(f"{BASE}/{session_id}/messages", json=body)
    assert response.status_code == 200, response.text
    events = []
    for frame in response.text.split("\n\n"):
        if not frame.strip():
            continue
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    assert events, response.text
    return events


def _successful(events):
    assert not [data for kind, data in events if kind == "error"], events
    assert not [kind for kind, _ in events if kind in {"plan", "human_check"}], events
    assert events[-1][0] in {"done", "clarify"}, events
    return events[-1][1]


def _bind_builtin_recipe(c):
    """Test preparation: bind the built-in recipe through the real tool and observe it."""
    store = AgentStore(c.database)
    arguments = {"profile": "snv_sg1"}
    result = c.tools.invoke("preprocess.recipe_ensure", arguments)
    state = task_memory.observe(store.context(c.session_id), "preprocess.recipe_ensure", arguments, result)
    store.save_context(c.session_id, state)


def test_cold_first_message_lists_then_calls_model_and_bad_ordinal_does_not_relist(settings_api, tmp_path):
    import httpx
    from .conftest import audit_rows, mock_client

    c = settings_api
    datasets = DatasetRegistry(c.database)
    for index in range(3):
        header = tmp_path / f"cold-{index + 1}.hdr"
        header.with_suffix(".img").write_bytes(np.full((2, 2, 3), index + 1, dtype=np.float32).tobytes())
        header.write_text("ENVI\nsamples=2\nlines=2\nbands=3\ndata type=4\ninterleave=bip\nbyte order=0\n", encoding="utf-8")
        datasets.import_path(str(header), raw=True)
    response = c.client.post(BASE, json={})
    assert response.status_code == 200, response.text
    session_id = response.json()["id"]
    store = AgentStore(c.database)
    assert store.context(session_id) == {} and store.rounds(session_id) == [] and store.steps(session_id) == []
    before = len(audit_rows(c))

    def model_response(request):
        step, = store.steps(session_id)
        assert step["tool"] == "datasets.list" and step["tool_call_id"] is None
        state = store.context(session_id)
        items = state["catalogs"]["dataset"]["items"]
        assert len(items) == 3 and state["selected_cube_id"] == items[0]["id"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "已收到请求，请在画布指认一处 PP 种子。"},
                                                     "finish_reason": "stop"}]})

    provider, transport = mock_client(c, handler=model_response, session_id=session_id)
    c.app.state.agent_llm_factory = lambda _: provider
    events = _events(c.client, session_id, "对第一个数据标注 PP，其余背景，参数默认，保存后做预处理")
    _successful(events)
    assert [kind for kind, _ in events][:2] == ["step", "workspace"]
    assert events[0][1]["tool"] == "datasets.list"
    assert events[0][1]["pending_clarify"] == {"kind": "dataset", "reason": "stale", "asked": False}
    rows = audit_rows(c)
    assert len(rows) - before == 1 and transport.call_count == 1
    assert rows[-1]["session_id"] == session_id and rows[-1]["status"] == "ok" and rows[-1]["http_status"] == 200
    assert "annotations.prepare" in json.loads(rows[-1]["tool_names"])
    assert store.steps(session_id)[0]["tool_call_id"] is None
    print("L1b_C", json.dumps({"events": events, "llm_call_before": before, "llm_call_after": len(rows),
                               "llm_call_added": len(rows) - before, "controller_tool_call_id": None}, ensure_ascii=False))

    invalid = _events(c.client, session_id, "第 9 个数据")
    assert [kind for kind, _ in invalid] == ["workspace", "clarify"]
    assert invalid[-1][1]["pending_clarify"] == {"kind": "dataset", "reason": "not_found", "asked": True}
    assert invalid[-1][1]["question"] == "当前没有可确定的数据，请明确指认或先列出对应列表。"
    repeated = _events(c.client, session_id, "第 9 个数据")
    assert [kind for kind, _ in repeated] == ["workspace", "done"]
    assert repeated[-1][1]["content"] == "仍未确定，保持当前选择"
    assert len(store.steps(session_id)) == 1 and len(audit_rows(c)) == len(rows) and transport.call_count == 1
    print("L1b_D", json.dumps({"events": invalid, "repeat_events": repeated, "relisted": False,
                               "llm_call_added": len(audit_rows(c)) - len(rows)}, ensure_ascii=False))


@pytest.fixture
def conversation_case(gateway_case, tmp_path, monkeypatch):
    """Use the production app wiring; only the remote text model is substituted."""
    def forbid_remote(*args, **kwargs):
        raise AssertionError("Acceptance tests must not call a real provider")
    monkeypatch.setattr(OpenAICompatibleClient, "chat", forbid_remote)
    c = gateway_case
    datasets = DatasetRegistry(c.database)
    rng = np.random.default_rng(9017)
    axis = np.linspace(1000, 1700, 32)
    band = np.linspace(0, 1, 32)
    pp = .08 + .72 * np.exp(-((band - .22) / .17) ** 2)
    background = .08 + .72 * np.exp(-((band - .78) / .17) ** 2)
    cube_ids, headers = [], []
    for index in range(2):
        cube = np.empty((16, 16, 32), dtype=np.float32)
        cube[:, :8] = pp
        cube[:, 8:] = background
        cube += rng.normal(0, .002, cube.shape).astype(np.float32)
        header = tmp_path / f"sample-{81 + index:03d}.hdr"
        header.with_suffix(".img").write_bytes(cube.tobytes())
        header.write_text("ENVI\nsamples=16\nlines=16\nbands=32\ndata type=4\n"
                          "interleave=bip\nbyte order=0\nwavelength={" +
                          ",".join(map(str, axis)) + "}\n", encoding="utf-8")
        cube_ids.append(str(datasets.import_path(str(header), raw=True).datasets[0].id))
        headers.append(header)
    identity = EngineIdentity()
    app = create_app(c.paths, identity)
    tools = build_registry(catalogue_version=2, datasets=datasets,
                           runner=app.state.preprocess_runner,
                           comparison=app.state.preprocess_compare,
                           database=c.database, sessions=app.state.annotation_sessions,
                           diffusion=app.state.diffusion_engine)
    app.state.agent_tools = tools
    provider = WorkflowProvider()
    app.state.agent_llm_factory = lambda session_id: provider
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + identity.token
        response = client.post(BASE, json={})
        assert response.status_code == 200, response.text
        yield SimpleNamespace(paths=c.paths, database=c.database, app=app, client=client,
                              tools=tools, provider=provider, datasets=datasets,
                              cube_ids=cube_ids, headers=headers,
                              session_id=response.json()["id"],
                              sessions=app.state.annotation_sessions)


class WorkflowProvider(LLMClient):
    """Small test policy: decide from the observations, never service side effects."""
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools, *, stream=False):
        self.calls.append((deepcopy(messages), deepcopy(tools), stream))
        user_index = max(i for i, message in enumerate(messages) if message["role"] == "user")
        text = messages[user_index]["content"]
        names = {call_["id"]: call_["function"]["name"]
                 for message in messages for call_ in message.get("tool_calls", [])}
        observed = [(names.get(message["tool_call_id"]), json.loads(message["content"]))
                    for message in messages[user_index + 1:] if message["role"] == "tool"]
        state = {}
        for message in messages:
            if message["role"] == "system":
                try:
                    state.update(json.loads(message["content"]).get("task_state", {}))
                except (ValueError, TypeError):
                    pass

        def seen(name):
            return next((result for tool, result in reversed(observed) if tool == name), None)

        def invoke(name, **arguments):
            available = {tool["function"]["name"] for tool in tools or []}
            assert name in available, (name, available)
            return ChatResult(content=None, tool_calls=[ToolCall(
                id=f"workflow-{len(self.calls)}", name=name,
                arguments_json=json.dumps(arguments, ensure_ascii=False))], finish_reason="tool_calls")

        def finish(content):
            return ChatResult(content=content, tool_calls=[], finish_reason="stop")

        if text == "查看可用的数据集":
            listing = seen("datasets.list")
            if listing is None:
                return invoke("datasets.list")
            return finish("可选数据集已列出；请指定其中一项。")

        resolved = seen("datasets.resolve")
        if "第一个" in text and resolved is None:
            return invoke("datasets.resolve", query="第一个")
        if text.startswith("对前缀") and resolved is None:
            return invoke("datasets.resolve", query=text.split("：", 1)[1].split("，", 1)[0])
        cube_id = resolved.get("cube_id") if resolved else state.get("selected_cube_id")
        assert cube_id, (text, state, observed)

        if "比较" in text:
            recipe = seen("preprocess.recipe_ensure")
            if recipe is None:
                return invoke("preprocess.recipe_ensure", profile="snv")
            recipes = seen("preprocess.recipes")
            if recipes is None:
                return invoke("preprocess.recipes")
            compared = seen("preprocess.compare")
            if compared is None:
                default = next(recipes[f"recipe_{i}_version_id"]
                               for i in range(1, recipes["recipe_count"] + 1)
                               if recipes[f"recipe_{i}_is_default"])
                return invoke("preprocess.compare", cube_id=cube_id,
                              annotation_version_id=state["annotation_version_id"],
                              recipe_version_ids=[default, recipe["recipe_version_id"]])
            assert compared["run_count"] == 2, compared
            assert any(key.startswith("boundary_") for key in compared), compared
            return finish("两种配方已实际比较；Fisher 为主排序，跨算子 SNR 不直接比较。")

        if "预处理" in text:
            result = seen("preprocess.run_default")
            if result is None:
                return invoke("preprocess.run_default", cube_id=cube_id,
                              annotation_version_id=state.get("annotation_version_id"),
                              recipe_version_id=state.get("recipe_version_id"))
            if not state.get("annotation_version_id") or not state.get("recipe_version_id"):
                assert result["status"] == "need_version", result
                return finish("请明确标注版本与配方版本后继续预处理。")
            assert result["status"] == "succeeded", result
            return finish("默认预处理已完成，结果来自实际运行。")

        context = seen("annotations.context")
        if context is None:
            return invoke("annotations.context", cube_id=cube_id)
        if seen("annotations.ensure_labels") is None:
            return invoke("annotations.ensure_labels", cube_id=cube_id,
                          class_codes=["PP"], include_background=True)
        if not context["segmentation_ready"] and seen("annotations.prepare") is None:
            return invoke("annotations.prepare", cube_id=cube_id)
        proposal = seen("annotations.propose")
        accepts_preview = "接受候选" in text
        if proposal is None and accepts_preview:
            # The accepted reference must come from a prior actual preview, not
            # a new invocation hidden behind the user's acceptance message.
            proposal = next((json.loads(message["content"])
                             for message in reversed(messages[:user_index])
                             if message["role"] == "tool"
                             and names.get(message["tool_call_id"]) == "annotations.propose"
                             and json.loads(message["content"]).get("cube_id") == cube_id
                             and json.loads(message["content"]).get("status") == "preview"), None)
        if proposal is None:
            arguments = {"cube_id": cube_id, "class_code": "PP"}
            if state.get("gesture_ref"):
                arguments["gesture_ref"] = state["gesture_ref"]
            return invoke("annotations.propose", **arguments)
        if proposal["status"] == "need_seed":
            return finish("请在画布上点选一处 PP 作为种子；数据集、PP/背景类别及默认参数已确定。")
        automatic = any("自动执行" in message.get("content", "")
                        for message in messages if message["role"] == "user")
        if not automatic and not accepts_preview:
            return finish("候选已预览，草稿尚未修改。若范围正确，请回复接受候选。")
        applied = seen("annotations.apply_candidate")
        if applied is None:
            return invoke("annotations.apply_candidate", cube_id=cube_id,
                          candidate_ref=proposal["candidate_ref"], revision=proposal["revision"])
        background = seen("annotations.set_background")
        if background is None:
            return invoke("annotations.set_background", cube_id=cube_id, revision=applied["revision"])
        confirmed = seen("annotations.draft_confirm")
        if confirmed is None:
            return invoke("annotations.draft_confirm", cube_id=cube_id, revision=background["revision"])
        assert confirmed["version_id"]
        return finish("已根据 PP 种子标注前景，将其余空白设为背景，并保存标注版本。")


def test_dialogue_resolves_first_asks_only_for_seed_and_really_saves_then_preprocesses(conversation_case):
    c = conversation_case
    _successful(_events(c.client, c.session_id, "查看可用的数据集"))
    first = _successful(_events(c.client, c.session_id,
        "对第一个数据集标注，类别PP，其余背景，参数默认，自动执行。"))
    assert first["task_result"] == "needs_input"
    text = first.get("content", first.get("question", ""))
    assert "种子" in text and "请提供数据集" not in text
    task = AgentStore(c.database).context(c.session_id)
    selected = task["selected_cube_id"]
    assert selected == c.cube_ids[0]
    assert task["class_codes"] == ["PP"] and task["include_background"] is True
    assert task["use_defaults"] is True
    assert c.sessions.drafts.get(selected) is None
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0

    response = c.client.post(f"/api/v1/annotations/{selected}/gestures", json={"seed": {"point": [4, 2]}})
    assert response.status_code == 200, response.text
    gesture = response.json()["gesture_ref"]
    saved_result = _successful(_events(c.client, c.session_id, "这里是PP，按上述方案继续并保存。",
                        workspace={"cube_id": selected, "gesture_ref": gesture}))
    assert saved_result["task_result"] == "succeeded"
    working = c.sessions.working(selected)
    assert working["statistics"]["blank_pixels"] == 0
    assert working["statistics"]["uncertain_pixels"] == 0
    with connect_database(c.database) as db:
        labels = dict(db.execute("SELECT id,code FROM label"))
        assert db.execute("SELECT count(*) FROM annotation_version WHERE cube_id=?", (selected,)).fetchone()[0] == 1
    occupied = {labels[working["label_index"][str(i)]] for i in np.unique(working["label_map"])}
    assert occupied == {"PP", "BG"}
    pp_index = next(int(i) for i, label_id in working["label_index"].items() if labels[label_id] == "PP")
    assert working["label_map"][4, 2] == pp_index
    task = AgentStore(c.database).context(c.session_id)
    assert task["annotation_version_id"]
    saved = c.sessions.read_version(task["annotation_version_id"])
    np.testing.assert_array_equal(saved["label_map"], working["label_map"])

    _bind_builtin_recipe(c)
    processed_result = _successful(_events(c.client, c.session_id, f"对前缀：{selected[:8]}，用默认预处理"))
    assert processed_result["task_result"] == "succeeded"
    task = AgentStore(c.database).context(c.session_id)
    run = c.app.state.preprocess_runner.get(task["last_run_id"])
    assert run["status"] == "succeeded"
    assert run["cube_id"] == selected and run["annotation_version_id"] == task["annotation_version_id"]
    assert run["metrics"]["snr"]["n_pixels"] > 0
    compared_result = _successful(_events(c.client, c.session_id, "新建仅SNV配方，与默认配方比较"))
    assert compared_result["task_result"] == "succeeded"
    with connect_database(c.database) as db:
        comparison_runs = db.execute("SELECT status,recipe_version_id,metrics FROM preprocess_run WHERE cube_id=?",
                                     (selected,)).fetchall()
        assert len(comparison_runs) == 3
        assert all(row[0] == "succeeded" for row in comparison_runs)
        assert len({row[1] for row in comparison_runs}) == 2
        assert all(json.loads(row[2])["snr"]["n_pixels"] > 0 for row in comparison_runs)
    steps = AgentStore(c.database).steps(c.session_id)
    assert sum(step["tool"] == "datasets.list" for step in steps) == 1
    assert all(step["status"] == "ok" for step in steps)
    for messages, _, _ in c.provider.calls:
        wire = json.dumps(messages, ensure_ascii=False)
        assert "[[" not in wire and str(c.headers[0]) not in wire


def test_history_keeps_recent_ten_rounds_and_assistant_questions(gateway_case):
    store = AgentStore(gateway_case.database)
    session = store.create_session()["id"]
    tools = simple_registry()[0]
    for index in range(12):
        fake = FakeLLM(reply(f"assistant-marker-{index:02d}"))
        list(StateMachine(store, session, fake, tools).message(content=f"user-marker-{index:02d}"))
    fake = FakeLLM(reply("继续"))
    list(StateMachine(store, session, fake, tools).message(content="user-marker-12"))
    messages = fake.calls[0][0]
    contents = [message.get("content") for message in messages]
    assert "user-marker-00" not in contents and "user-marker-01" not in contents
    assert "user-marker-02" in contents and "user-marker-11" in contents
    assert "assistant-marker-11" in contents


def test_switching_workspace_does_not_reuse_a_different_cubes_gesture(conversation_case):
    c = conversation_case
    first, second = c.cube_ids
    gesture = c.sessions.store_gesture(first, {"point": [4, 2]})
    _successful(_events(c.client, c.session_id,
                        "对当前数据标注，类别PP，其余背景，参数默认，自动执行。",
                        workspace={"cube_id": first, "gesture_ref": gesture}))
    assert AgentStore(c.database).context(c.session_id)["annotation_version_id"]
    result = _successful(_events(c.client, c.session_id,
                        "对当前数据标注，类别PP，其余背景，参数默认，自动执行。",
                        workspace={"cube_id": second}))
    assert "种子" in result.get("content", result.get("question", ""))
    task = AgentStore(c.database).context(c.session_id)
    assert task["selected_cube_id"] == second
    assert not task.get("gesture_ref")
    assert not task.get("annotation_version_id")
    assert c.sessions.drafts.get(second) is None


def test_preview_without_auto_authorization_waits_for_a_later_acceptance(conversation_case):
    c = conversation_case
    cube_id = c.cube_ids[0]
    gesture = c.sessions.store_gesture(cube_id, {"point": [4, 2]})
    preview = _successful(_events(c.client, c.session_id,
        "对当前数据标注PP，其余背景，参数默认，先预览候选。",
        workspace={"cube_id": cube_id, "gesture_ref": gesture}))
    assert preview["task_result"] == "needs_review"
    assert "尚未修改" in preview.get("content", preview.get("question", ""))
    assert c.sessions.drafts.get(cube_id) is None
    before = AgentStore(c.database).steps(c.session_id)
    proposed = next(json.loads(step["result_summary"]) for step in before if step["tool"] == "annotations.propose")
    assert proposed["status"] == "preview"
    _successful(_events(c.client, c.session_id, "接受候选，自动执行其余背景并保存。"))
    after = AgentStore(c.database).steps(c.session_id)
    assert sum(step["tool"] == "annotations.propose" for step in after) == 1
    applied = next(json.loads(step["arguments_json"]) for step in after if step["tool"] == "annotations.apply_candidate")
    assert applied["candidate_ref"] == proposed["candidate_ref"]
    assert AgentStore(c.database).context(c.session_id)["annotation_version_id"]


def test_explicit_second_item_wins_over_the_previously_visible_workspace(conversation_case):
    c = conversation_case
    _successful(_events(c.client, c.session_id, "查看可用的数据集"))
    result = _successful(_events(c.client, c.session_id,
        "对第二个数据集标注PP，其余背景，参数默认，自动执行。",
        workspace={"cube_id": c.cube_ids[0]}))
    task = AgentStore(c.database).context(c.session_id)
    assert task["selected_cube_id"] == c.cube_ids[1]
    assert task["authorization_cube_id"] == c.cube_ids[1]
    assert "种子" in result.get("content", result.get("question", ""))
    assert c.sessions.drafts.get(c.cube_ids[0]) is None
    assert c.sessions.drafts.get(c.cube_ids[1]) is None


@pytest.mark.parametrize("tool", ["annotations.draft_confirm", "annotations.apply_candidate"])
def test_model_cannot_spend_cube_a_authorization_on_cube_b(conversation_case, tool):
    c = conversation_case
    first, second = c.cube_ids
    body = {"cube_id": second, "revision": 1}
    if tool == "annotations.apply_candidate":
        body["candidate_ref"] = "c-from-a-different-dataset"
    fake = FakeLLM(reply(calls=[call(tool, json.dumps(body), "cross-cube")]))
    c.app.state.agent_llm_factory = lambda session_id: fake
    events = _events(c.client, c.session_id, "仅操作当前数据，自动执行并保存。",
                     workspace={"cube_id": first})
    assert events[-1][0] == "error", events
    assert events[-1][1]["code"] == "TASK_DATASET_MISMATCH", events
    task = AgentStore(c.database).context(c.session_id)
    assert task["selected_cube_id"] == task["authorization_cube_id"] == first
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_draft").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0
    assert c.sessions.drafts.get(first) is None and c.sessions.drafts.get(second) is None


@pytest.mark.parametrize("content,initial,forbidden_key", [
    ("不自动执行", {"auto_execute": True, "authorization_cube_id": "cube-a"}, "authorization_cube_id"),
    ("无法接受", {"candidate_ref": "candidate-a"}, "accepted_candidate_ref"),
    ("无法接受", {"candidate_ref": "candidate-a", "accepted_candidate_ref": "candidate-a"}, "accepted_candidate_ref"),
    ("不要用默认参数", {"use_defaults": True}, "use_defaults"),
])
def test_negated_instructions_do_not_grant_permissions(content, initial, forbidden_key):
    state = task_memory.remember_user({"selected_cube_id": "cube-a", **initial}, content)
    assert not state.get(forbidden_key)
    if "自动" in content:
        assert not state.get("auto_execute")


@pytest.mark.parametrize("content,tool,extra", [
    ("无法接受这个候选", "annotations.apply_candidate", {"candidate_ref": "c-declined"}),
    ("不要保存", "annotations.draft_confirm", {}),
])
def test_explicit_refusal_overrides_an_earlier_auto_execute_grant(conversation_case, content, tool, extra):
    c = conversation_case
    selected = c.cube_ids[0]
    store = AgentStore(c.database)
    store.save_context(c.session_id, {"selected_cube_id": selected,
        "auto_execute": True, "authorization_cube_id": selected,
        "candidate_ref": "c-declined", "accepted_candidate_ref": "c-declined",
        "save_requested": selected})
    fake = FakeLLM(reply(calls=[call(tool, json.dumps({"cube_id": selected, "revision": 1, **extra}), "refused-write")]))
    c.app.state.agent_llm_factory = lambda session_id: fake
    events = _events(c.client, c.session_id, content, workspace={"cube_id": selected})
    assert events[-1][0] == "clarify", events
    assert "未保存" in events[-1][1]["question"]
    assert store.steps(c.session_id) == []
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_draft").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0
    remembered = store.context(c.session_id)
    if extra:
        assert not remembered.get("accepted_candidate_ref")
        assert remembered["rejected_candidate_ref"] == "c-declined"
    else:
        assert not remembered.get("save_requested")
        assert remembered["save_denied"] == selected


@pytest.mark.parametrize("tool,result", [
    ("datasets.describe", {"dataset_id": "cube-b", "cube_id": "cube-b", "display_name": "Other cube"}),
    ("preprocess.run_get", {"cube_id": "cube-b", "run_id": "run-b", "status": "succeeded",
                            "annotation_version_id": "version-b", "recipe_version_id": "recipe-b"}),
])
def test_inspecting_another_cube_does_not_replace_the_current_task(tool, result):
    initial = {"selected_cube_id": "cube-a", "display_name": "Current cube", "gesture_ref": "g-current",
               "annotation_version_id": "version-a", "recipe_version_id": "recipe-a", "last_run_id": "run-a",
               "auto_execute": True, "authorization_cube_id": "cube-a", "stage": "annotation"}
    assert task_memory.observe(initial, tool, {}, result) == initial


@pytest.mark.parametrize("limit,error_code", [(None, "AGENT_NO_PROGRESS"), (2, "AGENT_BUDGET_EXCEEDED")])
def test_repeating_provider_is_bounded_without_writes(conversation_case, monkeypatch, limit, error_code):
    c = conversation_case
    if limit is not None:
        monkeypatch.setattr("spectrumagent.agent.state.MAX_WORKFLOW_BATCHES", limit)

    class RepeatingProvider(LLMClient):
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools, *, stream=False):
            self.calls += 1
            return reply(calls=[call(identifier=f"repeat-{self.calls}")])

    fake = RepeatingProvider()
    c.app.state.agent_llm_factory = lambda session_id: fake
    events = _events(c.client, c.session_id, "查看可用的数据集")
    assert events[-1][0] == "error", events
    assert events[-1][1]["code"] == error_code, events
    assert events[-1][1]["task_result"] == "failed", events
    assert fake.calls == 3
    steps = AgentStore(c.database).steps(c.session_id)
    assert len(steps) == 2 and all(step["tool"] == "datasets.list" and step["status"] == "ok" for step in steps)
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_draft").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0


def test_history_pairs_valid_results_after_a_rejected_call(gateway_case):
    store = AgentStore(gateway_case.database)
    session = store.create_session()["id"]
    tools = simple_registry()[0]
    fake = FakeLLM(reply(calls=[call(arguments='{"extra":true}', identifier="bad"),
                                call(identifier="valid")]), reply("第一轮完成"))
    list(StateMachine(store, session, fake, tools).message(content="列出数据"))
    next_model = FakeLLM(reply("继续"))
    list(StateMachine(store, session, next_model, tools).message(content="使用第一项"))
    history = next_model.calls[0][0]
    result = next(message for message in history if message.get("tool_call_id") == "valid")
    assert json.loads(result["content"]) == {"count": 2}
    pending = []
    for message in history:
        if message.get("tool_calls"):
            assert not pending
            pending = [item["id"] for item in message["tool_calls"]]
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
    assert not pending


def test_textual_dsml_is_a_protocol_error_without_tool_execution(gateway_case):
    store = AgentStore(gateway_case.database)
    session = store.create_session()["id"]
    tools, handler, _ = simple_registry()
    fake = FakeLLM(reply('<｜DSML｜tool_calls><｜DSML｜invoke name="tools.list"></｜DSML｜invoke>'))
    events = list(StateMachine(store, session, fake, tools).message(content="标注数据"))
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "LLM_TOOL_PROTOCOL"
    handler.assert_not_called()
    assert store.steps(session) == []


def test_history_after_rejected_confirmation_has_no_unanswered_tool_calls(gateway_case):
    store = AgentStore(gateway_case.database)
    session = store.create_session()["id"]
    tools = simple_registry()[0]
    fake = FakeLLM(reply(calls=[
        call("annotations.draft_confirm", '{"cube_id":"cube-1","revision":1}', "confirm"),
        call(identifier="unexecuted-after-rejection")]))
    machine = StateMachine(store, session, fake, tools)
    plan = list(machine.message(content="确认并继续"))[-1][1]
    check = list(machine.message(plan_id=plan["plan_id"], action="approve"))[-1][1]
    rejected = list(machine.message(check_id=check["check_id"], decision="reject"))
    assert rejected[-1][0] == "done"
    next_model = FakeLLM(reply("保持未保存状态"))
    list(StateMachine(store, session, next_model, tools).message(content="先不要保存"))
    pending = []
    for message in next_model.calls[0][0]:
        if message.get("tool_calls"):
            assert not pending
            pending = [item["id"] for item in message["tool_calls"]]
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending
            pending.remove(message["tool_call_id"])
        else:
            assert not pending
    assert not pending


def test_pending_save_can_be_confirmed_by_a_plain_chinese_reply(conversation_case):
    c = conversation_case
    cube_id = c.cube_ids[0]
    c.tools.invoke("annotations.ensure_labels", {"cube_id": cube_id, "class_codes": ["PP"], "include_background": True})
    c.tools.invoke("annotations.prepare", {"cube_id": cube_id})
    gesture = c.sessions.store_gesture(cube_id, {"point": [4, 2]})
    proposal = c.tools.invoke("annotations.propose", {"cube_id": cube_id, "class_code": "PP", "gesture_ref": gesture})
    applied = c.tools.invoke("annotations.apply_candidate", {"cube_id": cube_id,
        "candidate_ref": proposal["candidate_ref"], "revision": proposal["revision"]})
    background = c.tools.invoke("annotations.set_background", {"cube_id": cube_id, "revision": applied["revision"]})
    expected = c.sessions.working(cube_id)["label_map"]
    fake = FakeLLM(reply(calls=[call("annotations.draft_confirm", json.dumps({
        "cube_id": cube_id, "revision": background["revision"]}), "pending-save")]),
        reply("当前标注版本已保存。"))
    c.app.state.agent_llm_factory = lambda session_id: fake
    pending = _events(c.client, c.session_id, "请结束这次标注流程。", workspace={"cube_id": cube_id})
    check = next(data for kind, data in pending if kind == "human_check")
    store = AgentStore(c.database)
    pending_step = next(step for step in store.steps(c.session_id) if step["id"] == check["check_id"])
    assert pending_step["status"] == "human_check_pending"
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version").fetchone()[0] == 0

    _successful(_events(c.client, c.session_id, "确认保存"))
    steps = store.steps(c.session_id)
    assert len(steps) == 1 and steps[0]["id"] == check["check_id"] and steps[0]["status"] == "ok"
    version_id = json.loads(steps[0]["result_summary"])["version_id"]
    np.testing.assert_array_equal(c.sessions.read_version(version_id)["label_map"], expected)
    with connect_database(c.database) as db:
        assert db.execute("SELECT count(*) FROM annotation_version WHERE cube_id=?", (cube_id,)).fetchone()[0] == 1
    assert not store.context(c.session_id).get("auto_execute")
    assert store.session(c.session_id)["auto_confirm"] == 0


def test_pending_plan_can_be_approved_by_a_plain_chinese_reply(conversation_case):
    c = conversation_case
    cube_id = c.cube_ids[0]
    fake = FakeLLM(reply(calls=[
        call("annotations.ensure_labels", json.dumps({"cube_id": cube_id,
            "class_codes": ["PP"], "include_background": True}), "prepare-labels"),
        call("annotations.prepare", json.dumps({"cube_id": cube_id}), "prepare-segments")]),
        reply("分割已生成，请指认一处 PP 种子。"))
    c.app.state.agent_llm_factory = lambda session_id: fake
    pending = _events(c.client, c.session_id,
        "准备当前数据的标注，类别PP，其余背景，参数默认。", workspace={"cube_id": cube_id})
    plan = next(data for kind, data in pending if kind == "plan")
    store = AgentStore(c.database)
    assert store.steps(c.session_id, plan["plan_id"]) == []
    assert c.sessions._state(cube_id).segments is None

    _successful(_events(c.client, c.session_id, "批准执行"))
    original_steps = store.steps(c.session_id, plan["plan_id"])
    assert [step["tool"] for step in original_steps] == ["annotations.ensure_labels", "annotations.prepare"]
    assert all(step["status"] == "ok" for step in original_steps)
    assert c.sessions._state(cube_id).segments.shape == (16, 16)
    assert c.sessions.drafts.get(cube_id) is None
    assert not store.context(c.session_id).get("auto_execute")
    assert store.session(c.session_id)["auto_confirm"] == 0


def test_task_result_uses_local_need_version_without_changing_context(conversation_case):
    c = conversation_case
    cube_id = c.cube_ids[0]
    fake = FakeLLM(reply(calls=[call("preprocess.run_default", json.dumps({"cube_id": cube_id}), "needs-version")]),
                   reply("已完成并保存。"))  # Model prose must not manufacture success.
    c.app.state.agent_llm_factory = lambda session_id: fake
    events = _events(c.client, c.session_id, "使用默认预处理", workspace={"cube_id": cube_id})
    step = next(data for kind, data in events if kind == "step")
    assert step["result_summary"]["status"] == "need_version"
    assert _successful(events)["task_result"] == "needs_input"
    context = AgentStore(c.database).context(c.session_id)
    assert "last_status" not in context and "next_action" not in context and "last_error" not in context


@pytest.mark.parametrize("stored_status,expected", [("succeeded", "succeeded"), ("failed", "working")])
def test_task_result_reads_the_actual_run_not_the_last_model_reply(conversation_case, stored_status, expected):
    c = conversation_case
    cube_id = c.cube_ids[0]
    gesture = c.sessions.store_gesture(cube_id, {"point": [4, 2]})
    _successful(_events(c.client, c.session_id, "对当前数据标注PP，其余背景，参数默认，自动执行并保存。",
                        workspace={"cube_id": cube_id, "gesture_ref": gesture}))
    _bind_builtin_recipe(c)
    _successful(_events(c.client, c.session_id, "使用默认预处理"))
    context = AgentStore(c.database).context(c.session_id)
    with connect_database(c.database) as db:
        db.execute("UPDATE preprocess_run SET status=? WHERE id=?", (stored_status, context["last_run_id"]))
    c.app.state.agent_llm_factory = lambda session_id: FakeLLM(reply("全部处理完成。"))
    assert _successful(_events(c.client, c.session_id, "查看目前的任务结果"))["task_result"] == expected


def _reference_fixture(c, *, with_candidate=False):
    """Prepare real service objects; test providers never invent IDs or results."""
    store = AgentStore(c.database)
    row = store.new_round(c.session_id, "引用层测试准备", [], "done")
    state = task_memory.observe(store.context(c.session_id), "datasets.list", {}, c.tools.invoke("datasets.list", {}), row["id"])
    for profile in ("raw", "snv"):
        c.tools.invoke("preprocess.recipe_ensure", {"profile": profile})
    state = task_memory.observe(state, "preprocess.recipes", {}, c.tools.invoke("preprocess.recipes", {}), row["id"])
    if with_candidate:
        cube_id = c.cube_ids[1]
        c.tools.invoke("annotations.ensure_labels", {"cube_id": cube_id, "class_codes": ["PP"], "include_background": True})
        c.tools.invoke("annotations.prepare", {"cube_id": cube_id})
        gesture = c.sessions.store_gesture(cube_id, {"point": [4, 2]})
        arguments = {"cube_id": cube_id, "class_code": "PP", "gesture_ref": gesture}
        proposed = c.tools.invoke("annotations.propose", arguments)
        applied = c.tools.invoke("annotations.apply_candidate", {"cube_id": cube_id,
            "candidate_ref": proposed["candidate_ref"], "revision": proposed["revision"]})
        background = c.tools.invoke("annotations.set_background", {"cube_id": cube_id, "revision": applied["revision"]})
        c.tools.invoke("annotations.draft_confirm", {"cube_id": cube_id, "revision": background["revision"]})
        state = task_memory.observe(state, "annotations.context", {"cube_id": cube_id},
                                   c.tools.invoke("annotations.context", {"cube_id": cube_id}), row["id"])
        state = task_memory.observe(state, "annotations.propose", arguments,
                                   c.tools.invoke("annotations.propose", arguments), row["id"])
    store.save_context(c.session_id, state)
    return store, state


def _reference_trace(label, events, state):
    text = events[-1][1].get("content", events[-1][1].get("question", ""))
    trace = {"case": label, "events": events, "pending_clarify": state.get("pending_clarify"),
             "relisted": any(name == "step" and data["tool"] in {"datasets.list", "preprocess.recipes", "annotations.context"}
                             for name, data in events), "refresh_text_position": text.find("已刷新列表"),
             "selected_cube_id": state.get("selected_cube_id"), "annotation_version_id": state.get("annotation_version_id")}
    print("L1_SSE", json.dumps(trace, ensure_ascii=False))
    if directory := os.environ.get("L1_EVENT_EVIDENCE_DIR"):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{label}.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return trace


def test_l1_f_asks_once_then_holds_without_model_or_relist(conversation_case):
    c = conversation_case
    store, initial = _reference_fixture(c, with_candidate=True)
    def forbidden(*args):
        raise AssertionError("deterministic clarification must not call a provider")
    c.app.state.agent_llm_factory = lambda session_id: SimpleNamespace(chat=forbidden)
    first = _events(c.client, c.session_id, "接受第二个候选")
    asked = store.context(c.session_id)
    assert [name for name, _ in first] == ["workspace", "clarify"]
    assert first[-1][1]["question"] == "当前只有一个候选，是指它吗？"
    assert asked["pending_clarify"] == {"kind": "candidate", "reason": "only_one", "asked": True}
    _reference_trace("F-first", first, asked)
    held = _events(c.client, c.session_id, "第二个")
    after = store.context(c.session_id)
    assert [name for name, _ in held] == ["workspace", "done"]
    assert held[-1][1]["content"] == "仍未确定，保持当前选择"
    assert "pending_clarify" not in after
    assert after == {key: value for key, value in asked.items() if key != "pending_clarify"}
    assert after["annotation_version_id"] == initial["annotation_version_id"]
    assert not _reference_trace("F-repeat", held, after)["relisted"]
    assert store.steps(c.session_id) == []


def test_l1_e_plain_confirmation_accepts_only_candidate_without_clearing_annotation(conversation_case):
    c = conversation_case
    store, initial = _reference_fixture(c, with_candidate=True)
    _events(c.client, c.session_id, "接受第二个候选")
    events = _events(c.client, c.session_id, "就是这个")
    after = store.context(c.session_id)
    assert after["accepted_candidate_ref"] == initial["candidate_ref"]
    assert after["annotation_version_id"] == initial["annotation_version_id"]
    assert "第 1 个候选：PP 候选 1（C1）" in events[-1][1]["content"]


def test_l1_i_legacy_session_refreshes_once_with_visible_mapping(conversation_case):
    c = conversation_case
    store = AgentStore(c.database)
    actual = c.tools.invoke("datasets.list", {})
    # Deliberately reverse legacy indices: refresh must use the current tool output.
    legacy = [{"index": 1, "id": c.cube_ids[1], "ref": "D1", "name": "旧序号二"},
              {"index": 2, "id": c.cube_ids[0], "ref": "D2", "name": "旧序号一"}]
    store.save_context(c.session_id, {"dataset_catalog": legacy, "future_l2_key": "preserved"})
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy ordinal refresh must be deterministic")
    c.app.state.agent_llm_factory = lambda session_id: SimpleNamespace(chat=forbidden)
    events = _events(c.client, c.session_id, "第二个")
    after = store.context(c.session_id)
    assert [name for name, _ in events] == ["step", "workspace", "done"]
    assert events[0][1]["tool"] == "datasets.list"
    assert events[0][1]["pending_clarify"] == {"kind": "dataset", "reason": "stale", "asked": False}
    assert events[0][1]["result_summary"] == actual
    assert after["selected_cube_id"] == c.cube_ids[1] != legacy[1]["id"]
    assert after["future_l2_key"] == "preserved"
    assert after["dataset_catalog"][1]["id"] == actual["dataset_2_id"]
    assert events[-1][1]["content"] == "已刷新列表，第 2 个现在是 sample-082（D2）"
    assert _reference_trace("I-refresh", events, after)["refresh_text_position"] == 0
    step = store.steps(c.session_id)[0]
    assert step["tool_call_id"] is None  # A controller read must not become L0 native-model evidence.
    again = _events(c.client, c.session_id, "第二个")
    assert not _reference_trace("I-repeat", again, store.context(c.session_id))["relisted"]
    assert len(store.steps(c.session_id)) == 1


def test_l1_four_step_demo_keeps_dataset_for_recipe_and_candidate_ordinals(conversation_case):
    c = conversation_case
    store, state = _reference_fixture(c)
    provider = FakeLLM(reply(calls=[call("datasets.list", "{}", "demo-list")]), reply("可选数据：D1 sample-081、D2 sample-082。"))
    c.app.state.agent_llm_factory = lambda session_id: provider
    events = _events(c.client, c.session_id, "有哪些数据")
    _reference_trace("demo-1-list", events, store.context(c.session_id))
    events = _events(c.client, c.session_id, "选第二份数据")
    selected = store.context(c.session_id)["selected_cube_id"]
    assert selected == c.cube_ids[1]
    assert events[-1][1]["content"] == "已选第 2 份数据：sample-082（D2）"
    _reference_trace("demo-2-data", events, store.context(c.session_id))
    events = _events(c.client, c.session_id, "用第二个配方")
    after = store.context(c.session_id)
    assert after["selected_cube_id"] == selected
    assert events[-1][1]["content"] == "第 2 个配方：SNV（P2）"
    assert after["recipe_version_id"] == after["catalogs"]["recipe"]["items"][1]["id"]
    selected_recipe = after["recipe_version_id"]
    _reference_trace("demo-3-recipe", events, after)
    # A real preview already exists when the fourth demonstration message is sent.
    _, prepared = _reference_fixture(c, with_candidate=True)
    events = _events(c.client, c.session_id, "接受第二个候选")
    after = store.context(c.session_id)
    assert after["selected_cube_id"] == selected
    assert after["annotation_version_id"] == prepared["annotation_version_id"]
    assert after["recipe_version_id"] == selected_recipe
    assert events[-1][1]["question"] == "当前只有一个候选，是指它吗？"
    _reference_trace("demo-4-candidate", events, after)
    assert len(provider.calls) == 2


def test_l1_g_need_seed_bare_ordinal_asks_once_without_selecting_data(conversation_case):
    c = conversation_case
    store, state = _reference_fixture(c)
    state["next_action"] = "need_seed"
    store.save_context(c.session_id, state)
    def forbidden(*args, **kwargs):
        raise AssertionError("missing reference scope must not call a model")
    c.app.state.agent_llm_factory = lambda session_id: SimpleNamespace(chat=forbidden)
    events = _events(c.client, c.session_id, "第二个")
    assert [name for name, _ in events] == ["clarify"]
    assert events[-1][1]["pending_clarify"] == {"kind": None, "reason": "not_found", "asked": True}
    assert store.context(c.session_id).get("selected_cube_id") is None
    held = _events(c.client, c.session_id, "第二个")
    assert [name for name, _ in held] == ["done"]
    assert "保持当前选择" in held[-1][1]["content"]
    assert store.context(c.session_id).get("selected_cube_id") is None
    assert store.steps(c.session_id) == []


def test_l1_region_edit_request_continues_to_model_instead_of_only_echoing_a_choice(conversation_case):
    c = conversation_case
    store, state = _reference_fixture(c, with_candidate=True)
    assert len(state["catalogs"]["region"]["items"]) >= 2
    provider = FakeLLM(reply("编辑请求已进入业务编排。"))
    c.app.state.agent_llm_factory = lambda session_id: provider
    events = _events(c.client, c.session_id, "删除第二个区域")
    assert len(provider.calls) == 1
    assert "编辑请求已进入业务编排" in events[-1][1]["question"]
    assert store.context(c.session_id)["selected_cube_id"] == state["selected_cube_id"]
