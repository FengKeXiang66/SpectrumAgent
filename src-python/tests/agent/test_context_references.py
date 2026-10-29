"""L1 typed references: pure resolution, additive upgrades and import boundaries."""
import ast
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from spectrumagent.agent import context as memory
from spectrumagent.agent.task import CONTEXT_KEYS


def datasets():
    return memory.observe({}, "datasets.list", {}, {"dataset_count": 2,
        "dataset_1_id": "a" * 32, "dataset_1_name": "sample-081", "dataset_1_ref": "D1",
        "dataset_2_id": "b" * 32, "dataset_2_name": "sample-082", "dataset_2_ref": "D2"}, "round-list")


def choices():
    state = datasets()
    memory.select(state, "b" * 32, "sample-082")
    state = memory.observe(state, "preprocess.recipes", {}, {"recipe_count": 2,
        "recipe_1_id": "recipe-a", "recipe_1_version_id": "version-a", "recipe_1_version_no": 2, "recipe_1_name": "基线",
        "recipe_2_id": "recipe-b", "recipe_2_version_id": "version-b", "recipe_2_version_no": 3, "recipe_2_name": "SNV"}, "round-recipes")
    return memory.observe(state, "annotations.propose", {"class_code": "PP"},
                          {"candidate_ref": "c-deadbeef", "status": "preview", "revision": 3}, "round-candidate")


@pytest.mark.parametrize("content", ["接受第二个候选", "用第二个配方"])
def test_legacy_probe_never_selects_a_dataset_for_another_kind(content):
    state = {"dataset_catalog": datasets()["dataset_catalog"]}
    result = memory.remember_user(state, content)
    assert result.get("selected_cube_id") is None
    assert result["pending_clarify"]["asked"] is False
    assert result["pending_clarify"]["kind"] == ("candidate" if "候选" in content else "recipe")


def test_explicit_data_selection_clears_exact_original_eleven_keys():
    assert memory.CLEAR_ON_DATASET == {"gesture_ref", "annotation_version_id", "recipe_version_id", "last_run_id",
        "revision", "candidate_ref", "accepted_candidate_ref", "rejected_candidate_ref", "save_requested", "save_denied", "authorization_cube_id"}
    state = datasets()
    state["selected_cube_id"] = "a" * 32
    for key in memory.CLEAR_ON_DATASET:
        state[key] = "old"
    result = memory.remember_user(state, "选第二份数据")
    assert result["selected_cube_id"] == "b" * 32
    assert not memory.CLEAR_ON_DATASET.intersection(result)
    assert state["selected_cube_id"] == "a" * 32


def test_recipe_uses_version_id_and_preserves_annotation_and_candidate():
    state = {**choices(), "annotation_version_id": "annotation-v1", "last_run_id": "old-run"}
    result = memory.remember_user(state, "用第二个配方")
    assert result["recipe_version_id"] == "version-b" != "recipe-b"
    assert result["selected_cube_id"] == state["selected_cube_id"]
    assert result["annotation_version_id"] == "annotation-v1"
    assert result["candidate_ref"] == state["candidate_ref"]
    assert "last_run_id" not in result


def test_only_one_candidate_clarification_and_confirmation_preserve_saved_annotation():
    state = {**choices(), "annotation_version_id": "annotation-v1"}
    unclear = memory.remember_user(state, "接受第二个候选")
    assert unclear["pending_clarify"] == {"kind": "candidate", "reason": "only_one", "asked": False}
    assert "accepted_candidate_ref" not in unclear
    unclear["pending_clarify"]["asked"] = True
    confirmed = memory.remember_user(unclear, "就是这个")
    assert confirmed["accepted_candidate_ref"] == state["candidate_ref"]
    assert confirmed["annotation_version_id"] == "annotation-v1"
    assert confirmed["selected_cube_id"] == state["selected_cube_id"]
    assert "pending_clarify" not in confirmed


def test_repeated_unresolved_ordinal_keeps_asked_true_for_controller_to_stop():
    state = choices()
    state["pending_clarify"] = {"kind": "candidate", "reason": "only_one", "asked": True}
    result = memory.remember_user(state, "第二个")
    assert result == state


@pytest.mark.parametrize("content,expected", [
    ("选第二份数据", True), ("用第二个配方", True), ("就是这个", True), ("第二个", True),
    ("删除第二个区域", False), ("用第二个配方做预处理", False), ("对第一个数据标注PP", False),
])
def test_only_choices_finish_locally_while_business_requests_continue(content, expected):
    assert memory.reference_only(content) is expected


def test_need_seed_has_no_bare_ordinal_fallback_to_data():
    state = {**datasets(), "next_action": "need_seed"}
    result = memory.remember_user(state, "第二个")
    assert result.get("selected_cube_id") is None
    assert result["pending_clarify"]["kind"] is None


def test_legacy_upgrade_keeps_order_indexes_and_every_existing_key():
    state = {"dataset_catalog": [{"index": 7, "id": "z", "ref": "D7", "name": "先出现"},
                                 {"index": 2, "id": "a", "ref": "D2", "name": "后出现"}],
             "future_l2_key": {"keep": True}, "annotation_version_id": "v1"}
    before = deepcopy(state)
    result = memory.upgrade_context(state)
    assert state == before
    assert {key: result[key] for key in state} == state
    catalog = result["catalogs"]["dataset"]
    assert [item["ordinal"] for item in catalog["items"]] == [7, 2]
    assert [item["id"] for item in catalog["items"]] == ["z", "a"]
    assert catalog["round_id"] is None and catalog["source"] == "legacy.dataset_catalog"
    assert memory.upgrade_context(result) == result
    assert memory.resolve_reference(result, "第二个", None)[2] == {"reason": "stale"}


@pytest.mark.parametrize("state,last_tool,expected", [
    ({"next_action": "need_seed", "candidate_ref": "c1"}, "preprocess.recipes", None),
    ({"candidate_ref": "c1"}, None, "candidate"),
    ({}, "preprocess.recipes", "recipe"),
    ({}, "annotations.context", "region"),
    ({}, None, "dataset"),
    ({"selected_cube_id": "c1"}, "datasets.describe", "dataset"),
    ({"candidate_ref": "c1", "accepted_candidate_ref": "c1"}, None, "dataset"),
    ({"candidate_ref": "c1", "rejected_candidate_ref": "c1"}, None, "dataset"),
])
def test_active_catalog_priority_is_pure(state, last_tool, expected):
    before = deepcopy(state)
    assert memory.active_catalog(state, last_tool) == expected
    assert state == before


@pytest.mark.parametrize("content,kind,identifier", [
    ("D2", "dataset", "b" * 32), ("C1", "candidate", "c-deadbeef"),
    ("P2", "recipe", "version-b"), ("用第二个配方", "recipe", "version-b"),
    ("在当前数据上用第二个配方", "recipe", "version-b"),
    ("在当前数据上用 P2", "recipe", "version-b"),
    ("在 D1 上用第二个配方", "recipe", "version-b"),
    ("第一个候选", "candidate", "c-deadbeef"),
])
def test_typed_reference_never_crosses_catalogs(content, kind, identifier):
    resolved_kind, item, clarify = memory.resolve_reference(choices(), content, None)
    assert (resolved_kind, item["id"], clarify) == (kind, identifier, None)


@pytest.mark.parametrize("tool,key,value,expected", [
    ("annotations.apply_candidate", "candidate_ref", "第二个", "c-second"),
    ("annotations.reject_candidate", "candidate_ref", "C1", "c-deadbeef"),
    ("preprocess.run_default", "recipe_version_id", "P2", "version-b"),
    ("preprocess.run_default", "recipe_version_id", "第2个", "version-b"),
    ("annotations.edit_region", "region_id", "R1", "region-a"),
])
def test_arguments_replace_only_the_requested_kind(tool, key, value, expected):
    state = choices()
    # v1 stores one candidate; two entries here isolate the index replacement contract.
    memory._catalog(state, "candidate", state["catalogs"]["candidate"]["items"] + [
        {"ordinal": 2, "id": "c-second", "ref": "C2", "display": "第二项", "version": 3}], "fixture", "r1")
    state = memory.observe(state, "annotations.context", {}, {"region_1_id": "region-a", "revision": 3}, "round-regions")
    arguments = {key: value, "cube_id": "b" * 32}
    before = deepcopy(arguments)
    assert memory.resolve_arguments(state, tool, arguments)[key] == expected
    assert arguments == before


@pytest.mark.parametrize("tool,key,value", [
    ("annotations.apply_candidate", "candidate_ref", "c-0123456789abcdef"),
    ("preprocess.run_default", "recipe_version_id", "00000000-1111-2222-3333-444444444444"),
    ("annotations.edit_region", "region_id", "00000000-1111-2222-3333-444444444444"),
])
def test_real_ids_and_none_are_never_rewritten_or_injected(tool, key, value):
    arguments = {key: value}
    assert memory.resolve_arguments(choices(), tool, arguments) == arguments
    assert memory.resolve_arguments(choices(), tool, {}) == {}


def test_snapshot_formula_idempotence_change_and_four_entry_fifo():
    state = datasets()
    items = state["catalogs"]["dataset"]["items"]
    assert memory.snapshot_id("dataset", items) == memory.snapshot_id("dataset", deepcopy(items))
    expected = sha256(("dataset" + "\x1f".join(item["id"] for item in items) + "\x1f".join(str(item["version"]) for item in items)).encode()).hexdigest()[:8]
    assert memory.snapshot_id("dataset", items) == expected
    changed = deepcopy(items)
    changed[0]["version"] = 1
    assert memory.snapshot_id("dataset", changed) != expected
    snapshots = []
    for version in range(6):
        current = [{**items[0], "version": version}]
        memory._catalog(state, "dataset", current, "datasets.list", f"r-{version}")
        snapshots.append(memory.snapshot_id("dataset", current))
    history = state["catalogs"]["dataset"]["history"]
    assert [entry["snapshot_id"] for entry in history] == snapshots[-4:]
    memory._catalog(state, "dataset", current, "datasets.list", "r-repeat")
    assert len(state["catalogs"]["dataset"]["history"]) == 4


def test_region_selection_is_a_noop_and_does_not_change_ordinal_direction():
    state = memory.observe(choices(), "annotations.context", {},
                           {"region_1_id": "oldest-visible", "region_2_id": "newest", "revision": 4}, "r1")
    before = deepcopy(state)
    assert memory.remember_user(state, "选第二个区域") == before
    assert [item["id"] for item in state["catalogs"]["region"]["items"]] == ["oldest-visible", "newest"]


def test_new_keys_and_literal_catalog_writes_are_visible_to_l0():
    assert {"catalogs", "pending_clarify"} <= CONTEXT_KEYS
    tree = ast.parse(Path(memory.__file__).read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert not (isinstance(node.func.value, ast.Name) and node.func.value.id == "state" and node.func.attr == "update")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                assert not (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Subscript)
                            and isinstance(target.value.slice, ast.Constant) and target.value.slice.value == "catalogs")


def test_workflow_has_no_module_level_task_import_and_no_projection_calls():
    path = Path(memory.__file__).with_name("workflow.py")
    tree = ast.parse(path.read_text("utf-8"))
    imports = [node for root in tree.body if not isinstance(root, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               for node in ast.walk(root) if isinstance(node, (ast.ImportFrom, ast.Import))]
    assert not [node for node in imports if (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "task")
                or any(alias.name.split(".")[-1] == "task" for alias in node.names)]
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and ((isinstance(node.func, ast.Name) and node.func.id == "normalize_context")
                     or (isinstance(node.func, ast.Attribute) and node.func.attr == "normalize_context"))]
