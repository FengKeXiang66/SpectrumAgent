"""Full-coverage tool layer: import, deletion, recipes, modeling writes, training sets.

Design invariant kept from the rest of the catalogue: a summary is a flat map of
scalars. Local paths, provider URLs and secrets never appear in a model-facing
result. Where an operation needs one of those, the server keeps it behind an
opaque reference (``SRC-1`` / ``C-1`` / ``DEL-1``) that the model may name but
cannot read back.

Confirmation is still explicit but no longer UI-only: destructive calls take a
reference produced by their own preview tool, so the impact list is always read
before anything is removed.
"""
from pathlib import Path
import os
import sqlite3
from time import monotonic
from uuid import uuid4
from typing import Annotated, Literal

from pydantic import Field

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.preprocess.export import export_run
from spectrumagent.preprocess.references import registered_run
from ..tool_context import owner_session
from ..open_access import OPEN_ACCESS
from . import NoArguments, Reference, ToolInput


MAX_ITEMS = 10
SCAN_LIMIT = 50
HEADER_SUFFIXES = (".hdr", ".json", ".txt")


def label(value, fallback="未命名"):
    """Display name with every path marker, separator and data suffix removed."""
    if not isinstance(value, str) or not value.strip():
        return fallback
    name = value.strip().replace("\\", "/").rstrip("/").split("/")[-1]
    name = name.strip()
    stem, suffix = os.path.splitext(name)
    if suffix.lower() in HEADER_SUFFIXES:
        name = stem
    name = name.replace(":", "").replace("\n", " ").strip()
    return name[:60] or fallback


def finite(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value if isinstance(value, (str, int, float)) else None


class ReferenceBook:
    """Server-side holder for values the model must never see."""

    def __init__(self):
        self.sources = {}
        self.entries = {}
        self.deletions = {}
        self.counter = {"SRC": 0, "C": 0, "DEL": 0}

    def issue(self, kind, value):
        self.counter[kind] += 1
        reference = f"{kind}-{self.counter[kind]}"
        {"SRC": self.sources, "C": self.entries, "DEL": self.deletions}[kind][reference] = value
        return reference

    def source(self, reference):
        value = self.sources.get(reference, self.entries.get(reference))
        if value is None:
            raise DataError("REFERENCE_EXPIRED", "导入源引用已失效，请重新列出导入源")
        return value

    def deletion(self, reference):
        value = self.deletions.pop(reference, None)
        if value is None:
            raise DataError("REFERENCE_EXPIRED", "删除预览引用已失效，请重新预览影响清单")
        return value


# ---------------------------------------------------------------- import


class ScanArguments(ToolInput):
    source_ref: Reference
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=SCAN_LIMIT)] = SCAN_LIMIT


class ImportArguments(ToolInput):
    source_ref: Reference
    raw: bool = False
    confirm_new: bool = False


# ---------------------------------------------------------------- deletion


class DeletePreviewArguments(ToolInput):
    cube_ids: Annotated[list[Reference], Field(min_length=1, max_length=32)]


class DeleteArguments(ToolInput):
    deletion_ref: Reference
    confirm: bool = False


# ---------------------------------------------------------------- recipes


class SnvStep(ToolInput):
    op: Literal["snv"]
    zero_std: Literal["zeros", "nan", "error"] = "zeros"


class SmoothStep(ToolInput):
    op: Literal["sg_smooth"]
    window: Annotated[int, Field(gt=0)]
    polyorder: Annotated[int, Field(ge=0)]
    mode: Literal["interp", "mirror", "constant", "nearest", "wrap"] = "interp"


class DerivativeStep(ToolInput):
    op: Literal["sg_derivative"]
    order: Annotated[int, Field(ge=1, le=2)]
    window: Annotated[int, Field(gt=0)]
    polyorder: Annotated[int, Field(ge=0)]
    mode: Literal["interp", "mirror", "constant", "nearest", "wrap"] = "interp"


class StandardizeStep(ToolInput):
    op: Literal["standardize"]
    method: Literal["standard", "minmax", "area", "vector"]
    zero_std: Literal["zeros", "nan", "error"] = "zeros"


Step = Annotated[SnvStep | SmoothStep | DerivativeStep | StandardizeStep, Field(discriminator="op")]


class RecipeCreateArguments(ToolInput):
    code: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")]
    name: Annotated[str, Field(min_length=1, max_length=80)]
    steps: Annotated[list[Step], Field(max_length=8)]
    description: Annotated[str, Field(max_length=2000)] | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None


class RunExportArguments(ToolInput):
    run_id: Reference


# ---------------------------------------------------------------- modeling writes


class RegisterArguments(ToolInput):
    run_id: Reference
    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class StageArguments(ToolInput):
    model_id: Reference
    stage: Literal["experiment", "candidate", "production"]


class InferArguments(ToolInput):
    model_id: Reference
    cube_id: Reference
    preprocess_run_id: Reference
    annotation_version_id: Reference


# ---------------------------------------------------------------- settings and paths


class LlmSetArguments(ToolInput):
    model: Annotated[str, Field(max_length=120)] | None = None
    temperature: Annotated[str, Field(max_length=16)] | None = None
    max_tokens: Annotated[str, Field(max_length=16)] | None = None
    timeout_ms: Annotated[str, Field(max_length=16)] | None = None
    egress_enabled: bool | None = None
    base_url: Annotated[str, Field(max_length=500)] | None = None
    api_key: Annotated[str, Field(max_length=2000)] | None = None


class ProjectArguments(ToolInput):
    project_id: Reference | None = None


def _pipeline(steps):
    return {"steps": [{"op": step.op, "version": 1, "params": step.model_dump(exclude={"op"})}
                      for step in steps]}


def _recipe_version(row):
    return {"recipe_version_id": row["id"], "recipe_version_no": row.get("version_no", 1)}


def register_operations(registry, *, datasets=None, recycle=None, runner=None, models=None,
                        inferences=None, training_sets=None, paths=None, database=None):
    book = ReferenceBook()

    # ------------------------------------------------------------ import
    def known_sources():
        if database is None:
            return []
        values = []
        with connect_database(database) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_path_settings'").fetchone()
            if exists:
                values = [row[0] for row in db.execute(
                    "SELECT source_path FROM project_path_settings WHERE source_path<>'' ORDER BY source_path")]
        return [Path(value) for value in values if Path(value).is_dir()]

    def list_sources(arguments):
        roots = known_sources()
        book.sources.clear()
        result = {"status": "ok" if roots else "need_source_setup", "source_count": len(roots)}
        for index, root in enumerate(roots[:MAX_ITEMS], 1):
            result[f"source_{index}_ref"] = book.issue("SRC", root)
            # The configured root is a local path: only its ordinal is model-visible.
            result[f"source_{index}_name"] = f"数据源{index}"
            result[f"source_{index}_children"] = sum(1 for _ in root.iterdir()) if os.access(root, os.R_OK) else 0
        if not roots:
            result["hint"] = "尚无已登记的数据源目录，请先在设置界面登记一次；路径不允许进入模型上下文"
        return result

    def scan(arguments):
        root = book.source(arguments.source_ref)
        if not root.is_dir():
            raise DataError("INVALID_IMPORT", "该引用不是目录")
        children = []
        try:
            for entry in sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                if entry.is_dir():
                    children.append((entry, "dir"))
                elif entry.suffix.lower() in HEADER_SUFFIXES:
                    children.append((entry, "header"))
        except OSError as error:
            raise DataError("DIRECTORY_UNREADABLE", "无法读取该目录") from error
        page = children[arguments.offset:arguments.offset + arguments.limit]
        result = {"status": "ok", "total_count": len(children), "count": len(page), "offset": arguments.offset,
                  "truncated": arguments.offset + len(page) < len(children)}
        for index, (entry, kind) in enumerate(page, 1):
            result[f"entry_{index}_ref"] = book.issue("C", entry)
            result[f"entry_{index}_name"] = label(entry.name)
            result[f"entry_{index}_kind"] = kind
            if kind == "header":
                result[f"entry_{index}_has_header"] = 1
            elif entry.is_dir():
                result[f"entry_{index}_has_header"] = 1 if any(
                    child.suffix.lower() in HEADER_SUFFIXES for child in entry.iterdir() if child.is_file()) else 0
            else:
                result[f"entry_{index}_has_header"] = 0
        return result

    def import_source(arguments):
        root = book.source(arguments.source_ref)
        try:
            response = datasets.import_path(str(root), raw=arguments.raw, confirm_new=arguments.confirm_new)
        except DataError as error:
            if getattr(error, "status_code", None) == 409 or error.code == "REIMPORT_ACTIVE_EXISTS":
                return {"status": "need_confirm", "conflict": error.code,
                        "hint": "该路径已有活跃记录；确认以新记录重新登记后再调用一次，confirm_new=true"}
            raise
        rows = response.datasets
        result = {"status": "imported", "dataset_count": len(rows),
                  "imported_count": sum(1 for row in rows if not row.existing),
                  "existing_count": sum(1 for row in rows if row.existing),
                  "truncated": len(rows) > MAX_ITEMS}
        for index, row in enumerate(rows[:MAX_ITEMS], 1):
            result[f"dataset_{index}_id"] = str(row.id)
            result[f"dataset_{index}_name"] = label(row.display_name)
            result[f"dataset_{index}_existing"] = 1 if row.existing else 0
            result[f"dataset_{index}_lines"] = int(row.dataset.shape[0])
            result[f"dataset_{index}_samples"] = int(row.dataset.shape[1])
            result[f"dataset_{index}_bands"] = int(row.dataset.shape[2])
        return result

    # ------------------------------------------------------------ deletion
    def delete_preview(arguments):
        preview = recycle.preview_batch([str(cube) for cube in arguments.cube_ids])
        per_cube = preview.get("per_cube") or []
        result = {"status": "ok", "cube_count": len(preview.get("cube_ids") or []),
                  "file_count": len(preview.get("directories") or []),
                  "deletion_ref": book.issue("DEL", {"token": preview["preview_token"],
                                                     "cube_ids": list(preview.get("cube_ids") or [])})}
        for index, item in enumerate(per_cube[:MAX_ITEMS], 1):
            result[f"item_{index}_cube_id"] = item["cube_id"]
            result[f"item_{index}_annotation_versions"] = item["annotation_versions"]
            result[f"item_{index}_preprocess_runs"] = item["preprocess_runs"]
            result[f"item_{index}_inference_runs"] = item["inference_runs"]
            result[f"item_{index}_kilobytes"] = int(item["total_bytes"] // 1024)
        return result

    def delete(arguments):
        if arguments.confirm is not True:
            return {"status": "need_confirm", "hint": "永久删除须显式确认；先调用 datasets.delete_preview 查看影响清单"}
        record = book.deletion(arguments.deletion_ref)
        recycle.delete_batch(record["cube_ids"], confirm=True, preview_token=record["token"])
        return {"status": "deleted", "cube_count": len(record["cube_ids"])}

    # ------------------------------------------------------------ recipes
    def recipe_create(arguments):
        row = runner.recipes.create(arguments.code, arguments.name, arguments.description,
                                    _pipeline(arguments.steps), note=arguments.note)
        versions = row.get("versions") or []
        result = {"recipe_id": row["id"], "recipe_code": row["code"], "recipe_name": label(row["name"]),
                  "step_count": len(arguments.steps), "version_count": len(versions)}
        if versions:
            result.update(_recipe_version(versions[-1]))
        return result

    def run_export(arguments):
        row = export_run(runner, arguments.run_id)
        artifacts = row.get("artifacts") or []
        return {"status": row.get("status", "succeeded"), "run_id": row.get("run_id", arguments.run_id),
                'view_kind':'exports',
                "artifact_count": len(artifacts),
                "artifact_kinds": ", ".join(sorted({item.get("kind", "") for item in artifacts}))}

    # ------------------------------------------------------------ modeling writes
    def register_model(arguments):
        row = models.register(arguments.run_id, arguments.name)
        return {"model_id": row["id"], "run_id": row.get("run_id", arguments.run_id),
                "stage": row.get("stage", "experiment"), "version": row.get("version", 1),
                **({'training_protocol': row['training_protocol']} if row.get('training_protocol') else {}),
                "name_available": 1 if row.get("name") else 0}

    def set_stage(arguments):
        row = models.set_stage(arguments.model_id, arguments.stage)
        return {"model_id": row["id"], "stage": row["stage"]}

    def infer(arguments):
        row = inferences.create(arguments.model_id, arguments.cube_id,
                                arguments.preprocess_run_id, arguments.annotation_version_id)
        stats = row.get("stats") or {}
        return {"inference_run_id": row["id"], "status": row.get("status", "succeeded"),
                "model_id": row.get("model_id", arguments.model_id),
                "n_pixels": int(stats.get("n_pixels", 0)),
                "n_foreground": int(stats.get("n_foreground", 0)),
                "sample_prediction": finite(stats.get("sample_prediction")),
                'calibration_origin': stats.get('calibration_origin', ''),
                "out_of_domain_count": int(stats.get("out_of_domain_count", 0)),
                "quality_label": stats.get("quality_label", "")}

    # ------------------------------------------------------------ settings and paths
    def llm_set(arguments):
        from ..llm import LLMSettings, read_settings, write_settings, set_api_key
        current = read_settings(database)
        update = {key: value for key, value in arguments.model_dump().items() if value is not None}
        api_key = update.pop('api_key', None)
        settings = LLMSettings(**{**current.model_dump(), **update})
        write_settings(database, settings, **({'permanent_root':paths.credential_root} if paths is not None else {}))
        if api_key is not None:
            if paths is not None:
                from ..credential_store import save as save_credential
                root = getattr(paths, 'credential_root', None)
                if root is not None:
                    save_credential(root, api_key)
            set_api_key(api_key)
        return {"configured": bool(settings.base_url and settings.model), "model": settings.model,
                "temperature": settings.temperature, "max_tokens": settings.max_tokens,
                "timeout_ms": settings.timeout_ms,
                "egress_enabled": 1 if settings.egress_enabled else 0}

    def project_paths(arguments):
        if database is None:
            raise DataError("TOOL_NOT_IMPLEMENTED", "缺少数据库绑定")
        with connect_database(database) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_path_settings'").fetchone()
            if exists:
                row = db.execute("SELECT project_id,source_path,output_root FROM project_path_settings "
                                 + ("WHERE project_id=?" if arguments.project_id else "ORDER BY updated_at DESC LIMIT 1"),
                                 (str(arguments.project_id),) if arguments.project_id else ()).fetchone()
            else:
                row = None
            projects = db.execute("SELECT id FROM project ORDER BY rowid LIMIT 1").fetchone()
        result = {"project_id": row[0] if row else (projects[0] if projects else ""),
                  "source_configured": 1 if row and row[1] else 0,
                  "output_configured": 1 if row and row[2] else 0,
                  "source_set": 1 if row and row[1] else 0,
                  "output_set": 1 if row and row[2] else 0}
        return result

    tools = [
        ("sources.list", NoArguments, "列出服务端已登记的数据源目录（路径不进模型，只给引用）；无登记时返回 need_source_setup", list_sources, paths is not None or database is not None),
        ("sources.scan", ScanArguments, "按 source_ref 列出下一层的子目录与数据头，返回 entry 引用；不返回真实路径", scan, datasets is not None),
        ("datasets.import", ImportArguments, "按 source_ref 导入整批数据；冲突返回 need_confirm，确认后以 confirm_new=true 重试；不返回路径与谱值", import_source, datasets is not None),
        ("datasets.delete_preview", DeletePreviewArguments, "永久删除前的影响清单预览；返回 deletion_ref，不删除任何内容", delete_preview, recycle is not None),
        ("datasets.delete", DeleteArguments, "按 deletion_ref 永久删除数据集及其产物；须 confirm=true，不确认只返回 need_confirm", delete, recycle is not None),
        ("preprocess.recipe_create", RecipeCreateArguments, "组合算子新建配方（snv、sg_smooth、sg_derivative、standardize）；返回 recipe 与首个版本引用", recipe_create, runner is not None),
        ("preprocess.run_export", RunExportArguments, "把已成功的预处理 run 导出为可下载产物；只返回产物数量与类型", run_export, runner is not None and paths is not None),
        ("modeling.register", RegisterArguments, "把成功的分类或回归训练 run 注册为模型；返回 model_id", register_model, models is not None),
        ("modeling.set_stage", StageArguments, "设置模型阶段：experiment、candidate、production；同目标只有一个生产模型", set_stage, models is not None),
        ("modeling.infer", InferArguments, "对指定样品发起批量推理；须显式给出模型、cube、预处理 run 与标注版本", infer, inferences is not None),
        ("settings.llm_set", LlmSetArguments, "配置模型服务（base_url、API Key、model、temperature、max_tokens、timeout_ms、egress 开关）；开发期允许对话直接提供连接地址与密钥", llm_set, database is not None),
        ("projects.paths_get", ProjectArguments, "读取项目数据源与输出根的登记状态；只返回是否已配置，不返回路径", project_paths, database is not None),
    ]
    for name, arguments, description, handler, ready in tools:
        registry.register(name, arguments, description, handler if ready else None)
    from .recipe_drafts import register_draft_operations
    register_draft_operations(registry,runner)
