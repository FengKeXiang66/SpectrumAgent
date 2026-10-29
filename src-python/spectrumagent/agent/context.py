"""Reference-only working memory for conversational annotation/preprocessing.

The server owns object resolution. Numerical/geometry results still come from
the existing local services; this module never derives scientific results.
"""
from hashlib import sha256
import re


_ORDINAL = re.compile(r"(?:第\s*([一二三四五六七八九十百\d]+)\s*[个项份块]|序号\s*(?:为|是)?\s*(\d+))")
_SHORT_ID = re.compile(r"(?<![a-zA-Z0-9])([a-fA-F0-9]{3,36})(?:\s*开头|(?=\s*(?:的数据|数据集)))")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}\b")
_REF = re.compile(r"\b([DdCcPpRr])(\d+)\b")
_KINDS = {"数据": "dataset", "数据集": "dataset", "份": "dataset", "候选": "candidate",
          "配方": "recipe", "方案": "recipe", "区域": "region", "块": "region"}
CLEAR_ON_DATASET = frozenset({"gesture_ref", "annotation_version_id", "recipe_version_id", "last_run_id",
    "revision", "candidate_ref", "accepted_candidate_ref", "rejected_candidate_ref",
    "save_requested", "save_denied", "authorization_cube_id"})
CLEAR_ON_CANDIDATE = frozenset({"candidate_ref", "accepted_candidate_ref", "rejected_candidate_ref"})
CLEAR_ON_RECIPE = frozenset({"recipe_version_id", "last_run_id"})
CLEAR_ON_REGION = frozenset()


def snapshot_id(kind, items):
    payload = kind + "\x1f".join(item["id"] for item in items) + "\x1f".join(str(item["version"]) for item in items)
    return sha256(payload.encode("utf-8")).hexdigest()[:8]


def _catalog(state, kind, items, source, round_id):
    """Replace the complete root so the literal-write drift check sees it."""
    items = [dict(item) for item in items]
    digest = snapshot_id(kind, items)
    previous = state.get("catalogs", {}).get(kind, {})
    history = [entry for entry in previous.get("history", []) if entry["snapshot_id"] != digest]
    entry = {"snapshot_id": digest, "source": source, "round_id": round_id, "items": items}
    history = (history + [{**entry, "items": [dict(item) for item in items]}])[-4:]
    state["catalogs"] = {**state.get("catalogs", {}), kind: {**entry, "history": history}}


def upgrade_context(state):
    """Add the legacy catalogue without projecting, sorting or dropping keys."""
    state = dict(state)
    if "catalogs" not in state and state.get("dataset_catalog"):
        items = [{"ordinal": row["index"], "id": row["id"], "ref": row["ref"],
                  "display": row["name"], "version": None} for row in state["dataset_catalog"]]
        _catalog(state, "dataset", items, "legacy.dataset_catalog", None)
    return state


def active_catalog(state, last_tool):
    if state.get("next_action") == "need_seed":
        return None
    candidate = state.get("candidate_ref")
    if candidate and candidate not in {state.get("accepted_candidate_ref"), state.get("rejected_candidate_ref")}:
        return "candidate"
    if last_tool == "preprocess.recipes" and not state.get("recipe_version_id"):
        return "recipe"
    if last_tool == "annotations.context":
        return "region"
    if not state.get("selected_cube_id"):
        return "dataset"
    return "dataset"


def _index(content):
    match = _ORDINAL.search(content)
    if match:
        return ordinal(next(part for part in match.groups() if part))
    match = re.fullmatch(r"第?\s*([一二三四五六七八九十百\d]+)\s*(?:个|项|份)?", content)
    return ordinal(match[1]) if match else None


def reference_request(state, content):
    if _ORDINAL.search(content) or _REF.search(content) or _UUID.search(content) or _SHORT_ID.search(content):
        return True
    if re.search(r"前缀[：:\s]*[a-fA-F0-9]{3,36}", content):
        return True
    if state.get("pending_clarify") and content.strip() in {"就是这个", "是它", "是的", "就这个"}:
        return True
    return any(row.get("name") and row["name"] in content for row in state.get("dataset_catalog", []))


def reference_only(content):
    """Only a choice can finish locally; edits and compound work still reach the model."""
    return bool(re.fullmatch(r"(?:选(?:择)?|用|使用|接受|确认)?\s*(?:第\s*[一二三四五六七八九十百\d]+\s*[个项份块]"
                            r"(?:\s*(?:数据集|数据|候选|配方|方案|区域|块))?|序号\s*(?:为|是)?\s*\d+|"
                            r"[DdCcPpRr]\d+|就是这个|是它|是的|就这个)[。.!！]?", content.strip()))


def resolve_reference(state, content, last_tool, *, recent_round_ids=None):
    """Resolve one typed reference; freshness supplied by the caller is transient."""
    pending = state.get("pending_clarify") or {}
    if content.strip() in {"就是这个", "是它", "是的", "就这个"} and pending.get("reason") == "only_one":
        kind = pending["kind"]
        items = state.get("catalogs", {}).get(kind, {}).get("items", [])
        return (kind, items[0], None) if len(items) == 1 else (kind, None, {"reason": "stale"})
    match, short = _ORDINAL.search(content), _REF.search(content)
    nouns = list(re.finditer(r"数据集|数据|候选|配方|方案|区域|份|块", content))
    # Prefer the noun attached to the ordinal, e.g. "当前数据用第二个配方".
    noun = min(nouns, key=lambda n: min(abs(n.start() - match.end()), abs(n.end() - match.start()))) if nouns and match else (nouns[0] if nouns else None)
    short_kind = {"D": "dataset", "C": "candidate", "P": "recipe", "R": "region"}.get(short[1].upper()) if short else None
    kind = (short_kind if short and not match else _KINDS[noun.group()] if noun else
            short_kind if short else active_catalog(state, last_tool))
    index = _index(content) if match else int(short[2]) if short else _index(content)
    if not reference_request(state, content) and index is None:
        return None, None, {"reason": "not_found"}
    catalog = state.get("catalogs", {}).get(kind, {})
    items = catalog.get("items", [])
    if kind is None:
        return None, None, {"reason": "not_found"}
    if index is not None:
        if not items:
            return kind, None, {"reason": "not_found"}
        if catalog.get("round_id") is None or (not noun and not short and recent_round_ids is not None
                                                and catalog["round_id"] not in recent_round_ids):
            return kind, None, {"reason": "stale"}
        item = next((item for item in items if item["ordinal"] == index), None)
        return (kind, item, None) if item else (kind, None, {"reason": "only_one" if len(items) == 1 else "not_found"})
    explicit = _UUID.search(content)
    prefix = re.search(r"前缀[：:\s]*([a-fA-F0-9]{3,36})", content) or _SHORT_ID.search(content)
    value = explicit[0] if explicit else prefix[1] if prefix else None
    if value:
        kind = "dataset"
        items = state.get("catalogs", {}).get(kind, {}).get("items", [])
    matches = [item for item in items if (value and item["id"].lower().startswith(value.lower()))
               or (not value and item["display"] and item["display"] in content)]
    return (kind, matches[0], None) if len(matches) == 1 else (kind, None, {"reason": "not_found"})


def reference_mapping(kind, item, *, refreshed=False):
    index, name, ref = item["ordinal"], item["display"], item["ref"]
    if refreshed:
        return f"已刷新列表，第 {index} 个现在是 {name}（{ref}）"
    if kind == "dataset":
        return f"已选第 {index} 份数据：{name}（{ref}）"
    return f"第 {index} 个{dict(candidate='候选', recipe='配方', region='区域')[kind]}：{name}（{ref}）"


def user_reference(content, state=None, last_tool=None):
    if state is not None:
        kind, item, _ = resolve_reference(state, content, last_tool)
        if item and kind == "dataset":
            return item["id"]
        if kind != "dataset":
            return None
    elif re.search(r"候选|配方|方案|区域|块", content):
        return None
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
        for key in CLEAR_ON_DATASET:
            state.pop(key, None)
        state.pop("requested_stages", None)
        state.pop("stages_done", None)
        if state.get("catalogs"):
            state["catalogs"] = {kind: value for kind, value in state["catalogs"].items() if kind not in {"candidate", "region"}}
    state["selected_cube_id"] = cube_id
    if display_name:
        state["display_name"] = display_name
    elif changed:
        state.pop("display_name", None)
    return changed


def set_candidate(state, item):
    changed = state.get("candidate_ref") != item["id"]
    if changed:
        for key in CLEAR_ON_CANDIDATE:
            state.pop(key, None)
    state["candidate_ref"] = item["id"]
    return changed


def set_recipe(state, item):
    changed = state.get("recipe_version_id") != item["id"]
    if changed:
        for key in CLEAR_ON_RECIPE:
            state.pop(key, None)
    state["recipe_version_id"] = item["id"]
    return changed


def set_region(state, item):
    return False  # Region references only replace explicit tool arguments in L1.


def remember_user(state, content, workspace=None, last_tool=None, *, recent_round_ids=None):
    """Keep explicit decisions; do not infer materials, geometry or parameters."""
    state = upgrade_context(state)
    # The visible workbench is a trusted reference, never geometry or spectra.
    if workspace and workspace.get("cube_id"):
        select(state, workspace["cube_id"])
        if workspace.get("gesture_ref"):
            state["gesture_ref"] = workspace["gesture_ref"]
    confirmation = content.strip() in {"就是这个", "是它", "是的", "就这个"}
    if reference_request(state, content):
        kind, item, clarify = resolve_reference(state, content, last_tool, recent_round_ids=recent_round_ids)
        if clarify:
            previous = state.get("pending_clarify") or {}
            state["pending_clarify"] = (dict(previous) if previous.get("asked") and previous.get("kind") == kind else
                                        {"kind": kind, "reason": clarify["reason"], "asked": False})
        else:
            state.pop("pending_clarify", None)
            if kind == "dataset":
                select(state, item["id"], item["display"])
            elif kind == "candidate":
                set_candidate(state, item)
            elif kind == "recipe":
                set_recipe(state, item)
            else:
                set_region(state, item)
    stages = (("annotation", r"标注"), ("save", r"保存"),
              ("preprocess", r"预处理|跑一下"), ("compare", r"比较|对比"))
    requested = set(state.get("requested_stages") or ())
    mentioned = False
    for stage, words in stages:
        if re.search(words, content):
            mentioned = True
            if re.search(r"(?:不要|不用|先不|暂不|别)\s*(?:再|先|进行|做|执行|确认)?\s*(?:" + words + r")", content):
                requested.discard(stage)
            else:
                requested.add(stage)
    if mentioned or "requested_stages" in state:
        state["requested_stages"] = [stage for stage, _ in stages if stage in requested]
        state["intent"] = "preprocess" if "preprocess" in requested and "annotation" not in requested else "annotation"
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
    if (state.get("candidate_ref") and not state.get("pending_clarify")
            and (any(word in content for word in ("接受", "应用候选", "就用这个", "确认候选")) or confirmation)
            and not information_question
            and not any(word in content for word in ("不接受", "无法接受", "不能接受", "不想接受", "拒绝", "不要", "别接受"))):
        state["accepted_candidate_ref"] = state["candidate_ref"]
        state.pop("rejected_candidate_ref", None)
    return state


def observe(state, tool, arguments, result, round_id=None):
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
            _catalog(state, "dataset", [{"ordinal": row["index"], "id": row["id"], "ref": row["ref"],
                     "display": row["name"], "version": None} for row in rows], tool, round_id)
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
            code = result.get("latest_candidate_class_code", "")
            _catalog(state, "candidate", [{"ordinal": 1, "id": result["latest_candidate_ref"], "ref": "C1",
                "display": f"{code} 候选 1".strip(), "version": result.get("latest_candidate_revision")}], tool, round_id)
        regions = sorted((int(match[1]), value) for key, value in result.items()
                         if (match := re.fullmatch(r"region_(\d+)_id", key)))
        _catalog(state, "region", [{"ordinal": i, "id": value, "ref": f"R{i}", "display": f"区域 {i}",
                                   "version": result.get("revision")} for i, value in regions], tool, round_id)
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
            _catalog(state, "candidate", [], tool, round_id)
        if result.get("candidate_ref"):
            state["candidate_ref"] = result["candidate_ref"]
            code = result.get("class_code") or arguments.get("class_code", "")
            _catalog(state, "candidate", [{"ordinal": 1, "id": result["candidate_ref"], "ref": "C1",
                "display": f"{code} 候选 1".strip(), "version": result.get("revision")}], tool, round_id)
    if tool in {"annotations.apply_candidate", "annotations.reject_candidate"}:
        state.pop("candidate_ref", None)
        state.pop("accepted_candidate_ref", None)
        state.pop("rejected_candidate_ref", None)
        _catalog(state, "candidate", [], tool, round_id)
    if tool == "annotations.draft_confirm" and result.get("version_id"):
        state["annotation_version_id"] = result["version_id"]
        state["next_action"] = "preprocess"
        state["stages_done"] = sorted(set(state.get("stages_done") or ()) | {"annotation", "save"})
    if result.get("annotation_version_id"):
        state["annotation_version_id"] = result["annotation_version_id"]
    if result.get("recipe_version_id"):
        state["recipe_version_id"] = result["recipe_version_id"]
    if tool == "preprocess.recipes":
        items = [{"ordinal": i, "id": result[f"recipe_{i}_version_id"], "ref": f"P{i}",
                  "display": result[f"recipe_{i}_name"], "version": result[f"recipe_{i}_version_no"]}
                 for i in range(1, result.get("recipe_count", 0) + 1) if result.get(f"recipe_{i}_version_id")]
        _catalog(state, "recipe", items, tool, round_id)
    if tool.startswith("preprocess.") and result.get("run_id"):
        state["last_run_id"] = result["run_id"]
        state["stage"] = "preprocess"
        state["next_action"] = "review_preprocess" if result.get("status") == "succeeded" else "inspect_run"
    if tool == "preprocess.run_default" and result.get("status") == "succeeded":
        state["stages_done"] = sorted(set(state.get("stages_done") or ()) | {"preprocess"})
    return state


def resolve_arguments(state, name, arguments):
    """Resolve display order against the exact list the user was shown."""
    if name == "preprocess.run_default":
        # Validation supplies Optional fields before this runtime boundary.
        arguments = {**arguments, **{key: state[key] for key in ("annotation_version_id", "recipe_version_id")
                                    if key in arguments and arguments[key] is None and state.get(key) is not None}}
    targets = {"annotations.apply_candidate": ("candidate", "candidate_ref"),
               "annotations.reject_candidate": ("candidate", "candidate_ref"),
               "preprocess.run_default": ("recipe", "recipe_version_id"),
               "annotations.edit_region": ("region", "region_id")}
    if name in targets:
        kind, key = targets[name]
        value = arguments.get(key)
        if not isinstance(value, str) or not (re.fullmatch(r"第?\s*[一二三四五六七八九十百\d]+\s*个?", value)
                                             or re.fullmatch({"candidate": r"[Cc]\d+", "recipe": r"[Pp]\d+", "region": r"[Rr]\d+"}[kind], value)):
            return arguments
        short = _REF.fullmatch(value)
        index = int(short[2]) if short else _index(value)
        item = next((row for row in state.get("catalogs", {}).get(kind, {}).get("items", []) if row["ordinal"] == index), None)
        return {**arguments, key: item["id"]} if item else arguments
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
