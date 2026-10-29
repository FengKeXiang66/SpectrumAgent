"""L2 A-K: stage boundaries and confirmed versions, real local services, no remote IO."""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from backend.database import connect_database
from spectrumagent.agent import context as memory
from spectrumagent.agent.skill import ensure_workflow_skill, upgrade_builtin_sessions
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.task import CONTEXT_KEYS, evaluate_task
from spectrumagent.agent.tools import build_registry
from .test_conversation_workflows import (
    WorkflowProvider, _events, _successful, conversation_case,
)
from .test_state import FakeLLM, call, registry as simple_registry, reply


def _evidence(case, value):
    print(f"L2_{case}: " + json.dumps(value, ensure_ascii=False))


def _trace(events):
    return [{"event": kind, **{key: data[key] for key in ("tool", "task_result", "question") if key in data}}
            for kind, data in events]


def _run_count(c):
    with connect_database(c.database) as db:
        return db.execute("SELECT count(*) FROM preprocess_run").fetchone()[0]


def _bound_run(c, run_id):
    with connect_database(c.database) as db:
        row = db.execute("SELECT id,annotation_version_id,recipe_version_id,status FROM preprocess_run WHERE id=?",
                         (run_id,)).fetchone()
    return dict(zip(("run_id", "annotation_version_id", "recipe_version_id", "status"), row))


def _select_recipe(c):
    """Show the real recipe directory, then choose P2 through the HTTP/SSE route."""
    c.tools.invoke("preprocess.recipe_ensure", {"profile": "snv"})
    c.app.state.agent_llm_factory = lambda _: FakeLLM(
        reply(calls=[call("preprocess.recipes")]), reply("请选择配方。"))
    _successful(_events(c.client, c.session_id, "列出可用配方", workspace={"cube_id": c.cube_ids[0]}))
    store = AgentStore(c.database)
    expected = store.context(c.session_id)["catalogs"]["recipe"]["items"][1]["id"]
    _successful(_events(c.client, c.session_id, "用第二个配方"))
    assert store.context(c.session_id)["recipe_version_id"] == expected
    c.app.state.agent_llm_factory = lambda _: c.provider
    return expected


def _annotate(c, content="标注PP，其余背景，参数默认，自动执行并保存。"):
    cube_id = c.cube_ids[0]
    gesture = c.sessions.store_gesture(cube_id, {"point": [4, 2]})
    events = _events(c.client, c.session_id, content,
                     workspace={"cube_id": cube_id, "gesture_ref": gesture})
    _successful(events)
    saved = next(data["result_summary"]["version_id"] for kind, data in events
                 if kind == "step" and data["tool"] == "annotations.draft_confirm")
    return events, saved


def _save_newer_annotation(c):
    cube_id = c.cube_ids[0]
    gesture = c.sessions.store_gesture(cube_id, {"point": [4, 2]})
    context = c.tools.invoke("annotations.context", {"cube_id": cube_id})
    marked = c.tools.invoke("annotations.mark_region", {"cube_id": cube_id,
        "revision": context["revision"], "gesture_ref": gesture, "action": "uncertain"})
    return c.tools.invoke("annotations.draft_confirm", {"cube_id": cube_id, "revision": marked["revision"]})["version_id"]


class CompositeProvider(WorkflowProvider):
    """Use the annotation policy until saved, then request the pending preprocess stage."""
    def chat(self, messages, tools, *, stream=False):
        state = json.loads(messages[1]["content"])["task_state"]
        if not {"annotation", "save"} <= set(state.get("stages_done") or ()):
            annotation_messages = deepcopy(messages)
            user_index = max(i for i, message in enumerate(annotation_messages) if message["role"] == "user")
            annotation_messages[user_index]["content"] = annotation_messages[user_index]["content"].replace("预处理", "后续处理")
            return super().chat(annotation_messages, tools, stream=stream)
        self.calls.append((deepcopy(messages), deepcopy(tools), stream))
        if "preprocess" not in state.get("stages_done", []):
            # Deliberately omit both Optional IDs: validate must run before injection.
            return reply(calls=[call("preprocess.run_default", json.dumps({"cube_id": state["selected_cube_id"]}),
                                    f"composite-{len(self.calls)}")])
        return reply("刚保存的标注已按所选配方完成预处理。")


@pytest.mark.parametrize("negation", ["不要", "不用", "先不", "暂不", "别", "先不要"])
def test_stage_requests_append_and_negation_wins_without_mutating_input(negation):
    initial = memory.remember_user({}, "标注后保存，做预处理并对比")
    before = deepcopy(initial)
    state = memory.remember_user(initial, f"{negation}预处理")
    assert initial == before
    assert state["requested_stages"] == ["annotation", "save", "compare"]
    assert state["intent"] == "annotation"
    state = memory.remember_user(state, "跑一下")
    assert state["requested_stages"] == ["annotation", "save", "preprocess", "compare"]
    assert memory.remember_user({}, "执行预处理")["intent"] == "preprocess"


def test_stage_keys_clear_only_when_dataset_changes_and_are_registered():
    state = {"selected_cube_id": "cube-a", "requested_stages": ["annotation", "save", "preprocess"],
             "stages_done": ["annotation", "save"]}
    before = deepcopy(state)
    assert memory.select(state, "cube-a") is False and state == before
    assert memory.select(state, "cube-b") is True
    assert "requested_stages" not in state and "stages_done" not in state
    assert {"requested_stages", "stages_done"} <= CONTEXT_KEYS
    assert len(memory.CLEAR_ON_DATASET) == 11


def test_stages_advance_only_for_successful_service_results_and_compound_completion():
    state = {"requested_stages": ["annotation", "save", "preprocess"]}
    state = memory.observe(state, "annotations.draft_confirm", {}, {"version_id": "v1"})
    assert state["stages_done"] == ["annotation", "save"]
    assert evaluate_task(state, {}) == "working"  # I: saved is not the whole compound task.
    assert "preprocess" not in memory.observe(state, "preprocess.run_default", {}, {"status": "failed"})["stages_done"]
    state = memory.observe(state, "preprocess.run_default", {}, {"run_id": "r1", "status": "succeeded"})
    assert set(state["stages_done"]) == {"annotation", "save", "preprocess"}
    assert evaluate_task(state, {"run_status": "succeeded"}) == "succeeded"
    assert evaluate_task({"annotation_version_id": "v1"}, {}) == "succeeded"


def test_comparison_with_runs_advances_compare_and_preserves_completed_stages():
    state = {"stages_done": ["annotation", "save", "preprocess"]}
    before = deepcopy(state)
    result = memory.observe(state, "preprocess.compare", {}, {"run_count": 2})
    assert set(result["stages_done"]) == {"annotation", "save", "preprocess", "compare"}
    assert state == before


def test_comparison_without_runs_does_not_advance_compare():
    state = {"stages_done": ["annotation", "save", "preprocess"]}
    before = deepcopy(state)
    result = memory.observe(state, "preprocess.compare", {}, {"run_count": 0})
    assert "compare" not in result["stages_done"]
    assert result == before and state == before


@pytest.mark.parametrize("state,artifacts", [({"next_action": "need_version"}, {}), ({}, {"last_status": "need_version"})])
def test_missing_version_needs_input_without_mutating_context(state, artifacts):
    before = deepcopy((state, artifacts))
    assert evaluate_task(state, artifacts) == "needs_input"
    assert (state, artifacts) == before


def test_a_annotation_only_saves_without_starting_preprocess(conversation_case):
    c = conversation_case
    before = _run_count(c)
    events, saved = _annotate(c)
    state = AgentStore(c.database).context(c.session_id)
    assert state["requested_stages"] == ["annotation", "save"]
    assert state["stages_done"] == ["annotation", "save"]
    assert state["annotation_version_id"] == saved
    assert _run_count(c) == before
    assert events[-1][1]["task_result"] == "succeeded"
    _evidence("A", {"events": _trace(events), "requested_stages": state["requested_stages"],
                    "runs_before": before, "runs_after": _run_count(c)})


def test_b_compound_request_binds_just_saved_annotation_and_chosen_recipe(conversation_case):
    c = conversation_case
    recipe_id = _select_recipe(c)
    provider = CompositeProvider()
    c.app.state.agent_llm_factory = lambda _: provider
    events, saved = _annotate(c, "标注PP，其余背景，参数默认，自动执行并保存后做预处理。")
    state = AgentStore(c.database).context(c.session_id)
    row = _bound_run(c, state["last_run_id"])
    assert row["annotation_version_id"] == saved == state["annotation_version_id"]
    assert row["recipe_version_id"] == recipe_id
    assert row["status"] == "succeeded" and events[-1][1]["task_result"] == "succeeded"
    assert state["requested_stages"] == ["annotation", "save", "preprocess"]
    _evidence("B", {"events": _trace(events), "saved_version_id": saved, **row})


def test_c_newer_database_version_does_not_replace_the_session_saved_version(conversation_case):
    c = conversation_case
    _select_recipe(c)
    _, saved = _annotate(c)
    cube_id = c.cube_ids[0]
    newer = _save_newer_annotation(c)
    with connect_database(c.database) as db:
        latest = db.execute("SELECT id FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,)).fetchone()[0]
    assert latest == newer != saved
    c.app.state.agent_llm_factory = lambda _: FakeLLM(
        reply(calls=[call("preprocess.run_default", json.dumps({"cube_id": cube_id}))]), reply("处理已完成。"))
    events = _events(c.client, c.session_id, "用刚才保存的那版做预处理")
    assert _successful(events)["task_result"] == "succeeded"
    row = _bound_run(c, AgentStore(c.database).context(c.session_id)["last_run_id"])
    assert row["annotation_version_id"] == saved != latest
    _evidence("C", {"saved_version_id": saved, "database_latest_version_id": latest, **row})


def test_d_missing_recipe_returns_need_version_without_creating_default_or_run(conversation_case):
    c = conversation_case
    _, saved = _annotate(c)
    with connect_database(c.database) as db:
        recipes_before = list(db.execute("SELECT id FROM preprocess_recipe_version"))
    c.app.state.agent_llm_factory = lambda _: FakeLLM(
        reply(calls=[call("preprocess.run_default", json.dumps({"cube_id": c.cube_ids[0]}))]), reply("请指定配方。"))
    events = _events(c.client, c.session_id, "做预处理")
    assert _successful(events)["task_result"] == "needs_input"
    result = next(data["result_summary"] for kind, data in events if kind == "step")
    assert result == {"cube_id": c.cube_ids[0], "status": "need_version", "missing": "recipe_version",
                      "detail": "请先明确使用哪个标注版本与哪个配方版本，不采用库中最新或内置默认。"}
    assert _run_count(c) == 0
    with connect_database(c.database) as db:
        assert list(db.execute("SELECT id FROM preprocess_recipe_version")) == recipes_before
    assert AgentStore(c.database).context(c.session_id)["annotation_version_id"] == saved
    _evidence("D", result)


@pytest.mark.parametrize("explicit", [False, True], ids=["E-injected", "F-explicit"])
def test_e_f_confirmed_injection_and_explicit_versions_have_distinct_provenance(conversation_case, explicit):
    c = conversation_case
    selected = _select_recipe(c)
    _, saved = _annotate(c)
    other = c.tools.invoke("preprocess.recipe_ensure", {"profile": "raw"})["recipe_version_id"]
    assert other != selected
    arguments = {"cube_id": c.cube_ids[0]}
    annotation_id = _save_newer_annotation(c) if explicit else saved
    if explicit:
        assert annotation_id != saved
        arguments.update(annotation_version_id=annotation_id, recipe_version_id=other)
    validated = c.tools.validate("preprocess.run_default", arguments).model_dump(mode="json")
    state = AgentStore(c.database).context(c.session_id)
    before = deepcopy((state, validated))
    resolved = memory.resolve_arguments(state, "preprocess.run_default", validated)
    assert (state, validated) == before
    assert resolved["annotation_version_id"] == annotation_id
    assert resolved["recipe_version_id"] == (other if explicit else selected)
    # Explicit annotation IDs, too, must survive even if they differ from state.
    assert memory.resolve_arguments(state, "preprocess.run_default", {
        "annotation_version_id": "explicit-annotation", "recipe_version_id": other})["annotation_version_id"] == "explicit-annotation"
    c.app.state.agent_llm_factory = lambda _: FakeLLM(
        reply(calls=[call("preprocess.run_default", json.dumps(arguments))]), reply("处理已完成。"))
    events = _events(c.client, c.session_id, "做预处理")
    assert _successful(events)["task_result"] == "succeeded"
    row = _bound_run(c, AgentStore(c.database).context(c.session_id)["last_run_id"])
    assert row["annotation_version_id"] == annotation_id
    assert row["recipe_version_id"] == resolved["recipe_version_id"]
    _evidence("F" if explicit else "E", row)


def test_g_annotation_only_guard_blocks_model_write_but_allows_read(conversation_case):
    c = conversation_case
    _select_recipe(c)
    _, saved = _annotate(c)
    c.app.state.agent_llm_factory = lambda _: FakeLLM(
        reply(calls=[call("preprocess.recipes")]),
        reply(calls=[call("preprocess.run_default", json.dumps({"cube_id": c.cube_ids[0]}))]))
    before = _run_count(c)
    events = _events(c.client, c.session_id, "只做标注并保存")
    assert [data["tool"] for kind, data in events if kind == "step"] == ["preprocess.recipes"]
    assert events[-1][0] == "clarify"
    assert events[-1][1]["question"] == "你只要求了标注，没有要求预处理。需要我继续预处理吗？"
    assert _run_count(c) == before
    assert AgentStore(c.database).context(c.session_id)["annotation_version_id"] == saved
    _evidence("G", {"events": _trace(events), "runs_before": before, "runs_after": _run_count(c)})


@pytest.mark.parametrize("requested", [None, []], ids=["missing", "empty"])
def test_h_legacy_requests_without_stages_are_not_blocked(conversation_case, requested):
    c = conversation_case
    _select_recipe(c)
    _annotate(c)
    store = AgentStore(c.database)
    state = store.context(c.session_id)
    state.pop("requested_stages")
    if requested is not None:
        state["requested_stages"] = requested
    store.save_context(c.session_id, state)
    c.app.state.agent_llm_factory = lambda _: FakeLLM(
        reply(calls=[call("preprocess.run_default", json.dumps({"cube_id": c.cube_ids[0]}))]), reply("处理已完成。"))
    events = _events(c.client, c.session_id, "继续")
    assert _successful(events)["task_result"] == "succeeded"
    assert _run_count(c) == 1


def test_j_description_upgrade_preserves_pending_v1_plan_and_continuations(gateway_case):
    store = AgentStore(gateway_case.database)
    session_id = store.create_session()["id"]
    assert store.skill(session_id)["version_no"] == 1
    old_tools, _, confirm = simple_registry()
    llm = FakeLLM(reply(calls=[
        call("annotations.draft_confirm", '{"cube_id":"cube-a","revision":1}', "save-a"),
        call("annotations.draft_confirm", '{"cube_id":"cube-b","revision":2}', "save-b")]), reply("保存完成。"))
    pending = list(StateMachine(store, session_id, llm, old_tools).message(content="请确认两笔操作"))
    plan_id = next(data["plan_id"] for kind, data in pending if kind == "plan")
    tools = build_registry(catalogue_version=2)
    old_snapshot = deepcopy(tools.snapshot())
    entry = next(item for item in old_snapshot if item["function"]["name"] == "preprocess.run_default")
    entry["function"]["description"] = "按显式版本或当前最新标注运行；用户授权默认时取平台默认配方，返回真实指标和溯源"
    with connect_database(gateway_case.database) as db:
        old_version = ensure_workflow_skill(db, SimpleNamespace(snapshot=lambda: old_snapshot))
        new_version = ensure_workflow_skill(db, tools)
        assert ensure_workflow_skill(db, tools)["id"] == new_version["id"]
        upgraded = upgrade_builtin_sessions(db, tools)
    assert new_version["version_no"] == old_version["version_no"] + 1
    assert upgraded["upgraded"] == 1 and store.skill(session_id)["version_no"] == new_version["version_no"]
    # Keep the production catalogue/schema; isolate only the confirmation handler.
    tools._tools["annotations.draft_confirm"] = replace(tools.resolve("annotations.draft_confirm"), handler=confirm)
    resumed = StateMachine(store, session_id, llm, tools)
    sequences = [pending]
    events = list(resumed.message(plan_id=plan_id, action="approve"))
    sequences.append(events)
    while events[-1][0] == "human_check":
        events = list(resumed.message(check_id=events[-1][1]["check_id"], decision="approve"))
        sequences.append(events)
    assert events[-1][0] == "done" and events[-1][1]["task_result"] == "succeeded"
    assert confirm.call_count == 2
    assert len(store.rounds(session_id)) == 1
    assert [step["status"] for step in store.steps(session_id, plan_id)] == ["ok", "ok"]
    _evidence("J", {"active_skill_version_no_before": old_version["version_no"],
                    "active_skill_version_no_after": new_version["version_no"],
                    "session_skill_version_no_before": 1, "session_skill_version_no_after": store.skill(session_id)["version_no"],
                    "events": [_trace(events) for events in sequences]})
