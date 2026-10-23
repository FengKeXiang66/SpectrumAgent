"""12.2: schema and runtime geometry prohibition, explicit handler readiness."""
from copy import deepcopy
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from backend.database import connect_database
from spectrumagent.agent import llm, skill
from spectrumagent.agent.tools import (
    DraftRegionArguments, NoArguments, ToolInput, ToolRegistry, build_registry,
)
from spectrumagent.data import DataError
from .conftest import MESSAGES, mock_client


EXPECTED_NAMES = {"datasets.list", "datasets.describe", "annotations.draft_get", "annotations.draft_add_region",
    "annotations.draft_select_candidates", "annotations.draft_confirm", "preprocess.run", "preprocess.compare",
    "training_mat.export", "settings.llm_get"}
PENDING = {
    "annotations.draft_get": {"cube_id": "cube-1"},
    "annotations.draft_add_region": {"cube_id": "cube-1", "revision": 1, "class_code": "PP", "geometry": {"gesture_ref": "gesture-1"}},
    "annotations.draft_select_candidates": {"cube_id": "cube-1", "class_code": "PP", "method": "SLIC", "params": {"n_segments": 8, "compactness": 1.0, "pca_components": 3}},
    "annotations.draft_confirm": {"cube_id": "cube-1", "revision": 1},
    "training_mat.export": {"cube_id": "cube-1", "version_id": "version-1"},
}


def independently_scan_schema(node):
    if isinstance(node, dict):
        assert not {"points", "coords", "polygon", "spectra", "values", "bands"} & set(node.get("properties", {}))
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
        for value in node.values():
            independently_scan_schema(value)
    elif isinstance(node, list):
        for value in node:
            independently_scan_schema(value)


def test_v1_catalogue_snapshot_and_live_schemas_independent_static_scan(gateway_case):
    registry = build_registry()
    live = registry.snapshot()
    with connect_database(gateway_case.database) as db:
        persisted = json.loads(skill.active_skill(db)["tools_json"])
    assert {tool["function"]["name"] for tool in persisted} == EXPECTED_NAMES
    assert len(persisted) == len(EXPECTED_NAMES) and persisted == live
    for catalogue in (persisted, live):
        for tool in catalogue:
            assert tool["type"] == "function" and tool["function"]["description"]
            independently_scan_schema(tool["function"]["parameters"])
            independently_scan_schema(registry.resolve(tool["function"]["name"]).adapter.json_schema())
    # §10-7 is not exercised by these read/add/select/confirm tools: retain the
    # specified summary, do not pre-add region listings or truncation fields.
    description = registry.resolve("annotations.draft_get").description
    for field in ("cube_id", "revision", "n_regions", "n_classes", "updated_at", "estimated_mat_bytes"):
        assert field in description
    assert "region_id" not in description and "truncated" not in description


def test_seed_prompt_and_complete_catalogue_pass_existing_gateway_without_network(gateway_case):
    with connect_database(gateway_case.database) as db:
        seeded = skill.active_skill(db)
    tools = json.loads(seeded["tools_json"])
    assert "$ref" not in seeded["tools_json"] and "$defs" not in seeded["tools_json"]
    client, transport = mock_client(gateway_case)
    result = client.chat([{"role": "system", "content": seeded["system_prompt"]}, *MESSAGES], tools)
    transport.assert_called_once()
    assert result.tool_calls[0].name == "datasets.describe"
    validated = build_registry().validate(result.tool_calls[0].name, result.tool_calls[0].arguments_json)
    assert validated.dataset_id == "cube-1"


@pytest.mark.parametrize("name", list(PENDING))
def test_unready_tools_have_registered_schema_and_explicit_failure(gateway_case, name):
    registry = build_registry(database=gateway_case.database)
    assert not registry.resolve(name).ready
    registry.validate(name, PENDING[name])
    with pytest.raises(DataError) as caught:
        registry.invoke(name, PENDING[name])
    assert caught.value.code == "TOOL_NOT_IMPLEMENTED"


@pytest.mark.parametrize("op", ["add", "uncertain", "erase"])
def test_gesture_reference_is_only_geometry_and_each_valid_op_executes(op):
    registry = ToolRegistry()
    handler = Mock(return_value={"ok": True})
    registry.register("region", DraftRegionArguments, "fixture", handler)
    arguments = {"cube_id": "cube-1", "revision": 1, "op": op, "geometry": {"gesture_ref": "gesture-1"}}
    if op == "add":
        arguments["class_code"] = "PP"
    assert registry.invoke("region", arguments) == {"ok": True}
    handler.assert_called_once()
    assert handler.call_args.args[0].geometry.gesture_ref == "gesture-1"


@pytest.mark.parametrize("op", ["uncertain", "erase"])
@pytest.mark.parametrize("extra", [{"class_code": "PP"}, {"confidence": "high"}, {"class_code": None}, {"confidence": None}])
def test_uncertain_erase_forbid_class_and_confidence_even_null(op, extra):
    registry = ToolRegistry()
    handler = Mock(return_value={"ok": True})
    registry.register("region", DraftRegionArguments, "fixture", handler)
    with pytest.raises(DataError) as caught:
        registry.invoke("region", {"cube_id": "cube-1", "revision": 1, "op": op,
            "geometry": {"gesture_ref": "gesture-1"}, **extra})
    assert caught.value.code == "TOOL_ARGS_INVALID"
    handler.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"geometry": {"points": [[1, 2], [3, 4]]}}, {"geometry": {"polygon": [[1, 2], [3, 4]]}},
    {"geometry": {"gesture_ref": "gesture-1", "coords": [[1, 2]]}}, {"points": [[1, 2]]},
    {"spectra": [1.0, 2.0]}, {"bands": [0]}, {"class_code": None}, {"revision": "1"},
    {"revision": True}, {"revision": 0}, {"source": "algorithm"},
])
def test_invalid_geometry_extra_or_coerced_types_reject_before_handler(changes):
    registry = ToolRegistry()
    handler = Mock(return_value={"ok": True})
    registry.register("region", DraftRegionArguments, "fixture", handler)
    arguments = {**PENDING["annotations.draft_add_region"], **changes}
    with pytest.raises(DataError) as caught:
        registry.invoke("region", arguments)
    assert caught.value.code == "TOOL_ARGS_INVALID"
    assert caught.value.as_dict()["context"] == {}
    handler.assert_not_called()


def test_add_requires_class_code_and_json_input_is_strict():
    registry = build_registry()
    arguments = deepcopy(PENDING["annotations.draft_add_region"])
    del arguments["class_code"]
    with pytest.raises(DataError) as caught:
        registry.validate("annotations.draft_add_region", json.dumps(arguments))
    assert caught.value.code == "TOOL_ARGS_INVALID"
    arguments["class_code"] = "PP"
    assert registry.validate("annotations.draft_add_region", json.dumps(arguments)).op == "add"
    arguments["revision"] = "1"
    with pytest.raises(DataError):
        registry.validate("annotations.draft_add_region", json.dumps(arguments))


def test_candidates_require_typed_parameters_reject_nested_geometry_and_unknown_method():
    registry = build_registry()
    slic = PENDING["annotations.draft_select_candidates"]
    assert registry.validate("annotations.draft_select_candidates", slic).method == "SLIC"
    sam = {"cube_id": "cube-1", "class_code": "PP", "method": "SAM", "params": {
        "gesture_ref": "gesture-1", "threshold": 0.9, "queue_min_similarity": 0.8}}
    assert registry.validate("annotations.draft_select_candidates", sam).method == "SAM"
    for invalid in ({**sam, "method": "invented"}, {**sam, "params": {}},
                    {**sam, "params": {**sam["params"], "seed": {"point": [1, 2]}}},
                    {**slic, "params": {**slic["params"], "values": [[1, 2]]}}):
        with pytest.raises(DataError) as caught:
            registry.validate("annotations.draft_select_candidates", invalid)
        assert caught.value.code == "TOOL_ARGS_INVALID"


def test_registry_rejects_geometric_or_open_schemas_duplicate_and_unknown_tools():
    class Forbidden(ToolInput):
        points: list[list[int]]
    class OpenValue(ToolInput):
        params: Any
    class OpenObject(ToolInput):
        params: dict[str, Any]
    registry = ToolRegistry()
    for arguments in (Forbidden, OpenValue, OpenObject):
        with pytest.raises(ValueError):
            registry.register("unsafe", arguments, "fixture")
    registry.register("safe", NoArguments, "fixture", lambda _: {"ok": True})
    with pytest.raises(ValueError, match="duplicate"):
        registry.register("safe", NoArguments, "fixture")
    with pytest.raises(DataError) as caught:
        registry.resolve("missing")
    assert caught.value.code == "TOOL_NOT_FOUND"
    with pytest.raises(DataError) as caught:
        registry.invoke("safe", '{"private":')
    assert caught.value.code == "TOOL_ARGS_INVALID"


def test_existing_service_bindings_filter_paths_geometries_and_credentials(gateway_case):
    c = gateway_case
    # Deliberately contaminated service fixtures: only whitelisted values may
    # survive. Numerical values are provider/service fixture values, not guesses.
    datasets = SimpleNamespace(database=c.database, get=Mock(return_value=(SimpleNamespace(
        shape=(5, 6, 7), dtype="uint16", interleave="bil", name="private.img", data_path="C:/private/cube"), False)))
    row = {"id": "run-1", "status": "succeeded", "recipe_version_id": "recipe-1", "cube_id": "cube-1",
           "annotation_version_id": "version-1", "input_fingerprint": "digest", "error": None,
           "artifacts": [{"relative_path": "private/data.mat"}], "sample_pixels": [[1, 2]],
           "metrics": {"fisher": 3.5, "snr": {"mean": 7.5}, "values": [[1, 2]]}}
    runner = SimpleNamespace(run=Mock(return_value=row))
    comparison = SimpleNamespace(compare=Mock(return_value={"runs": [row], "ranking": [
        {"rank": 1, "run_id": "run-1", "recipe_version_id": "recipe-1", "fisher": 3.5}], "document": {"points": [[1, 2]]}}))
    registry = build_registry(datasets=datasets, runner=runner, comparison=comparison, database=c.database)
    assert registry.snapshot() == build_registry().snapshot()
    assert {name for name in EXPECTED_NAMES if registry.resolve(name).ready} == EXPECTED_NAMES - set(PENDING)
    with connect_database(c.database) as db:
        db.execute("INSERT INTO dataset_registry (id,header_key,raw,payload) VALUES ('cube-1','fixture',1,'{}')")
    llm.set_api_key("test-memory-only")
    summaries = [registry.invoke("datasets.list", {}), registry.invoke("datasets.describe", {"dataset_id": "cube-1"}),
        registry.invoke("preprocess.run", {"cube_id": "cube-1", "annotation_version_id": "version-1", "recipe_version_id": "recipe-1"}),
        registry.invoke("preprocess.compare", {"cube_id": "cube-1", "annotation_version_id": "version-1", "recipe_version_ids": ["recipe-1"]}),
        registry.invoke("settings.llm_get", {})]
    assert summaries[0] == {"count": 1, "dataset_ids": "cube-1"}
    assert summaries[1] == {"dataset_id": "cube-1", "n_lines": 5, "n_samples": 6, "n_bands": 7, "dtype": "uint16", "interleave": "bil"}
    assert summaries[2]["fisher"] == 3.5 and summaries[2]["snr_mean"] == 7.5
    assert summaries[3]["rank_1_run_id"] == "run-1" and summaries[3]["rank_1_fisher"] == 3.5
    assert summaries[4]["configured"] is True and summaries[4]["model"] == "mock-model"
    runner.run.assert_called_once_with("cube-1", "version-1", "recipe-1")
    comparison.compare.assert_called_once_with("cube-1", "version-1", ["recipe-1"])
    for summary in summaries:
        assert not llm._egress_blocked(summary)
        text = json.dumps(summary)
        assert all(value not in text for value in ("[[", "private", "document", "sample_pixels", "test-memory-only", "base_url"))
        assert all(value is None or type(value) in (str, int, float, bool) for value in summary.values())


@pytest.mark.parametrize("summary", [{"document": "forbidden"}, {"count": [[1, 2]]}, {"count": float("nan")}])
def test_framework_rejects_non_scalar_or_forbidden_handler_output(summary):
    registry = ToolRegistry()
    registry.register("fixture", NoArguments, "fixture", lambda _: summary)
    with pytest.raises(DataError) as caught:
        registry.invoke("fixture", {})
    assert caught.value.code == "TOOL_RESULT_INVALID"
