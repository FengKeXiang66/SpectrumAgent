"""Bounded observe/act loop for the versioned conversational workflow skill."""
from hashlib import sha256
import json
import re
import sqlite3
from time import perf_counter_ns

from spectrumagent.data import DataError
from spectrumagent.data.validation import PARAMETER_ERRORS, INPUT_ERRORS, parameter_answer, safe_error
from . import context as memory
from .llm import _json, validate_tool_response
from .open_access import OPEN_ACCESS
from .execution import RequestCancelled, numerical_confirmation


READ_TOOLS = {"datasets.list", "datasets.resolve", "datasets.describe", "annotations.context",
              "annotations.status_batch",
              "annotations.draft_get", "preprocess.recipes", "preprocess.run_get", "settings.llm_get",
              "modeling.runs", "modeling.run", "modeling.registry", "modeling.coefficients", "modeling.inference", "modeling.metrics",
              "sources.list", "sources.scan", "datasets.delete_preview", "training_sets.list",
              "training_sets.members", "training_sets.candidates", "projects.paths_get"}
READ_TOOLS.add('preprocess.draft_get')
READ_TOOLS.update({'preprocess.runs','preprocess.operators','modeling.targets','ui.show'})
READ_TOOLS.add('modeling.classification_result')
READ_TOOLS.add('modeling.regression_plan_get')
RECOVERABLE = {"DRAFT_REVISION_CONFLICT", "SUPERPIXELS_REQUIRED", "LABEL_NOT_FOUND", "LABEL_REMOVED", "GESTURE_NOT_FOUND",
               "GESTURE_EXPIRED", "GESTURE_NOT_CURRENT", "CANDIDATE_STALE", "SEGMENTATION_STALE", "CANDIDATE_NOT_FOUND", "ANNOTATION_VERSION_REQUIRED"}


def _authorized(state, cube_id=None):
    if OPEN_ACCESS:
        return True
    selected = state.get("selected_cube_id")
    return bool(selected and state.get("auto_execute") and state.get("authorization_cube_id") == selected
                and (cube_id is None or cube_id == selected))


def _readable(text, state):
    # Internal context is not a user-facing result document. Remove only known
    # context objects, leaving requested JSON and ordinary prose intact.
    decoder = json.JSONDecoder()
    spans = []
    for match in re.finditer(r'\{', text):
        if any(start<=match.start()<end for start,end in spans):continue
        try:
            obj, length = decoder.raw_decode(text[match.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and set(obj) & {'task_state', 'current_datasets', 'current_registered_datasets', 'confirmed_preprocess_inputs', 'operation_authorization'}:
            spans.append((match.start(), match.start() + length))
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    text = text.replace('[路径已隐藏]', '').strip()
    text = re.sub(r'```(?:json)?\s*```','',text).strip()
    if not text:
        text = '本次回复包含内部状态，已隐藏。请查看执行记录核对实际结果。'
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
    stage = state.get("stage")
    if stage in {"annotation", "preprocess"}:
        result["stage"] = stage
    return result


def _messages(machine, version, state, content, turn_id, *, reasoning_by_round=None):
    from spectrumagent.experiments.pairing import CAPABILITY
    result = [{"role": "system", "content": version["system_prompt"]},
              {"role": "system", "content": _json({"task_state": {
                  k: v for k, v in state.items() if k not in {'canvas_focus', 'operation_authorization','preprocess_selection'}
              }})}]
    result.append({'role':'system', 'content':CAPABILITY + '\n'
                   '1. 用户泛泛咨询用本地高光谱数据训练分类模型且尚未说明数据形态时，先简明说明以下两条路线，'
                   '再问用户手头是已有配套标注或 NPZ，还是只有未标注原图。不要把去设置页登记数据源当成默认第一步。\n'
                   '2. 通用导入使用数据接入卡片：未说明标注情况时让用户选择尚未标注或已有标注；已说明时沿用，不重复询问。'
                   '已有标注只先收集原图和标注位置，配对后接入工作台可直接预处理，不要求用户重做超像素。'
                   '不要在导入或查看数据时强制要求训练原图、训练标注、测试原图、测试标注四类用途；只有用户明确要求已有训练测试实验时才收集。'
                   '已有 ENVI 原图和外部 ROI 标注 JSON，或已有训练和测试 NPZ，也可直接走本机实验流程。'
                   '无需到设置页登记数据源，无需调用 sources.scan 或 datasets.import 导入工作台，'
                   '也无需建项目标签、重新做画布标注、编辑工作台预处理配方或把原图和标注先转为 NPZ。'
                   '用户可以直接在对话框中粘贴本地文件或目录路径，也可以点输入框旁的「选择目录」或「选择文件」带入。'
                   '本机后端接收路径并脱敏为内部引用后才与模型交互。不要把“路径不进入模型上下文”解释成“路径不能发进对话”。\n'
                   '3. 路线 B：只有未标注原图，且需要在软件画布上人工点选时，走工作台流程。'
                   '工作台已有导入数据时，不要自造 A、B 划分或预处理问卷。核验仅有一个前景类时，说明分类至少需要两个不同的已标注前景类，'
                   '引导补标并保存，再通过“配置预处理与训练”进入统一方案。'
                   '用户提供路径后可直接使用数据接入卡片导入，随后建标签、做超像素画布标注、按配方预处理并训练。'
                   'sources.scan 和 datasets.import 仍可用于已登记的数据源，但不能要求路径导入用户先去设置页。\n'
                   '4. 前后一致地说明当前路线的入口。工作台已导入数据集为 0 只描述工作台状态，不能据此要求路线 A 先登记。'
                   '同一条建议中不要一边说本地路径不能发进对话，一边让用户发目录。'})
    if state.get('preprocess_selection'):
        result.append({'role':'system','content':_json({'confirmed_preprocess_inputs':state['preprocess_selection']['inputs'],
            'policy':'本轮用户明确选择已展示方案后，服务端绑定的完整版本范围。执行须显式传入这些引用，不换为最新，不添加成员。'})})
    examples = json.loads(version["examples_json"])
    if examples:
        result.append({"role": "system", "content": _json({"workflow_examples": examples})})
    result.extend(machine._history_messages(version, exclude_turn_id=turn_id))
    if state.get('current_datasets') is not None:
        result.append({'role':'system','content':_json({
            'current_registered_datasets':state['current_datasets'],
            'source':'本请求从当前应用登记库读取，优先于历史数据数量和数据源设置。',
            'policy':'未登记数据源不代表没有已导入数据。登记数量不等于已经核验可读；需要时调用工具检查。'
                     '当前目录仅供查询，不替代用户最后看到的D编号目录，不授予操作权限。'})})
    result.append({"role": "user", "content": content})
    if turn_id:
        for row in machine.store.turn_rounds(machine.session_id, turn_id):
            reasoning = reasoning_by_round.get(row["id"]) if reasoning_by_round is not None else None
            result.extend(machine._round_messages(row, reasoning_content=reasoning))
    return result


def request_tools(tools, content, state=None):
    """Recipe composition has no annotation/data dependency; execution does."""
    # Explicit train/test collection has its own reviewed, session-owned flow.
    tools = [tool for tool in tools if not tool['function']['name'].startswith('experiments.')]
    if ((re.search(r'配方|算子|SNV|SG|平滑|导数', content or '', re.I) or (state or {}).get('recipe_editing'))
            and not re.search(r'预处理|执行|运行|标注|查询数据|查看数据|分割|训练|建模|回归|测量|连续量|含量|展示|结果|对比|比较|导出|(?:使用|采用|用)(?:默认|上述|这个|该)(?:配方|方案)', content or '')):
        names = {'preprocess.recipes', 'preprocess.recipe_ensure', 'preprocess.recipe_create',
                 'preprocess.recipe_version_add', 'preprocess.recipe_delete', 'preprocess.recipe_restore',
                 'preprocess.draft_get', 'preprocess.draft_update', 'preprocess.draft_save',
                 'preprocess.recipe_select', 'preprocess.operators', 'workspace.current', 'workspace.recipe_edit',
                 'datasets.list', 'datasets.describe'}
        if (state or {}).get('recipe_editing'):
            names-={'preprocess.recipe_create','preprocess.recipe_version_add'}
        return [t for t in tools if t['function']['name'] in names]
    return tools


def draft_parameter_stall(machine, turn_id, step, result):
    """Changing a revision or prose is not progress on missing parameters."""
    if step['tool']!='preprocess.draft_update' or result.get('validation_valid') is not False:
        return None
    signature={k:v for k,v in result.items() if re.fullmatch(r'step_\d+_.+',k)}
    for round_ in machine.store.turn_rounds(machine.session_id,turn_id):
        for old in machine.store.steps(machine.session_id,round_['id']):
            if old['id']==step['id'] or old['tool']!=step['tool'] or old['status']!='ok':continue
            previous=json.loads(old['result_summary'])
            if (previous.get('draft_id')==result.get('draft_id') and previous.get('validation_valid') is False
                    and {k:v for k,v in previous.items() if re.fullmatch(r'step_\d+_.+',k)}==signature):
                fields=[str(v) for k,v in result.items() if re.fullmatch(r'validation_\d+_field',k)]
                return ('草稿及已确认参数已保留，但实际步骤参数尚未补齐：'+ '、'.join(fields)+
                        '。重复更新已停止；请给出这些字段的值，或确认上一条明确提出的具体参数后继续。')
    return None


def generate(machine, *, content=None, workspace=None, continuation=None, decision=None, plan=None):
    from backend.database import connect_database
    from .state import State, MAX_TOOL_CALLS, MAX_WORKFLOW_BATCHES, MAX_WORKFLOW_STEPS, RAW_BYTES
    from .task import evaluate_task
    store, session_id = machine.store, machine.session_id
    row, turn_id, creation_attempted = None, None, False
    reasoning_by_round = {}
    workspace_sent = None
    canvas_touched = False
    canvas_workspace = None
    state, last_status, last_batch_status = {}, None, None
    mapping = ""

    def parameter_reply(error):
        # End this request immediately. A later user correction is a new request;
        # no model retry can repeat an invalid call or run dependent writes.
        answer = parameter_answer(error) + '。此前完成项已保留。'
        store.save_answer(row['id'], answer)
        store.round_status(row['id'], 'done')
        yield 'clarify', {'question': answer, 'task_result': 'needs_input',
                         'request_status': 'finished', 'reply_status': 'needs_input'}

    def current_workspace():
        if canvas_workspace:
            return canvas_workspace
        if state.get('intent') in {'modeling', 'modeling_query'} and not canvas_touched:
            return None
        if not canvas_touched and not (content and (memory.reference_request(state, content)
                or re.search(r'当前(?:这)?(?:张|幅|图|样品|数据)', content))):
            return None  # A greeting/follow-up answer must not move the canvas to an old task target.
        return _workspace(state)

    def task_result():
        run_status = None
        preprocess_batch = None
        if state.get("last_run_id"):
            with connect_database(store.database) as db:
                run = db.execute("SELECT status FROM preprocess_run WHERE id=?", (state["last_run_id"],)).fetchone()
            run_status = run[0] if run else None
        if turn_id:
            # Read this logical request's receipt, including a resumed round.
            # A successful batch from an older user request is not completion.
            with connect_database(store.database) as db:
                batch = db.execute("SELECT s.result_summary FROM agent_step s JOIN agent_round r ON r.id=s.round_id "
                    "WHERE s.session_id=? AND COALESCE(r.turn_id,r.id)=? AND s.tool IN ('preprocess.run_batch','preprocess.draft_execute','workspace.preprocess') "
                    "AND s.status='ok' ORDER BY s.rowid DESC LIMIT 1",(session_id,turn_id)).fetchone()
            preprocess_batch = json.loads(batch[0]) if batch else None
        return evaluate_task(state, {"run_status": run_status, "last_status": last_status,
                                     "batch_prepare_status": last_batch_status, "preprocess_batch":preprocess_batch})

    def reference_answer(answer, *, clarify=False):
        nonlocal row, creation_attempted
        if row is None:
            creation_attempted = True
            row = store.new_round(session_id, content, [], "done")
        else:
            store.round_status(row["id"], "done")
        store.save_context(session_id, state)
        store.save_answer(row["id"], answer)
        visible = current_workspace()
        if visible:
            yield "workspace", visible
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
        if hasattr(machine.tools, 'hydrate'):
            state = machine.tools.hydrate(state)
            machine.tools.check_workspace(workspace)
        prior_steps = store.steps(session_id)
        last_tool = next((step["tool"] for step in reversed(prior_steps) if step["status"] in {"ok", "error"}), None)
        prior_rounds = store.rounds(session_id)
        latest_turn = (prior_rounds[-1].get("turn_id") or prior_rounds[-1]["id"]) if prior_rounds else None
        recent_ids = {r["id"] for r in prior_rounds if (r.get("turn_id") or r["id"]) == latest_turn}
        if continuation is None:
            from .authorization import annotation_mode
            mode = annotation_mode(content)
            if mode and hasattr(machine.tools, 'start_annotation_mode'):
                # A mode answer is a complete user action against the pending
                # annotation scope. Do not ask the model to reconstruct it or
                # resolve “first image” as an unrelated catalogue reference.
                try:
                    machine.tools.capture_intent(content, workspace, state)
                except DataError as missing:
                    if missing.code != 'TASK_TARGET_REQUIRED':
                        raise
                    for event, payload in reference_answer(missing.payload.detail + '。请在下方选择范围，再点击生成方式。'):
                        yield event, {**payload, 'task_result': 'needs_input', 'reply_status':'needs_input','annotation_target_cube_ids': []}
                    return
                store.save_context(session_id, state)
                creation_attempted = True
                row = store.new_round(session_id, content, [], 'running')
                payload = machine.tools.start_annotation_mode(mode, state)
                store.save_answer(row['id'], payload['content'])
                store.round_status(row['id'], 'done')
                machine.state = State.DONE
                yield 'done', payload
                return
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
            if hasattr(machine.tools, 'capture_intent'):
                try:
                    machine.tools.capture_intent(content, workspace, state)
                finally:
                    # Explicit refusals/preferences survive an unresolved target.
                    store.save_context(session_id, state)
            store.save_context(session_id, state)
            calls, offset = None, 0
        else:
            resumed, pending = continuation
            if hasattr(machine.tools, 'user_content'):
                machine.tools.user_content = resumed['user_message']
            if hasattr(machine.tools, 'preflight_group') and decision != 'reject' and (plan is None or plan[0] != 'reject'):
                saved_calls, _ = store.effective_calls(resumed['id'])
                try:
                    machine.tools.preflight_group(saved_calls)
                except DataError as stale:
                    if pending is not None:
                        store.finish_step(pending,'error',{'error':stale.code,'stale_pending':True},0)
                    store.round_status(resumed['id'],'error')
                    raise
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
                if call['name']=='sessions.create_work' and hasattr(machine.tools,'approve_partial'):
                    machine.tools.approve_partial(call['arguments'], json.loads(pending['result_summary']))
                if getattr(machine, 'control', None) is not None:
                    yield 'progress', {'phase': 'tool', 'tool': call['name']}
                step, error = machine._execute(row, call, pending)
                canvas_touched = not error and call['name'] in memory.CANVAS_ANNOTATION_TOOLS
                result = json.loads(step["result_summary"])
                if canvas_touched and result.get('cube_id') and result.get('status') not in {'accepted','need_seed','failed'}:
                    canvas_workspace = {'cube_id': result['cube_id'], 'stage': 'annotation',
                        **{k:result[k] for k in ('revision','display_name') if result.get(k) is not None}}
                last_status = result.get("status")
                last_tool = call["name"]
                state = memory.observe(state, call["name"], call["arguments"], result, row["id"])
                store.save_context(session_id, state)
                yield machine._step_event(step)
                stalled=draft_parameter_stall(machine,turn_id,step,result) if not error else None
                if stalled:
                    store.save_answer(row['id'],stalled)
                    store.round_status(row['id'],'done')
                    yield 'clarify',{'question':stalled,'task_result':'needs_input'}
                    return
                if error:
                    raise error
        while True:
            visible = current_workspace()
            if visible and visible != workspace_sent:
                workspace_sent = visible
                yield "workspace", visible
            if calls is None:
                machine.state = State.PARSE if row is None else State.INTERPRET
                if getattr(machine, 'control', None) is not None:
                    yield 'progress', {'phase': 'model'}
                offered_tools = request_tools(tools, content, state)
                reply = machine._chat(_messages(machine, version, state, content, turn_id,
                                                reasoning_by_round=reasoning_by_round), offered_tools)
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
                    machine.state = State.DONE
                    outcome = task_result()
                    if not count and not any(state.get(k) for k in ('requested_stages', 'candidate_ref', 'annotation_version_id', 'last_run_id', 'task_target')):
                        outcome = 'succeeded'
                    choice_target = (machine.tools.annotation_choice_target(state)
                                     if hasattr(machine.tools, 'annotation_choice_target') else None)
                    if choice_target is not None:
                        outcome='needs_input'
                    yield "done", {"content": answer, "step_count": count, "task_result": outcome,
                                   'request_status': 'finished',
                                   'reply_status': 'needs_input' if choice_target is not None or last_status in {'need_seed', 'need_version', 'need_annotation'} else 'replied',
                                   **({'annotation_target_cube_ids': choice_target} if choice_target is not None else {})}
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
                        if call.name not in {tool["function"]["name"] for tool in offered_tools}:
                            machine.tools.resolve(call.name)  # work scope still rejects forged global/unknown calls
                            raise DataError("TOOL_NOT_FOUND", "工具未在当前会话中提供")
                        arguments = machine.tools.validate(call.name, call.arguments_json).model_dump(
                            mode="json", exclude_unset=call.name == 'modeling.regression_plan_update')
                        arguments = memory.resolve_arguments(state, call.name, arguments)
                        calls.append({"id": call.id, "name": call.name, "arguments": arguments})
                    except DataError as error:
                        raw = call.arguments_json.encode("utf-8")
                        rejected.append((call.name, {"_raw_sha256": sha256(raw).hexdigest(),
                            "_raw_bytes": len(raw)}, error,
                            (perf_counter_ns() - started) // 1_000_000))
                if row is not None:
                    store.round_status(row["id"], "done")
                if hasattr(machine.tools, 'preflight_group'):
                    if any(error.code=='SESSION_SCOPE_MISMATCH' for _,_,error,_ in rejected):
                        raise DataError('SESSION_SCOPE_MISMATCH','本组包含范围外操作，整组未执行')
                    if not any(error.code in PARAMETER_ERRORS for _,_,error,_ in rejected):
                        machine.tools.preflight_group(calls)
                needs_plan = not OPEN_ACCESS and len([call for call in calls if call["name"] not in READ_TOOLS]) >= 2 and not _authorized(state)
                if needs_plan and hasattr(machine.tools, 'authorizes_modeling_plan'):
                    needs_plan = not machine.tools.authorizes_modeling_plan(content, calls)
                if needs_plan and hasattr(machine.tools,'authorizes_recipe_plan'):
                    needs_plan = not machine.tools.authorizes_recipe_plan(content,calls)
                creation_attempted = True
                row = store.new_round(session_id, content, calls, "plan_check" if needs_plan else "running", turn_id=turn_id)
                turn_id = row["turn_id"]
                if reply.reasoning_content is not None:
                    reasoning_by_round[row["id"]] = reply.reasoning_content
                for name, arguments, error, elapsed in rejected:
                    yield machine._step_event(store.add_step(row, name, arguments, "rejected", safe_error(error), elapsed))
                invalid = next((error for _, _, error, _ in rejected if error.code in PARAMETER_ERRORS), None)
                if invalid is not None:
                    if needs_plan:
                        store.claim_plan(row['id'])
                    yield from parameter_reply(invalid)
                    return
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
                # 2026-11-13 ruling: no target-equality check against the
                # visible workspace. A global session may act on any registered
                # cube; per-cube consent and live-reference gates below stand.
                denied_candidate = (call["name"] == "annotations.apply_candidate"
                                    and state.get("rejected_candidate_ref") == call["arguments"].get("candidate_ref"))
                denied_save = (call["name"] == "annotations.draft_confirm" and call_cube
                               and state.get("save_denied") == call_cube)
                denied_defaults = (state.get("use_defaults") is False and call["name"] in {"annotations.prepare", "annotations.prepare_batch", "preprocess.run_default"})
                denied_stage = (call["name"] in {'preprocess.run_default', 'preprocess.run', 'preprocess.run_batch'}
                                and state.get("requested_stages") and "preprocess" not in state["requested_stages"])
                manual_missing = ({'annotation', 'save'} & set(state.get('requested_stages') or ())
                                  - set(state.get('stages_done') or ()))
                denied_dependencies = (bool(manual_missing) and 'modeling' in (state.get('requested_stages') or ())
                    and call['name'] in {'preprocess.run', 'preprocess.run_default', 'preprocess.run_batch'})
                denied_modeling = (call['name'] in {'modeling.classify', 'modeling.preflight'} and
                    (state.get('intent') == 'modeling_query' or state.get('modeling_denied') or
                     'modeling' not in (state.get('requested_stages') or ()) or manual_missing))
                exclusive_annotation = denied_stage and re.search(r'(?:只|仅)(?:做|进行)?标注',content or '')
                if exclusive_annotation or not OPEN_ACCESS and (denied_candidate or denied_save or denied_defaults or denied_stage or denied_modeling or denied_dependencies):
                    answer = ("请先人工完成本次要求的标注与保存，再继续预处理和建模。" if denied_dependencies or denied_modeling and manual_missing else
                              "尚未明确授权本次建模，请先确认目标与版本引用。" if denied_modeling else
                              "你只要求了标注，没有要求预处理。需要我继续预处理吗？" if denied_stage else
                              "已遵从你的要求：保留当前进度，未接受候选、未保存新版本。" if denied_candidate or denied_save
                              else "已保留当前进度，没有采用默认参数。请指定希望使用的配置。")
                    if mapping:
                        answer = mapping + "\n" + answer
                    store.save_answer(row["id"], answer)
                    store.round_status(row["id"], "done")
                    yield "clarify", {"question": answer, "task_result": task_result()}
                    return
                fullchain = 'modeling' in (state.get('requested_stages') or ())
                if (not OPEN_ACCESS and call["name"] == "annotations.apply_candidate" and (fullchain or not _authorized(state, call_cube))
                        and state.get("accepted_candidate_ref") != call["arguments"].get("candidate_ref")):
                    answer = "候选预览已生成，尚未写入标注。请查看画布后回复“接受候选”或“不要这个”；已选数据和参数会保留。"
                    if mapping:
                        answer = mapping + "\n" + answer
                    store.save_answer(row["id"], answer)
                    store.round_status(row["id"], "done")
                    yield "clarify", {"question": answer, "task_result": task_result()}
                    return
                tool = machine.tools.resolve(call["name"])
                forced = (machine.tools.requires_confirmation(call['name'],call['arguments'])
                          if hasattr(machine.tools,'requires_confirmation') else None)
                save_authorized = (call["name"] == "annotations.draft_confirm" and call_cube
                                   and state.get("save_requested") == call_cube == state.get("selected_cube_id"))
                if call['name'] == 'annotations.draft_confirm' and call_cube and hasattr(machine.tools,'save_authorized'):
                    save_authorized = machine.tools.save_authorized(call_cube)
                numerical = numerical_confirmation(call)
                if numerical is not None or not OPEN_ACCESS and (forced or tool.human_check and not ((not fullchain and _authorized(state, call_cube)) or save_authorized)):
                    summary = {key: value for key, value in call["arguments"].items()
                               if key in {"cube_id", "revision", "class_code", "overwrite"} and value is not None}
                    if numerical is not None:
                        summary.update(numerical)
                    if forced:
                        summary.update(forced)
                        summary['partial_confirmation_token']=machine.tools.partial_tokens[call['arguments']['dataset_version_id']]
                    step = store.add_step(row, call["name"], call["arguments"], "human_check_pending", summary, 0, tool_call_id=call["id"])
                    machine.state = State.HUMAN_CHECK
                    public_summary={k:v for k,v in summary.items() if k!='partial_confirmation_token'}
                    if numerical is not None:
                        reason = '请核对训练或推理输入，确认后提交。'
                    elif forced:
                        reason = '部分成员可用，确认仍创建完整范围会话'
                    else:
                        reason = '标注版本确认'
                    yield "human_check", {"check_id": step["id"], "tool": call["name"], "summary": public_summary,
                                          "reason":(mapping+"\n" if mapping else "")+reason}
                    return
                previous = [step for batch in store.turn_rounds(session_id, turn_id)
                            for step in store.steps(session_id, batch["id"])
                            if step["status"] in {"ok", "error"} and step["tool"] == call["name"]
                            and json.loads(step["arguments_json"]) == call["arguments"]]
                repeat_limit = machine.tools.explicit_repeat_limit(call['name']) if hasattr(machine.tools,'explicit_repeat_limit') else 1
                if previous and (call["name"] not in READ_TOOLS and len(previous) >= repeat_limit or call['name'] in READ_TOOLS and len(previous) >= 2):
                    raise DataError("AGENT_NO_PROGRESS", "助手重复了相同操作，已停止重复执行并保留进度")
                machine.state = State.CALL_TOOL
                if getattr(machine, 'control', None) is not None:
                    yield 'progress', {'phase': 'tool', 'tool': call['name']}
                step, error = machine._execute(row, call)
                canvas_touched |= not error and call['name'] in memory.CANVAS_ANNOTATION_TOOLS
                result = json.loads(step["result_summary"])
                if not error and call['name'] in memory.CANVAS_ANNOTATION_TOOLS and result.get('cube_id') and result.get('status') not in {'accepted','need_seed','failed'}:
                    canvas_workspace = {'cube_id': result['cube_id'], 'stage': 'annotation',
                        **{k:result[k] for k in ('revision','display_name') if result.get(k) is not None}}
                if call['name'] == 'annotations.prepare_batch':
                    last_batch_status = result.get('status')
                elif call['name'] not in READ_TOOLS and not error:
                    last_batch_status = None
                last_status = result.get("status")
                last_tool = call["name"]
                state = memory.observe(state, call["name"], call["arguments"], result, row["id"])
                if call["name"] == "annotations.draft_confirm" and not error:
                    state.pop("save_requested", None)
                store.save_context(session_id, state)
                yield machine._step_event(step)
                stalled=draft_parameter_stall(machine,turn_id,step,result) if not error else None
                if stalled:
                    store.save_answer(row['id'],stalled)
                    store.round_status(row['id'],'done')
                    yield 'clarify',{'question':stalled,'task_result':'needs_input'}
                    return
                if error and error.code in INPUT_ERRORS:
                    yield from parameter_reply(error)
                    return
                visible = current_workspace()
                if visible and visible != workspace_sent:
                    workspace_sent = visible
                    yield "workspace", visible
                if call['name'] in {'modeling.classify','modeling.regress','workspace.classify'} and not error and last_status not in {'succeeded', 'need_version'}:
                    answer = ('分类训练已在后台受理，任务 ' + result['job_id'] + '。可在页面顶部训练任务中查看进度，或继续对话查询；完整指标尚未生成。'
                              if last_status == 'accepted' and result.get('job_id') else
                              '建模失败，请核对真实运行记录。' if last_status == 'failed' else '建模状态尚未确认，请先查询真实 run；不会自动重训。')
                    store.save_answer(row['id'], answer)
                    store.round_status(row['id'], 'done')
                    yield 'done', {'content': answer, 'step_count': sum(len(store.steps(session_id, batch['id']))
                        for batch in store.turn_rounds(session_id, turn_id)), 'task_result': task_result()}
                    return
                if error and error.code not in RECOVERABLE:
                    raise error
            calls = None
    except (GeneratorExit, RequestCancelled):
        if row is not None:
            store.cancel_running(row["id"])
        raise
    except Exception as exc:
        if not isinstance(exc,DataError):
            import structlog
            import traceback
            frames=traceback.extract_tb(exc.__traceback__)
            structlog.get_logger().error('agent_unhandled',error_type=type(exc).__name__,
                function=frames[-1].name if frames else '',line=frames[-1].lineno if frames else 0)
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
                        **({'annotation_target_cube_ids':[]} if error.code=='TASK_TARGET_REQUIRED' else {}),
                        "task_result": evaluate_task({**state, "last_error": error.code},
                                                     {"run_status": None, "last_status": last_status})}
    finally:
        machine.state = State.IDLE
