"""Bounded observe/act loop for the versioned conversational workflow skill."""
from hashlib import sha256
import json
import re
import sqlite3
from time import perf_counter_ns

from spectrumagent.data import DataError
from . import context as memory
from .llm import _json, validate_tool_response


READ_TOOLS = {"datasets.list", "datasets.resolve", "datasets.describe", "annotations.context",
              "annotations.draft_get", "preprocess.recipes", "preprocess.run_get", "settings.llm_get"}
RECOVERABLE = {"DRAFT_REVISION_CONFLICT", "SUPERPIXELS_REQUIRED", "LABEL_NOT_FOUND", "GESTURE_NOT_FOUND",
               "GESTURE_EXPIRED", "GESTURE_NOT_CURRENT", "CANDIDATE_STALE", "SEGMENTATION_STALE", "CANDIDATE_NOT_FOUND", "ANNOTATION_VERSION_REQUIRED"}


def _authorized(state, cube_id=None):
    selected = state.get("selected_cube_id")
    return bool(selected and state.get("auto_execute") and state.get("authorization_cube_id") == selected
                and (cube_id is None or cube_id == selected))


def _readable(text, state):
    for row in state.get("dataset_catalog", []):
        text = text.replace(row["id"], f"{row['name']}（{row['ref']}）")
    if state.get("selected_cube_id"):
        text = text.replace(state["selected_cube_id"], state.get("display_name", "当前数据"))
    # Provenance remains in the execution log; prose uses short, readable refs.
    return re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
                  lambda match: match.group(0)[:8], text)


def _workspace(state):
    if not state.get("selected_cube_id"):
        return None
    result = {"cube_id": state["selected_cube_id"]}
    for key in ("display_name", "revision"):
        if state.get(key) is not None:
            result[key] = state[key]
    stage = state.get("stage") or state.get("intent")
    if stage in {"annotation", "preprocess"}:
        result["stage"] = stage
    return result


def _messages(machine, version, state, content, turn_id):
    result = [{"role": "system", "content": version["system_prompt"]},
              {"role": "system", "content": _json({"task_state": state})}]
    examples = json.loads(version["examples_json"])
    if examples:
        result.append({"role": "system", "content": _json({"workflow_examples": examples})})
    result.extend(machine._history_messages(version, exclude_turn_id=turn_id))
    result.append({"role": "user", "content": content})
    if turn_id:
        for row in machine.store.turn_rounds(machine.session_id, turn_id):
            result.extend(machine._round_messages(row))
    return result


def generate(machine, *, content=None, workspace=None, continuation=None, decision=None, plan=None):
    from backend.database import connect_database
    from .state import State, MAX_TOOL_CALLS, MAX_WORKFLOW_BATCHES, MAX_WORKFLOW_STEPS, RAW_BYTES
    from .task import evaluate_task
    store, session_id = machine.store, machine.session_id
    row, turn_id, creation_attempted = None, None, False
    workspace_sent = None
    state, last_status = {}, None
    mapping = ""

    def task_result():
        run_status = None
        if state.get("last_run_id"):
            with connect_database(store.database) as db:
                run = db.execute("SELECT status FROM preprocess_run WHERE id=?", (state["last_run_id"],)).fetchone()
            run_status = run[0] if run else None
        return evaluate_task(state, {"run_status": run_status, "last_status": last_status})

    def reference_answer(answer, *, clarify=False):
        nonlocal row, creation_attempted
        if row is None:
            creation_attempted = True
            row = store.new_round(session_id, content, [], "done")
        else:
            store.round_status(row["id"], "done")
        store.save_context(session_id, state)
        store.save_answer(row["id"], answer)
        current_workspace = _workspace(state)
        if current_workspace:
            yield "workspace", current_workspace
        machine.state = State.CLARIFY if clarify else State.DONE
        payload = {"question" if clarify else "content": answer, "task_result": task_result(),
                   "pending_clarify": state.get("pending_clarify")}
        if not clarify:
            payload["step_count"] = len(store.steps(session_id, row["id"]))
        yield "clarify" if clarify else "done", payload

    try:
        version = store.skill(session_id)
        # The tool catalogue comes from the live registry, not the stored skill row:
        # the two can disagree after an upgrade, and only the live catalogue describes
        # what the model may actually call. Prompt and examples still come from the skill.
        tools = machine.tools.snapshot()
        state = memory.upgrade_context(store.context(session_id))
        prior_steps = store.steps(session_id)
        last_tool = next((step["tool"] for step in reversed(prior_steps) if step["status"] in {"ok", "error"}), None)
        prior_rounds = store.rounds(session_id)
        latest_turn = (prior_rounds[-1].get("turn_id") or prior_rounds[-1]["id"]) if prior_rounds else None
        recent_ids = {r["id"] for r in prior_rounds if (r.get("turn_id") or r["id"]) == latest_turn}
        if continuation is None:
            requested = memory.reference_request(state, content)
            kind, item, _ = memory.resolve_reference(state, content, last_tool, recent_round_ids=recent_ids)
            state = memory.remember_user(state, content, workspace, last_tool, recent_round_ids=recent_ids)
            pending = state.get("pending_clarify")
            if pending and pending["reason"] == "stale" and not pending["asked"]:
                read_tool = {"dataset": "datasets.list", "recipe": "preprocess.recipes",
                             "candidate": "annotations.context", "region": "annotations.context"}.get(pending["kind"])
                arguments = {} if pending["kind"] in {"dataset", "recipe"} else {"cube_id": state.get("selected_cube_id")}
                if read_tool and (not arguments or arguments["cube_id"]):
                    creation_attempted = True
                    row = store.new_round(session_id, content, [], "running")
                    started = perf_counter_ns()
                    error = None
                    try:
                        result = machine.tools.invoke(read_tool, arguments)
                    except Exception as exc:
                        error = exc if isinstance(exc, DataError) else DataError("TOOL_FAILED", "列表刷新失败")
                        result = {"error": error.code}
                    # Controller reads are audited but have no model tool_call_id.
                    # They must never count as native model calls in L0 evidence.
                    step = store.add_step(row, read_tool, arguments, "error" if error else "ok", result,
                                          (perf_counter_ns() - started) // 1_000_000)
                    last_status, last_tool = result.get("status"), read_tool
                    state = memory.observe(state, read_tool, arguments, result, row["id"])
                    store.save_context(session_id, state)
                    event, payload = machine._step_event(step)
                    yield event, {**payload, "pending_clarify": state.get("pending_clarify")}
                    if error:
                        raise error
                    recent_ids.add(row["id"])
                    kind, item, _ = memory.resolve_reference(state, content, last_tool, recent_round_ids=recent_ids)
                    state = memory.remember_user(state, content, workspace, last_tool, recent_round_ids=recent_ids)
                    mapping = memory.reference_mapping(kind, item, refreshed=True) if item else "已刷新列表。"
                    pending = state.get("pending_clarify")
            if pending:
                if pending["asked"]:
                    state.pop("pending_clarify", None)
                    yield from reference_answer("仍未确定，保持当前选择")
                else:
                    state["pending_clarify"] = {**pending, "asked": True}
                    label = {"dataset": "数据", "candidate": "候选", "recipe": "配方", "region": "区域"}.get(pending["kind"], "编号对象")
                    answer = (f"当前只有一个{label}，是指它吗？" if pending["reason"] == "only_one" else
                              f"当前没有可确定的{label}，请明确指认或先列出对应列表。")
                    yield from reference_answer((mapping + "\n" if mapping else "") + answer, clarify=True)
                return
            if requested and item:
                mapping = mapping or memory.reference_mapping(kind, item)
                if memory.reference_only(content):
                    yield from reference_answer(mapping)
                    return
            reference = memory.user_reference(content, state, last_tool) if kind == "dataset" else None
            selected = state.get("selected_cube_id")
            if reference or selected:
                # Validate and hydrate a local UI reference; never trust a path
                # or a user-provided dataset description as provider context.
                query = memory.resolve_arguments(state, "datasets.resolve", {"query": reference or selected})
                resolved = machine.tools.invoke("datasets.resolve", query)
                if resolved.get("status") in {"ambiguous", "not_found"}:
                    choices = [f"{resolved[key]}（{resolved.get(key.replace('_name', '_ref'), '')}）"
                               for key in resolved if re.fullmatch(r"match_\d+_name", key)]
                    answer = ("找到多个匹配数据，请从以下名称中选择：" + "、".join(choices)) if choices else "没有找到对应数据，请指定列表中的名称或短引用。"
                    creation_attempted = True
                    row = store.new_round(session_id, content, [], "done")
                    store.save_answer(row["id"], answer)
                    store.save_context(session_id, state)
                    yield "clarify", {"question": answer}
                    return
                state = memory.observe(state, "datasets.resolve", {}, resolved)
                # Reapply explicit task-local permission AFTER the reference
                # is hydrated, so resolving a new cube cannot inherit old consent.
                state = memory.remember_user(state, content, last_tool=last_tool, recent_round_ids=recent_ids)
            store.save_context(session_id, state)
            calls, offset = None, 0
        else:
            resumed, pending = continuation
            if plan is not None:
                store.claim_plan(resumed["id"])
            else:
                store.claim(resumed["id"])
            row = resumed
            turn_id = row.get("turn_id") or row["id"]
            content = row["user_message"]
            if plan is not None:
                action, step_ref, reason = plan
                if action != "approve":
                    store.add_plan_action(row, action, step_ref, reason)
                if action == "reject":
                    store.save_answer(row["id"], "计划已拒绝、未执行")
                    store.round_status(row["id"], "done")
                    yield "done", {"content": "计划已拒绝、未执行", "step_count": 0}
                    return
                calls, _ = store.effective_calls(row["id"])
                offset = 0
            else:
                calls, _ = store.effective_calls(row["id"])
                if decision == "reject":
                    step = store.finish_step(pending, "rejected", {"error": "HUMAN_REJECTED"}, 0)
                    store.save_answer(row["id"], "已拒绝、未执行后续操作")
                    yield machine._step_event(step)
                    yield "done", {"content": "已拒绝、未执行后续操作", "step_count": len(store.steps(session_id, row["id"]))}
                    return
                completed = [step for step in store.steps(session_id, row["id"]) if step["status"] != "rejected"]
                offset = len(completed)
                call = calls[offset - 1]
                step, error = machine._execute(row, call, pending)
                result = json.loads(step["result_summary"])
                last_status = result.get("status")
                last_tool = call["name"]
                state = memory.observe(state, call["name"], call["arguments"], result, row["id"])
                store.save_context(session_id, state)
                yield machine._step_event(step)
                if error:
                    raise error
        while True:
            current_workspace = _workspace(state)
            if current_workspace and current_workspace != workspace_sent:
                workspace_sent = current_workspace
                yield "workspace", current_workspace
            if calls is None:
                machine.state = State.PARSE if row is None else State.INTERPRET
                reply = machine.llm.chat(_messages(machine, version, state, content, turn_id), tools)
                validate_tool_response(reply)
                if not reply.tool_calls:
                    if row is None:
                        creation_attempted = True
                        row = store.new_round(session_id, content, [], "done")
                        turn_id = row["turn_id"]
                    else:
                        store.round_status(row["id"], "done")
                    answer = _readable(reply.content or "", state)
                    if mapping:
                        answer = mapping + "\n" + answer
                    store.save_answer(row["id"], answer)
                    count = sum(len(store.steps(session_id, batch["id"])) for batch in store.turn_rounds(session_id, turn_id))
                    machine.state = State.DONE if count else State.CLARIFY
                    outcome = task_result()
                    yield ("done", {"content": answer, "step_count": count, "task_result": outcome}) if count else ("clarify", {"question": answer, "task_result": outcome})
                    return
                batches = store.turn_rounds(session_id, turn_id) if turn_id else []
                step_count = sum(len(store.steps(session_id, batch["id"])) for batch in batches)
                if len(batches) >= MAX_WORKFLOW_BATCHES or step_count >= MAX_WORKFLOW_STEPS:
                    raise DataError("AGENT_BUDGET_EXCEEDED", "本次任务达到连续执行上限，已保留进度，请检查执行记录后继续")
                calls, rejected = [], []
                for index, call in enumerate(reply.tool_calls):
                    started = perf_counter_ns()
                    try:
                        if index >= MAX_TOOL_CALLS or step_count + index >= MAX_WORKFLOW_STEPS:
                            raise DataError("TOOL_SEQUENCE_LIMIT", "工具序列超限")
                        if call.name not in {tool["function"]["name"] for tool in tools}:
                            raise DataError("TOOL_NOT_FOUND", "工具未在当前会话中提供")
                        arguments = machine.tools.validate(call.name, call.arguments_json).model_dump(mode="json")
                        arguments = memory.resolve_arguments(state, call.name, arguments)
                        calls.append({"id": call.id, "name": call.name, "arguments": arguments})
                    except DataError as error:
                        raw = call.arguments_json.encode("utf-8")
                        rejected.append((call.name, {"_raw_sha256": sha256(raw).hexdigest(),
                            "_raw_truncated": raw[:RAW_BYTES].decode("utf-8", errors="ignore")}, error.code,
                            (perf_counter_ns() - started) // 1_000_000))
                if row is not None:
                    store.round_status(row["id"], "done")
                needs_plan = len([call for call in calls if call["name"] not in READ_TOOLS]) >= 2 and not _authorized(state)
                creation_attempted = True
                row = store.new_round(session_id, content, calls, "plan_check" if needs_plan else "running", turn_id=turn_id)
                turn_id = row["turn_id"]
                for name, arguments, code, elapsed in rejected:
                    yield machine._step_event(store.add_step(row, name, arguments, "rejected", {"error": code}, elapsed))
                if needs_plan:
                    machine.state = State.PLAN_CHECK
                    yield "plan", {"plan_id": row["id"], "steps": [
                        {"seq": i, "tool": call["name"], "summary": {key: value for key, value in call["arguments"].items()
                         if key in {"cube_id", "revision", "class_code", "overwrite"} and value is not None},
                         "gpu": machine.tools.resolve(call["name"]).gpu,
                         "estimate_ms": machine.tools.resolve(call["name"]).estimate_ms}
                        for i, call in enumerate(calls, 1)], "reason": (mapping + "\n" if mapping else "") + "执行计划待确认"}
                    return
                offset = 0
            for call in calls[offset:]:
                call_cube = call["arguments"].get("cube_id")
                if call_cube and state.get("selected_cube_id") and call_cube != state["selected_cube_id"]:
                    raise DataError("TASK_DATASET_MISMATCH", "工具目标与当前选定数据不一致，已停止执行，请重新指定数据")
                denied_candidate = (call["name"] == "annotations.apply_candidate"
                                    and state.get("rejected_candidate_ref") == call["arguments"].get("candidate_ref"))
                denied_save = (call["name"] == "annotations.draft_confirm" and call_cube
                               and state.get("save_denied") == call_cube)
                denied_defaults = (state.get("use_defaults") is False and call["name"] in {"annotations.prepare", "preprocess.run_default"})
                denied_stage = (call["name"] == "preprocess.run_default" and state.get("requested_stages")
                                and "preprocess" not in state["requested_stages"])
                if denied_candidate or denied_save or denied_defaults or denied_stage:
                    answer = ("你只要求了标注，没有要求预处理。需要我继续预处理吗？" if denied_stage else
                              "已遵从你的要求：保留当前进度，未接受候选、未保存新版本。" if denied_candidate or denied_save
                              else "已保留当前进度，没有采用默认参数。请指定希望使用的配置。")
                    if mapping:
                        answer = mapping + "\n" + answer
                    store.save_answer(row["id"], answer)
                    store.round_status(row["id"], "done")
                    yield "clarify", {"question": answer, "task_result": task_result()}
                    return
                if (call["name"] == "annotations.apply_candidate" and not _authorized(state, call_cube)
                        and state.get("accepted_candidate_ref") != call["arguments"].get("candidate_ref")):
                    answer = "候选预览已生成，尚未写入标注。请查看画布后回复“接受候选”或“不要这个”；已选数据和参数会保留。"
                    if mapping:
                        answer = mapping + "\n" + answer
                    store.save_answer(row["id"], answer)
                    store.round_status(row["id"], "done")
                    yield "clarify", {"question": answer, "task_result": task_result()}
                    return
                tool = machine.tools.resolve(call["name"])
                save_authorized = (call["name"] == "annotations.draft_confirm" and call_cube
                                   and state.get("save_requested") == call_cube == state.get("selected_cube_id"))
                if tool.human_check and not (_authorized(state, call_cube) or save_authorized):
                    summary = {key: value for key, value in call["arguments"].items()
                               if key in {"cube_id", "revision", "class_code", "overwrite"} and value is not None}
                    step = store.add_step(row, call["name"], call["arguments"], "human_check_pending", summary, 0, tool_call_id=call["id"])
                    machine.state = State.HUMAN_CHECK
                    yield "human_check", {"check_id": step["id"], "tool": call["name"], "summary": summary, "reason": (mapping + "\n" if mapping else "") + "标注版本确认"}
                    return
                previous = [step for batch in store.turn_rounds(session_id, turn_id)
                            for step in store.steps(session_id, batch["id"])
                            if step["status"] == "ok" and step["tool"] == call["name"]
                            and json.loads(step["arguments_json"]) == call["arguments"]]
                if previous and (call["name"] not in READ_TOOLS or len(previous) >= 2):
                    raise DataError("AGENT_NO_PROGRESS", "助手重复了相同操作，已停止重复执行并保留进度")
                machine.state = State.CALL_TOOL
                step, error = machine._execute(row, call)
                result = json.loads(step["result_summary"])
                last_status = result.get("status")
                last_tool = call["name"]
                state = memory.observe(state, call["name"], call["arguments"], result, row["id"])
                if call["name"] == "annotations.draft_confirm" and not error:
                    state.pop("save_requested", None)
                store.save_context(session_id, state)
                yield machine._step_event(step)
                current_workspace = _workspace(state)
                if current_workspace and current_workspace != workspace_sent:
                    workspace_sent = current_workspace
                    yield "workspace", current_workspace
                if error and error.code not in RECOVERABLE:
                    raise error
            calls = None
    except GeneratorExit:
        if row is not None:
            store.cancel_running(row["id"])
        raise
    except Exception as exc:
        machine.state = State.ERROR
        error = exc if isinstance(exc, DataError) else DataError("AGENT_FAILED", "编排执行失败")
        try:
            if row is None and content is not None and not creation_attempted:
                store.new_round(session_id, content, [], "error")
            elif row is not None:
                store.cancel_running(row["id"])
        except (sqlite3.Error, DataError):
            error = DataError("AGENT_STORAGE", "编排留痕存储失败")
        yield "error", {"code": error.code, "detail": error.payload.detail,
                        "task_result": evaluate_task({**state, "last_error": error.code},
                                                     {"run_status": None, "last_status": last_status})}
    finally:
        machine.state = State.IDLE
