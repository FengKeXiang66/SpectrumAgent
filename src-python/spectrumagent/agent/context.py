"""Reference-only working memory for conversational annotation/preprocessing.

The server owns object resolution. Numerical/geometry results still come from
the existing local services; this module never derives scientific results.
"""
import re


_ORDINAL = re.compile(r"(?:第\s*([一二三四五六七八九十百\d]+)\s*[个项份]|序号\s*(?:为|是)?\s*(\d+))")
_SHORT_ID = re.compile(r"(?<![a-zA-Z0-9])([a-fA-F0-9]{3,36})(?:\s*开头|(?=\s*(?:的数据|数据集)))")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}\b")


def user_reference(content):
    match = _UUID.search(content) or _ORDINAL.search(content)
    if match:
        return match.group(0)
    match = re.search(r"(?:前缀[：:\s]*)([a-fA-F0-9]{3,36})", content) or _SHORT_ID.search(content)
    if match:
        return match.group(1)
    match = re.search(r"\b[Dd]\d+\b", content)
    return match.group(0) if match else None


def ordinal(value):
    if value.isdecimal():
        return int(value)
    digits = {c: i for i, c in enumerate("零一二三四五六七八九")}
    if value == "十":
        return 10
    if "十" in value and len(value) <= 3:
        a, b = value.split("十")
        return (digits.get(a, 1) * 10) + digits.get(b, 0)
    return digits.get(value)


def select(state, cube_id, display_name=None):
    changed = state.get("selected_cube_id") != cube_id
    if changed:
        if state.get("selected_cube_id"):
            state["auto_execute"] = False
        for key in ("gesture_ref", "annotation_version_id", "recipe_version_id", "last_run_id",
                    "revision", "candidate_ref", "accepted_candidate_ref", "rejected_candidate_ref",
                    "save_requested", "save_denied", "authorization_cube_id"):
            state.pop(key, None)
    state["selected_cube_id"] = cube_id
    if display_name:
        state["display_name"] = display_name
    elif changed:
        state.pop("display_name", None)
    return changed


def remember_user(state, content, workspace=None):
    """Keep explicit decisions; do not infer materials, geometry or parameters."""
    state = dict(state)
    catalog = state.get("dataset_catalog", [])
    # The visible workbench is a trusted reference, never geometry or spectra.
    if workspace and workspace.get("cube_id"):
        select(state, workspace["cube_id"])
        if workspace.get("gesture_ref"):
            state["gesture_ref"] = workspace["gesture_ref"]
    match = _ORDINAL.search(content)
    index = ordinal(next((part for part in match.groups() if part), "")) if match else None
    candidates = []
    if index is not None:
        candidates = [row for row in catalog if row["index"] == index]
    else:
        explicit = _UUID.search(content) or _SHORT_ID.search(content)
        reference = explicit.group(0) if explicit and _UUID.fullmatch(explicit.group(0)) else explicit.group(1) if explicit else None
        short = re.search(r"\b[Dd](\d+)\b", content)
        if reference:
            candidates = [row for row in catalog if row["id"].lower().startswith(reference.lower())]
        elif short:
            candidates = [row for row in catalog if row["index"] == int(short.group(1))]
        else:
            candidates = [row for row in catalog if row.get("name") and row["name"] in content]
    if len(candidates) == 1:
        select(state, candidates[0]["id"], candidates[0].get("name"))
    if "标注" in content:
        state["intent"] = "annotation"
    if "预处理" in content and "标注" not in content:
        state["intent"] = "preprocess"
    if "默认" in content:
        state["use_defaults"] = not bool(re.search(r"(?:不要|不能|不想|不用|不|别|禁止)\s*(?:使用|用|采用)?\s*默认", content))
    if "背景" in content and any(word in content for word in ("其余", "剩余", "其他")):
        state["include_background"] = True
    information_question = any(word in content for word in ("是什么意思", "如何", "怎么", "是否支持")) and not any(word in content for word in ("请直接", "请帮我", "请自动"))
    if (any(word in content for word in ("不要自动", "不自动", "不能自动", "不想自动", "不需要自动", "禁止自动", "停止自动", "取消自动", "需要确认", "恢复确认"))
            or re.search(r"(?:不要|不能|不想|不|别|禁止)\s*(?:跳过|关闭|取消)\s*确认", content)):
        state.pop("authorization_cube_id", None)
        state["auto_execute"] = False
    elif not information_question and any(word in content for word in ("自动执行", "自动帮我执行", "无需确认", "不用确认")):
        state["auto_execute"] = True
        if state.get("selected_cube_id"):
            state["authorization_cube_id"] = state["selected_cube_id"]
    save_denied = re.search(r"(?:不要|不能|不想|不用|暂不|不|别|禁止)\s*(?:再|先|进行)?\s*保存", content)
    if save_denied:
        state.pop("save_requested", None)
        state["save_denied"] = state.get("selected_cube_id")
    elif "保存" in content and not information_question:
        state["save_requested"] = state.get("selected_cube_id")
        state.pop("save_denied", None)
    acceptance_denied = any(word in content for word in ("不接受", "无法接受", "不能接受", "不想接受", "拒绝候选", "不要这个", "别接受"))
    if acceptance_denied:
        state.pop("accepted_candidate_ref", None)
        state["rejected_candidate_ref"] = state.get("candidate_ref")
    if (state.get("candidate_ref") and any(word in content for word in ("接受", "应用候选", "就用这个", "确认候选"))
            and not information_question
            and not any(word in content for word in ("不接受", "无法接受", "不能接受", "不想接受", "拒绝", "不要", "别接受"))):
        state["accepted_candidate_ref"] = state["candidate_ref"]
        state.pop("rejected_candidate_ref", None)
    return state


def observe(state, tool, arguments, result):
    """Only validated service results advance business state."""
    state = dict(state)
    if result.get("error"):
        state["last_error"] = result["error"]
        return state
    state.pop("last_error", None)
    if tool == "datasets.list":
        count = result.get("dataset_count", result.get("count", 0))
        rows = []
        for i in range(1, min(int(count), 200) + 1):
            identifier = result.get(f"dataset_{i}_id")
            if identifier:
                rows.append({"index": i, "id": identifier,
                             "name": result.get(f"dataset_{i}_name", f"数据 {i}"),
                             "ref": result.get(f"dataset_{i}_ref", f"D{i}")})
        if rows or count == 0:
            state["dataset_catalog"] = rows
    cube_id = result.get("cube_id") or result.get("dataset_id")
    if cube_id and state.get("selected_cube_id") and cube_id != state["selected_cube_id"] and tool != "datasets.resolve":
        # Inspecting an old run or describing another cube is not a selection.
        return state
    if cube_id and (tool != "datasets.resolve" or result.get("status") in (None, "resolved", "ok")):
        select(state, cube_id, result.get("display_name") or result.get("dataset_name") or result.get("name"))
        if state.get("auto_execute") and not state.get("authorization_cube_id"):
            state["authorization_cube_id"] = cube_id
    if "revision" in result:
        state["revision"] = result["revision"]
    if tool == "annotations.context":
        if result.get("latest_annotation_version_id"):
            state["annotation_version_id"] = result["latest_annotation_version_id"]
        if result.get("last_gesture_ref"):
            state["gesture_ref"] = result["last_gesture_ref"]
        if result.get("latest_candidate_ref"):
            state["candidate_ref"] = result["latest_candidate_ref"]
    if tool == "annotations.ensure_labels":
        state["class_codes"] = arguments["class_codes"]
        state["include_background"] = arguments.get("include_background", True)
    if tool.startswith("annotations."):
        state["stage"] = "annotation"
    if tool == "annotations.propose":
        state.pop("accepted_candidate_ref", None)
        state["next_action"] = "need_seed" if result.get("status") == "need_seed" else "review_candidate"
        if result.get("status") == "need_seed":
            state.pop("candidate_ref", None)
            state.pop("accepted_candidate_ref", None)
        if result.get("candidate_ref"):
            state["candidate_ref"] = result["candidate_ref"]
    if tool in {"annotations.apply_candidate", "annotations.reject_candidate"}:
        state.pop("candidate_ref", None)
        state.pop("accepted_candidate_ref", None)
        state.pop("rejected_candidate_ref", None)
    if tool == "annotations.draft_confirm" and result.get("version_id"):
        state["annotation_version_id"] = result["version_id"]
        state["next_action"] = "preprocess"
    if result.get("annotation_version_id"):
        state["annotation_version_id"] = result["annotation_version_id"]
    if result.get("recipe_version_id"):
        state["recipe_version_id"] = result["recipe_version_id"]
    if tool.startswith("preprocess.") and result.get("run_id"):
        state["last_run_id"] = result["run_id"]
        state["stage"] = "preprocess"
        state["next_action"] = "review_preprocess" if result.get("status") == "succeeded" else "inspect_run"
    return state


def resolve_arguments(state, name, arguments):
    """Resolve display order against the exact list the user was shown."""
    if name != "datasets.resolve":
        return arguments
    query = arguments.get("query", "")
    match = _ORDINAL.search(query)
    index = ordinal(next((part for part in match.groups() if part), "")) if match else None
    if re.fullmatch(r"[Dd]\d+", query):
        index = int(query[1:])
    if index is not None:
        row = next((row for row in state.get("dataset_catalog", []) if row["index"] == index), None)
        if row:
            return {**arguments, "query": row["id"]}
    return arguments
