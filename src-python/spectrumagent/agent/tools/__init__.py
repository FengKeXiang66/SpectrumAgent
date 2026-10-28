"""Strict tool inputs, complete v1 catalogue, service bindings and safe summaries.

No draft or MAT implementation lives here. Their schemas are frozen into v1
now; a missing handler raises TOOL_NOT_IMPLEMENTED after argument validation.
"""
from dataclasses import dataclass
import math
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from backend.database import connect_database
from spectrumagent.data import DataError
from .annotations import draft_get, draft_confirm, add_region, select_candidates


class ToolInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


Reference = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]


class NoArguments(ToolInput):
    pass


class DescribeArguments(ToolInput):
    dataset_id: Reference


class CubeArguments(ToolInput):
    cube_id: Reference


class GestureReference(ToolInput):
    gesture_ref: Reference


class RegionArguments(CubeArguments):
    revision: PositiveInt
    geometry: GestureReference


class AddRegionArguments(RegionArguments):
    op: Literal["add"] = "add"  # TASK-07 §2.4: omitted op means add.
    class_code: Reference
    confidence: Literal["high", "medium", "low"] | None = None


class UncertainRegionArguments(RegionArguments):
    op: Literal["uncertain"]


class EraseRegionArguments(RegionArguments):
    op: Literal["erase"]


# Distinct extra-forbid branches prohibit even null class/confidence on erase
# or uncertain, in JSON Schema as well as Pydantic validation.
DraftRegionArguments = AddRegionArguments | UncertainRegionArguments | EraseRegionArguments


class SLICParameters(ToolInput):
    # Fields/ranges from #04 SuperpixelRequest, with no invented tool defaults.
    n_segments: PositiveInt
    compactness: Annotated[float, Field(gt=0)]
    pca_components: PositiveInt


class SAMParameters(ToolInput):
    # #04 DiffuseRequest's seed is a canvas reference, never free geometry.
    gesture_ref: Reference
    threshold: Annotated[float, Field(ge=-1, le=1)]
    queue_min_similarity: Annotated[float, Field(ge=-1, le=1)]


class SLICCandidates(CubeArguments):
    class_code: Reference
    method: Literal["SLIC"]
    params: SLICParameters


class SAMCandidates(CubeArguments):
    class_code: Reference
    method: Literal["SAM"]
    params: SAMParameters


class ConfirmArguments(CubeArguments):
    revision: PositiveInt
    overwrite: bool | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None  # Existing #04 SaveRequest limit.


class ExportArguments(CubeArguments):
    version_id: Reference


class RunArguments(CubeArguments):
    annotation_version_id: Reference
    recipe_version_id: Reference


class CompareArguments(CubeArguments):
    annotation_version_id: Reference
    recipe_version_ids: Annotated[list[Reference], Field(min_length=1)]


_FORBIDDEN_FIELDS = {"point", "points", "coords", "coordinates", "polygon", "spectra", "spectrum", "values", "bands"}


def validate_schema(schema):
    """Reject geometric fields and free objects at every nested schema level."""
    if not isinstance(schema, dict):
        raise ValueError("schema must be an object")
    def visit(node):
        if isinstance(node, dict):
            if not any(key in node for key in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")):
                raise ValueError("untyped tool fields are forbidden")
            if _FORBIDDEN_FIELDS.intersection(node.get("properties", {})):
                raise ValueError("geometry/spectrum fields are forbidden")
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                raise ValueError("tool objects must forbid extra properties")
            for value in node.get("properties", {}).values():
                visit(value)
            for value in node.get("$defs", {}).values():
                visit(value)
            if "items" in node:
                visit(node["items"])
            for key in ("anyOf", "oneOf", "allOf"):
                for value in node.get(key, []):
                    visit(value)
        else:
            raise ValueError("typed schema node required")
    visit(schema)


def validate_snapshot(snapshot):
    if not isinstance(snapshot, list):
        raise ValueError("tools must be a list")
    names = set()
    for tool in snapshot:
        function = tool["function"]
        if tool["type"] != "function" or function["name"] in names:
            raise ValueError("invalid or duplicate tool")
        names.add(function["name"])
        validate_schema(function["parameters"])


def _parameters(adapter):
    """Inline Pydantic local refs for a self-contained wire schema.

    '#/$defs/...' otherwise looks like a path to the unchanged G1 deny scan.
    Keep that backstop intact and mechanically inline the generated schema.
    """
    schema = adapter.json_schema()
    definitions = schema.pop("$defs", {})
    def expand(node, ancestors=()):
        if isinstance(node, dict):
            if "$ref" in node:
                reference = node["$ref"]
                prefix = "#/$defs/"
                if not reference.startswith(prefix) or reference in ancestors:
                    raise ValueError("tool schema refs must be local and acyclic")
                target = definitions[reference[len(prefix):]]
                node = {**expand(target, (*ancestors, reference)), **{k: v for k, v in node.items() if k != "$ref"}}
            return {key: expand(value, ancestors) for key, value in node.items()}
        if isinstance(node, list):
            return [expand(value, ancestors) for value in node]
        return node
    return expand(schema)


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    adapter: TypeAdapter
    handler: Callable | None
    human_check: bool = False
    gpu: bool = False
    estimate_ms: int | None = None

    @property
    def ready(self):
        return self.handler is not None


class ToolRegistry:
    def __init__(self):
        self._tools = {}
        # Compatibility handlers can remain executable for frozen old sessions
        # while absent from every new model-facing catalogue.
        self.hidden_names = set()

    def register(self, name, arguments, description, handler=None, *, human_check=False, gpu=False, estimate_ms=None):
        if name in self._tools:
            raise ValueError("duplicate tool")
        adapter = TypeAdapter(arguments)
        validate_schema(adapter.json_schema())
        self._tools[name] = RegisteredTool(name, description, adapter, handler, human_check, gpu, estimate_ms)

    def resolve(self, name):
        try:
            return self._tools[name]
        except KeyError:
            raise DataError("TOOL_NOT_FOUND", "工具未注册") from None

    def snapshot(self):
        return [{"type": "function", "function": {"name": tool.name, "description": tool.description,
                 "parameters": _parameters(tool.adapter)}} for tool in self._tools.values()
                if tool.name not in self.hidden_names]

    def validate(self, name, arguments):
        tool = self.resolve(name)
        try:
            if isinstance(arguments, str):
                return tool.adapter.validate_json(arguments, strict=True)
            return tool.adapter.validate_python(arguments, strict=True)
        except ValidationError:
            # No raw arguments, coordinate arrays or provider text in errors.
            raise DataError("TOOL_ARGS_INVALID", "工具参数不合法") from None

    def invoke(self, name, arguments):
        tool = self.resolve(name)
        validated = self.validate(name, arguments)
        if not tool.ready:
            raise DataError("TOOL_NOT_IMPLEMENTED", "工具底层尚未就绪")
        try:
            summary = tool.handler(validated)
        except DataError as error:
            raise DataError(error.code, error.code) from None
        # Return summaries only. Future draft bindings must implement their
        # specified scalar whitelist here, never return full REST documents.
        if not isinstance(summary, dict) or any(
            not isinstance(key, str) or key in _FORBIDDEN_FIELDS | {"document", "sample_pixels", "bbox", "path", "filename"}
            or value is not None and type(value) not in (str, int, float, bool)
            or isinstance(value, float) and not math.isfinite(value)
            for key, value in summary.items()
        ):
            raise DataError("TOOL_RESULT_INVALID", "工具摘要必须符合标量白名单")
        return summary


def _run_summary(row):
    result = {"run_id": row["id"]}
    for key in ("cube_id", "annotation_version_id", "recipe_version_id", "status", "input_fingerprint"):
        if key in row:
            result[key] = row[key]
    metrics = row.get("metrics") or {}
    for key in ("fisher", "interclass_distance", "intraclass_variance", "snr_nan_count", "nan_spectra_skipped"):
        if key in metrics:
            result[key] = metrics[key]
    for key in ("mean", "median", "p10", "p90", "n_pixels"):
        if key in metrics.get("snr", {}):
            result["snr_" + key] = metrics["snr"][key]
    if row.get("error"):
        result["error_code"] = row["error"]["error"]
    return result


def build_registry(*, datasets=None, runner=None, comparison=None, database=None, sessions=None, diffusion=None, catalogue_version=1):
    """Bind available services without constructing engines or making requests."""
    registry = ToolRegistry()
    if catalogue_version not in (1, 2):
        raise ValueError("unsupported tool catalogue version")
    registry.catalogue_version = catalogue_version

    def list_datasets(arguments):
        with connect_database(datasets.database) as db:
            ids = [row[0] for row in db.execute("SELECT id FROM dataset_registry ORDER BY id")]
        return {"count": len(ids), "dataset_ids": ", ".join(ids)}

    def describe(arguments):
        dataset, _ = datasets.get(arguments.dataset_id)
        return {"dataset_id": arguments.dataset_id, "n_lines": dataset.shape[0],
                "n_samples": dataset.shape[1], "n_bands": dataset.shape[2],
                "dtype": dataset.dtype, "interleave": dataset.interleave}

    def run(arguments):
        row = runner.run(arguments.cube_id, arguments.annotation_version_id, arguments.recipe_version_id)
        result = _run_summary(row)
        if catalogue_version == 2:
            from .workflows import run_provenance
            result.update(run_provenance(runner, row))
        return result

    def compare(arguments):
        result = comparison.compare(arguments.cube_id, arguments.annotation_version_id, arguments.recipe_version_ids)
        summary = {"run_count": len(result["runs"])}
        for index, row in enumerate(result["runs"], 1):
            summary.update({f"run_{index}_{key}": value for key, value in _run_summary(row).items()})
        for row in result["ranking"]:
            for key in ("run_id", "recipe_version_id", "fisher"):
                summary[f"rank_{row['rank']}_{key}"] = row[key]
        if catalogue_version == 2:
            from .workflows import comparison_notes, run_provenance
            summary.update(comparison_notes(result))
            if runner is not None:
                for index, row in enumerate(result["runs"], 1):
                    summary.update({f"run_{index}_{key}": value for key, value in run_provenance(runner, row).items()})
        return summary

    def settings(arguments):
        from ..llm import read_settings
        value = read_settings(database)
        # Provider URL and the credential are not LLM context. Read persisted
        # non-sensitive settings, expose only scalars without paths.
        return {"configured": bool(value.base_url and value.model), "model": value.model,
                "temperature": value.temperature, "max_tokens": value.max_tokens, "timeout_ms": value.timeout_ms}

    registry.register("datasets.list", NoArguments, "数据集列表", list_datasets if datasets is not None else None)
    registry.register("datasets.describe", DescribeArguments, "数据集描述", describe if datasets is not None else None)
    registry.register("annotations.draft_get", CubeArguments,
                      "草稿摘要：cube_id、revision、n_regions、n_classes、updated_at、estimated_mat_bytes，完整 document 只走 REST 响应",
                      (lambda arguments: draft_get(sessions, arguments)) if sessions is not None else None)
    registry.register("annotations.draft_add_region", DraftRegionArguments,
                      "画布手势引用，op=add 必填 class_code，uncertain、erase 禁传 class_code、confidence",
                      (lambda arguments: add_region(sessions, arguments)) if sessions is not None else None)
    registry.register("annotations.draft_select_candidates", SLICCandidates | SAMCandidates, "SLIC、SAM 扩散算法候选",
                      (lambda arguments: select_candidates(sessions, diffusion, arguments)) if sessions is not None else None)
    registry.register("annotations.draft_confirm", ConfirmArguments, "标注版本确认",
                      (lambda arguments: draft_confirm(sessions, arguments)) if sessions is not None else None,
                      human_check=True, estimate_ms=1700)
    registry.register("preprocess.run", RunArguments, "预处理运行", run if runner is not None else None)
    registry.register("preprocess.compare", CompareArguments, "预处理配方对比", compare if comparison is not None else None)
    from .training_mat import export
    registry.register("training_mat.export", ExportArguments, "训练 MAT 导出",
                      (lambda arguments: export(sessions, arguments)) if sessions is not None else None, estimate_ms=650)
    registry.register("settings.llm_get", NoArguments, "LLM 设置（无 key）", settings if database is not None else None)
    if catalogue_version == 2:
        registry.hidden_names.update({"annotations.draft_add_region", "annotations.draft_select_candidates"})
        from .workflows import register_workflows
        register_workflows(registry, datasets=datasets, runner=runner, comparison=comparison,
                           sessions=sessions, diffusion=diffusion)
    return registry
