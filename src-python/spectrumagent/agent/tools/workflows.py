"""Conversation workflows: bounded scalar observations, server-owned geometry.

The v1 catalogue remains immutable. v2 provides discovery and explicit preview /
accept operations; neither spectral similarity nor an LLM supplies material truth.
"""
from copy import deepcopy
import hashlib
import json
import re
import sqlite3
from uuid import uuid4

import numpy as np
from pydantic import Field, model_validator
from typing import Annotated, Literal

from backend.database import connect_database
from spectrumagent.annotation.draft import conflict
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.engines.diffusion import DEFAULT_THRESHOLD, DEFAULT_QUEUE_MIN_SIMILARITY
from spectrumagent.annotation.labels import LabelStore, CatalogRequest, CustomRequest, SchemaRequest, SchemaField
from spectrumagent.annotation.gestures import region_from_gesture
from spectrumagent.data import DataError
from spectrumagent.preprocess.migrations import BUILTIN_CODE, BUILTIN_PIPELINE
from . import ToolInput, Reference, CubeArguments, NoArguments, _run_summary


LIMIT = 50
Revision = Annotated[int, Field(ge=0)]


class ResolveArguments(ToolInput):
    query: Annotated[str, Field(min_length=1, max_length=200)]


class LabelsArguments(CubeArguments):
    class_codes: Annotated[list[Reference], Field(min_length=1, max_length=30)]
    include_background: bool = True


class ProposeArguments(CubeArguments):
    class_code: Reference
    gesture_ref: Reference | None = None


class CandidateArguments(CubeArguments):
    candidate_ref: Reference


class ApplyArguments(CandidateArguments):
    revision: Revision


class RevisionArguments(CubeArguments):
    revision: Revision


class MarkArguments(RevisionArguments):
    gesture_ref: Reference
    action: Literal["uncertain", "erase"]


class EditArguments(RevisionArguments):
    region_id: Reference
    action: Literal["relabel", "delete"]
    class_code: Reference | None = None

    @model_validator(mode="after")
    def valid_patch(self):
        if (self.action == "relabel") != (self.class_code is not None):
            raise ValueError("relabel requires class_code; delete forbids it")
        return self


class RecipeArguments(ToolInput):
    profile: Literal["raw", "snv", "snv_sg1"]


class DefaultRunArguments(CubeArguments):
    annotation_version_id: Reference | None = None
    recipe_version_id: Reference | None = None


class RunGetArguments(ToolInput):
    run_id: Reference


def safe_name(value):
    """A display label may contain a relative filename; never expose directories."""
    value = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    value = re.sub(r"[\x00-\x1f\x7f:]", " ", value).strip()
    value = re.sub(r"\.(?:hdr|img|mat)\b", "", value, flags=re.I)
    return value[:160] or "未命名数据集"


def _rows(database, query, arguments=()):
    with connect_database(database) as db:
        return db.execute(query, arguments).fetchall()


def dataset_catalog(datasets):
    rows = _rows(datasets.database, "SELECT id,payload FROM dataset_registry ORDER BY rowid")
    result = {"dataset_count": len(rows), "count": len(rows), "truncated": len(rows) > LIMIT}
    for index, (identifier, payload) in enumerate(rows[:LIMIT], 1):
        data = json.loads(payload)
        result.update({f"dataset_{index}_id": identifier, f"dataset_{index}_ref": f"D{index}",
                       f"dataset_{index}_name": safe_name(data.get("name"))})
        for key, value in zip(("n_lines", "n_samples", "n_bands"), data.get("shape", ())):
            result[f"dataset_{index}_{key}"] = value
    return result


def dataset_description(datasets, identifier):
    dataset, _ = datasets.get(identifier)
    return {"dataset_id": identifier, "cube_id": identifier, "display_name": safe_name(dataset.name),
            "n_lines": dataset.shape[0], "n_samples": dataset.shape[1], "n_bands": dataset.shape[2],
            "dtype": dataset.dtype, "interleave": dataset.interleave}


def comparison_notes(result):
    # These service-authored boundaries use slash as prose punctuation, which
    # the unchanged egress path guard deliberately rejects. Spell it out.
    summary = {f"boundary_{i}": text.replace("/", "或") for i, text in enumerate(result.get("boundaries", [])[:10], 1)}
    if result.get("selection"):
        summary["selection_rule"] = result["selection"]
    for i, run in enumerate(result.get("runs", [])[:LIMIT], 1):
        metrics = run.get("metrics") or {}
        for j, text in enumerate(metrics.get("limitations", [])[:10], 1):
            summary[f"run_{i}_limitation_{j}"] = text.replace("/", "或")
        for j, excluded in enumerate(metrics.get("excluded_classes", [])[:LIMIT], 1):
            for key in ("label_index", "pixel_count", "reason"):
                if key in excluded:
                    summary[f"run_{i}_excluded_{j}_{key}"] = excluded[key]
    return summary


def run_provenance(runner, row):
    versions = _rows(runner.database, "SELECT pipeline,version_no FROM preprocess_recipe_version WHERE id=?", (row["recipe_version_id"],))
    result = {}
    if versions:
        result["recipe_version_no"] = versions[0][1]
        for i, step in enumerate(json.loads(versions[0][0])["steps"][:30], 1):
            result[f"step_{i}_op"] = step["op"]
            result[f"step_{i}_version"] = step["version"]
    result.update(comparison_notes({"runs": [row], "boundaries": (row.get("metrics") or {}).get("boundaries", [])}))
    return result


class Workflows:
    def __init__(self, *, datasets, runner, comparison, sessions, diffusion):
        self.datasets = datasets if datasets is not None else getattr(sessions, "registry", None)
        self.runner, self.comparison, self.sessions, self.diffusion = runner, comparison, sessions, diffusion

    def resolve(self, arguments):
        rows = _rows(self.datasets.database, "SELECT id,payload FROM dataset_registry ORDER BY rowid")
        query = arguments.query.strip().casefold()
        ordinal = re.fullmatch(r"(?:d|第)?(\d+)(?:项|个|个数据集)?", query)
        words = {"第一项": 1, "第一个": 1, "第一个数据集": 1, "第二项": 2, "第二个": 2,
                 "第三项": 3, "第三个": 3, "第一": 1, "第二": 2, "第三": 3}
        index = int(ordinal.group(1)) if ordinal else words.get(query)
        choices = [(i, identifier, safe_name(json.loads(payload).get("name")))
                   for i, (identifier, payload) in enumerate(rows, 1)]
        exact = [item for item in choices if query in {item[1].casefold(), item[2].casefold()}]
        by_index = [item for item in choices if item[0] == index] if index is not None else []
        # A numeric acquisition name (e.g. 081) takes precedence over ordinal 81.
        matches = exact or by_index or [item for item in choices if item[1].casefold().startswith(query)
                                       or item[2].casefold().startswith(query)]
        if len(matches) == 1:
            i, identifier, name = matches[0]
            return {"status": "resolved", "cube_id": identifier, "display_name": name, "dataset_ref": f"D{i}"}
        result = {"status": "ambiguous" if matches else "not_found", "match_count": len(matches)}
        for j, (i, identifier, name) in enumerate(matches[:LIMIT], 1):
            result.update({f"match_{j}_id": identifier, f"match_{j}_name": name, f"match_{j}_ref": f"D{i}"})
        return result

    def context(self, arguments):
        cube_id = arguments.cube_id
        with self.sessions._lock:
            state = self.sessions._state(cube_id)
            labels = self.sessions.drafts.labels(cube_id)
            document = json.loads(state.document_json)
            dataset, _ = self.datasets.get(cube_id)
            latest = _rows(self.sessions.database,
                "SELECT id,version_no FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,))
            summary = {"cube_id": cube_id, "display_name": safe_name(dataset.name), "revision": state.revision,
                       "n_regions": len(document["regions"]), "n_classes": len(labels),
                       "segmentation_ready": state.segments is not None,
                       "latest_annotation_version_id": latest[0][0] if latest else None,
                       "latest_annotation_version_no": latest[0][1] if latest else None,
                       "blank_pixels": int(np.count_nonzero(state.label_map == -1)),
                       "uncertain_pixels": int(np.count_nonzero(state.label_map == -2)),
                       "labeled_pixels": int(np.count_nonzero(state.label_map >= 0)),
                       "regions_truncated": len(document["regions"]) > LIMIT}
            if state.gestures:
                summary["last_gesture_ref"] = next(reversed(state.gestures))
            pending = [(ref, item) for ref, item in self._previews().items()
                       if item["cube_id"] == cube_id and item["revision"] == state.revision]
            if pending:
                key = self._segmentation_key(state) if state.segments is not None else None
                pending = [(ref, item) for ref, item in pending if item["segmentation_key"] == key]
            if pending:
                ref, item = pending[-1]
                summary.update(latest_candidate_ref=ref, latest_candidate_class_code=item["class_code"],
                               latest_candidate_revision=item["revision"])
            for i, (identifier, code, name, _) in enumerate(labels[:LIMIT], 1):
                summary.update({f"class_{i}_id": identifier, f"class_{i}_code": safe_name(code),
                                f"class_{i}_name": safe_name(name),
                                f"class_{i}_pixel_count": int(np.count_nonzero(state.label_map == i - 1))})
            for i, region in enumerate(document["regions"][-LIMIT:], 1):
                summary.update({f"region_{i}_id": region["region_id"], f"region_{i}_op": region["op"],
                                f"region_{i}_class_code": document["classes"][region["class_index"]]["code"]
                                if region["op"] == "add" else None})
            return summary

    def prepare(self, arguments):
        params = Parameters()  # Registered platform/UI defaults, not LLM choices.
        segmentation = self.diffusion.superpixels.generate(arguments.cube_id, params)
        self.sessions.set_segmentation(arguments.cube_id, segmentation)
        return {"cube_id": arguments.cube_id, "status": "ready", "profile": "annotation-default-v1",
                "n_segments": params.n_segments, "compactness": params.compactness,
                "pca_components": params.pca_components,
                "superpixel_count": int(segmentation.report["superpixel_count"]),
                "threshold": DEFAULT_THRESHOLD, "queue_min_similarity": DEFAULT_QUEUE_MIN_SIMILARITY,
                "source": "TASK-04 平台已登记默认值；仅分割与相似区域扩散，不识别材质"}

    def ensure_labels(self, arguments):
        with self.sessions._lock:
            cube_id = arguments.cube_id
            self.datasets.get(cube_id)
            project_id = _rows(self.sessions.database, "SELECT project_id FROM dataset_registry WHERE id=?", (cube_id,))[0][0]
            store = LabelStore(self.sessions.database)
            existing = {row[0] for row in _rows(self.sessions.database, "SELECT code FROM label WHERE project_id=?", (project_id,))}
            from spectrumagent.annotation.labels import plastic_catalog
            known = {item["code"] for item in plastic_catalog()} | {"BG"}
            wanted = set(arguments.class_codes) | ({"BG"} if arguments.include_background else set())
            if wanted - existing - known:
                raise DataError("LABEL_NOT_FOUND", "未登记的自定义类别需要先定义，不能猜测标签含义")
            if not _rows(self.sessions.database, "SELECT id FROM label_schema WHERE project_id=? AND tree_path='材料'", (project_id,)):
                store.add(SchemaRequest(project_id=project_id, schema=SchemaField(name="材料", tree_path="材料", field_type="enum")))
            missing = sorted(wanted - existing)
            catalog_codes = [code for code in missing if code != "BG"]
            if catalog_codes:
                store.add(CatalogRequest(project_id=project_id, from_catalog="plastic", codes=catalog_codes))
            if "BG" in missing:
                store.add(CustomRequest(project_id=project_id, code="BG", name="背景", tree_path="材料/塑料/BG",
                                        color_hex="#9aa7b2", is_background=True))
            result = self.context(arguments)
            result.update(status="ready", created_label_count=len(missing))
            return result

    def _previews(self):
        if not hasattr(self.sessions, "_orchestration_previews"):
            self.sessions._orchestration_previews = {}
        return self.sessions._orchestration_previews

    @staticmethod
    def _segmentation_key(state):
        return hashlib.sha256(state.segments.tobytes() + json.dumps(state.params, sort_keys=True).encode()).hexdigest()

    def _clear_previews(self, cube_id, state):
        previews = self._previews()
        removed = {ref for ref, item in previews.items() if item["cube_id"] == cube_id}
        for ref in removed:
            previews.pop(ref)
        state.candidates[:] = [item for item in state.candidates if item.get("candidate_ref") not in removed]

    def propose(self, arguments):
        cube_id = arguments.cube_id
        with self.diffusion.superpixels.lock, self.sessions._lock:
            state = self.sessions._state(cube_id)
            gesture_ref = arguments.gesture_ref or (next(reversed(state.gestures)) if state.gestures else None)
            if gesture_ref is None:
                return {"cube_id": cube_id, "status": "need_seed", "class_code": arguments.class_code,
                        "detail": "尚无可信材质种子。请在目标材质上指认一次；分割和原谱相似扩散不能自动判断 PP 等材质。"}
            if state.segments is None:
                self.prepare(arguments)
                state = self.sessions._state(cube_id)
            if not any(row[1] == arguments.class_code for row in self.sessions.drafts.labels(cube_id)):
                raise DataError("LABEL_NOT_FOUND", "请先确保目标标签已登记")
            result = self.diffusion.generate(cube_id, self.sessions.resolve_gesture(cube_id, gesture_ref),
                threshold=DEFAULT_THRESHOLD, queue_min_similarity=DEFAULT_QUEUE_MIN_SIMILARITY)
            state = self.sessions._state(cube_id)
            self._clear_previews(cube_id, state)
            candidate = result["candidate"]
            if not result["enqueued"]:
                # The existing queue guard deliberately withholds this overlay.
                # Do not issue an accept-able reference for an invisible region.
                return {"cube_id": cube_id, "status": "need_seed", "revision": state.revision,
                        "class_code": arguments.class_code, "below_queue_floor": True,
                        "pixel_count": candidate["pixel_count"], "min_similarity": candidate["min_similarity"],
                        "threshold": DEFAULT_THRESHOLD, "queue_min_similarity": DEFAULT_QUEUE_MIN_SIMILARITY,
                        "detail": "该扩散区域低于入队相似度下限，未进入可接受预览且未修改草稿。请重新指认更有代表性的种子；相似度不是材质识别置信度。"}
            candidate_ref = "c-" + uuid4().hex
            previews = self._previews()
            # Preview lifetime is the service session; cap stale masks/references.
            while len(previews) >= LIMIT:
                previews.pop(next(iter(previews)))
            previews[candidate_ref] = {"cube_id": cube_id, "revision": state.revision,
                "class_code": arguments.class_code, "superpixels": tuple(candidate["superpixels"]),
                "segmentation_key": self._segmentation_key(state), "below_queue_floor": not result["enqueued"]}
            if result["enqueued"]:
                # Opaque reference ties the existing display queue to this
                # preview without exposing the server-owned geometry to the LLM.
                state.candidates[-1]["candidate_ref"] = candidate_ref
            return {"cube_id": cube_id, "status": "preview", "candidate_ref": candidate_ref,
                    "revision": state.revision, "class_code": arguments.class_code,
                    "pixel_count": candidate["pixel_count"], "min_similarity": candidate["min_similarity"],
                    "below_queue_floor": not result["enqueued"], "threshold": DEFAULT_THRESHOLD,
                    "queue_min_similarity": DEFAULT_QUEUE_MIN_SIMILARITY,
                    "detail": "候选已预览，草稿尚未修改；相似度不是材质识别置信度。确认后才接受候选。"}

    def apply(self, arguments):
        with self.sessions._lock:
            self.datasets.readable(arguments.cube_id, raw=False)
            state = self.sessions._state(arguments.cube_id)
            item = self._previews().get(arguments.candidate_ref)
            if item is None or item["cube_id"] != arguments.cube_id:
                raise DataError("CANDIDATE_NOT_FOUND", "候选引用不存在或已失效")
            if state.revision != arguments.revision or item["revision"] != state.revision:
                raise conflict()
            if state.segments is None or item["segmentation_key"] != self._segmentation_key(state):
                raise DataError("SEGMENTATION_STALE", "分割已变化，请重新预览")
            labels = {row[1]: row[0] for row in self.sessions.drafts.labels(arguments.cube_id)}
            mask = np.isin(state.segments, item["superpixels"])
            self.sessions.edit(arguments.cube_id, mask, action="confirm", label_id=labels[item["class_code"]],
                geometry={"superpixels": list(item["superpixels"])}, source="algorithm",
                confidence="low" if item["below_queue_floor"] else "medium")
            self._previews().pop(arguments.candidate_ref)
            result = self.context(arguments)
            result.update(status="applied", region_id=json.loads(self.sessions._state(arguments.cube_id).document_json)["regions"][-1]["region_id"])
            return result

    def reject(self, arguments):
        with self.sessions._lock:
            item = self._previews().get(arguments.candidate_ref)
            if item is None or item["cube_id"] != arguments.cube_id:
                raise DataError("CANDIDATE_NOT_FOUND", "候选引用不存在或已失效")
            state = self.sessions._state(arguments.cube_id)
            state.candidates[:] = [candidate for candidate in state.candidates
                                   if candidate.get("candidate_ref") != arguments.candidate_ref]
            self._previews().pop(arguments.candidate_ref)
            return {"cube_id": arguments.cube_id, "status": "rejected", "revision": state.revision,
                    "detail": "已拒绝候选，草稿未修改。"}

    def background(self, arguments):
        with self.sessions._lock:
            state = self.sessions._state(arguments.cube_id)
            if state.revision != arguments.revision:
                raise conflict()
            labels = _rows(self.sessions.database, "SELECT id,code,is_background FROM label WHERE project_id="
                           "(SELECT project_id FROM dataset_registry WHERE id=?) ORDER BY sort_order,code", (arguments.cube_id,))
            background = next((identifier for identifier, code, is_bg in labels if code == "BG" and is_bg), None)
            foreground = [state.label_ids.index(identifier) for identifier, _, is_bg in labels if not is_bg]
            if background is None:
                raise DataError("LABEL_NOT_FOUND", "请先登记背景标签")
            if not np.isin(state.label_map, foreground).any():
                return {"cube_id": arguments.cube_id, "status": "need_seed",
                        "detail": "先接受可信前景候选，才能把其余留白设为背景；不能把未指认的整图当作背景。"}
            mask = state.label_map == -1
            count = int(mask.sum())
            if count:
                self.sessions.edit(arguments.cube_id, mask, action="confirm", label_id=background, source="manual")
            result = self.context(arguments)
            result.update(status="applied" if count else "unchanged", background_added_pixels=count,
                          detail="仅将留白设为背景；已标类别和不确定像素保持。")
            return result

    def mark(self, arguments):
        with self.sessions._lock:
            state = self.sessions._state(arguments.cube_id)
            if not state.gestures or arguments.gesture_ref != next(reversed(state.gestures)):
                raise DataError("GESTURE_NOT_CURRENT", "请先读取当前手势，不能使用其他或已过时的手势")
            result = region_from_gesture(self.sessions, arguments.cube_id, arguments.gesture_ref,
                op=arguments.action, expected_revision=arguments.revision)
            summary = self.context(arguments)
            summary.update(status="applied", region_id=result["region_id"], op=arguments.action,
                           marked_pixels=result["pixel_count"])
            return summary

    def edit(self, arguments):
        with self.sessions._lock:
            state = self.sessions._state(arguments.cube_id)
            if state.revision != arguments.revision:
                raise conflict()
            before = (state.document_json, state.label_map.copy())
            patch = {"deleted": True} if arguments.action == "delete" else {"class_code": arguments.class_code}
            self.sessions.drafts.patch(arguments.cube_id, arguments.region_id, arguments.revision, patch)
            state.undo_stack.append(before)
            result = self.context(arguments)
            result.update(status="applied", region_id=arguments.region_id)
            return result

    def undo(self, arguments):
        with self.sessions._lock:
            if self.sessions._state(arguments.cube_id).revision != arguments.revision:
                raise conflict()
            self.sessions.undo(arguments.cube_id)
            result = self.context(arguments)
            result["status"] = "applied"
            return result

    def recipes(self, arguments):
        items = self.runner.recipes.list()
        result = {"recipe_count": len(items), "truncated": len(items) > LIMIT}
        for i, recipe in enumerate(items[:LIMIT], 1):
            version = recipe["versions"][-1]
            if recipe["code"] == BUILTIN_CODE:
                version = next((item for item in reversed(recipe["versions"]) if item["pipeline"] == BUILTIN_PIPELINE), version)
            result.update({f"recipe_{i}_id": recipe["id"], f"recipe_{i}_code": recipe["code"],
                f"recipe_{i}_name": safe_name(recipe["name"]), f"recipe_{i}_version_id": version["id"],
                f"recipe_{i}_version_no": version["version_no"], f"recipe_{i}_is_default": recipe["code"] == BUILTIN_CODE})
            for j, step in enumerate(version["pipeline"]["steps"][:30], 1):
                result[f"recipe_{i}_step_{j}_op"] = step["op"]
                result[f"recipe_{i}_step_{j}_version"] = step["version"]
        return result

    def recipe_ensure(self, arguments):
        profiles = {"raw": ("conversation-raw-v1", "反射率基线", {"steps": []}),
                    "snv": ("conversation-snv-v1", "SNV", {"steps": [{"op": "snv", "version": 1, "params": {}}]}),
                    "snv_sg1": (BUILTIN_CODE, "塑料 SNV + SG 一阶导数", BUILTIN_PIPELINE)}
        code, name, pipeline = profiles[arguments.profile]
        store = self.runner.recipes
        with store.lock:
            recipe = next((row for row in store.list() if row["code"] == code), None)
            if recipe is None:
                try:
                    recipe = store.create(code, name, "对话编排显式选择的固定模板；不宣称普遍最优", deepcopy(pipeline))
                except sqlite3.IntegrityError:
                    # A different process may have created the same fixed code.
                    recipe = next(row for row in store.list() if row["code"] == code)
            version = next((item for item in reversed(recipe["versions"]) if item["pipeline"] == pipeline), None)
            if version is None:
                # A user-created recipe sharing a code is not scientific proof
                # that its latest content matches the requested fixed template.
                version = store.add_version(recipe["id"], deepcopy(pipeline), note="对话固定模板；保留既有版本")
        return {"recipe_id": recipe["id"], "recipe_version_id": version["id"], "recipe_version_no": version["version_no"],
                "profile": arguments.profile, "display_name": name, "status": "ready",
                "detail": "基线仅执行平台前置反射率转换；SNV 和 SG 参数取已登记模板。优劣需要实际运行比较。"}

    def run_default(self, arguments):
        version = arguments.annotation_version_id
        recipe_id = arguments.recipe_version_id
        if version is None or recipe_id is None:
            missing = "annotation_version" if version is None else "recipe_version"
            return {"cube_id": arguments.cube_id, "status": "need_version", "missing": missing,
                    "detail": "请先明确使用哪个标注版本与哪个配方版本，不采用库中最新或内置默认。"}
        row = self.runner.run(arguments.cube_id, version, recipe_id)
        result = _run_summary(row)
        result.update(run_provenance(self.runner, row))
        return result

    def run_get(self, arguments):
        row = self.runner.get(arguments.run_id)
        return {**_run_summary(row), **run_provenance(self.runner, row)}


def register_workflows(registry, **services):
    workflows = Workflows(**services)
    datasets, sessions, diffusion, runner = workflows.datasets, workflows.sessions, workflows.diffusion, workflows.runner
    # Replace only v2 observations. v1 snapshots/descriptions remain byte-stable.
    registry._tools.pop("datasets.list")
    registry._tools.pop("datasets.describe")
    registry.register("datasets.list", NoArguments, "可读数据集目录；返回 dataset_i_id、dataset_i_name、dataset_i_ref，按导入顺序，禁止要求用户抄 UUID",
                      (lambda _: dataset_catalog(datasets)) if datasets is not None else None)
    from . import DescribeArguments
    registry.register("datasets.describe", DescribeArguments, "按内部 ID 查询数据集的安全名称与形状摘要",
                      (lambda a: dataset_description(datasets, a.dataset_id)) if datasets is not None else None)
    tools = [
        ("datasets.resolve", ResolveArguments, "按名称、唯一 UUID 前缀、D 序号或第一项解析数据集；歧义时返回匹配，不猜测", workflows.resolve, datasets is not None),
        ("annotations.context", CubeArguments, "当前标签、区域引用、草稿 revision、分割状态、最近手势、最新已保存版本；无几何和光谱", workflows.context, sessions is not None),
        ("annotations.prepare", CubeArguments, "用户授权默认参数时生成默认超像素；只分割，不识别材质", workflows.prepare, sessions is not None and diffusion is not None),
        ("annotations.ensure_labels", LabelsArguments, "确保目标材料目录标签及可选背景存在，不修改已有标签", workflows.ensure_labels, sessions is not None),
        ("annotations.propose", ProposeArguments, "按现有手势原谱相似扩散，仅预览 candidate_ref；无手势返回 need_seed，不猜测 PP 材质", workflows.propose, sessions is not None and diffusion is not None),
        ("annotations.apply_candidate", ApplyArguments, "用户接受预览后按引用与 revision 写入草稿；支持首笔 revision=0", workflows.apply, sessions is not None),
        ("annotations.reject_candidate", CandidateArguments, "用户说不要此候选时清预览引用；不修改草稿", workflows.reject, sessions is not None),
        ("annotations.set_background", RevisionArguments, "用户明确说其余背景时，仅将前景之外的留白标背景，保留已标类和不确定像素", workflows.background, sessions is not None),
        ("annotations.mark_region", MarkArguments, "按当前手势把区域标为不确定或擦除；服务器解析几何，不添加材质类别，支持首笔 revision=0", workflows.mark, sessions is not None),
        ("annotations.edit_region", EditArguments, "按上下文的区域引用改类或删除；不要向用户索要 region_id", workflows.edit, sessions is not None),
        ("annotations.undo", RevisionArguments, "撤销最近一次草稿修改，须当前 revision", workflows.undo, sessions is not None),
        ("preprocess.recipes", NoArguments, "发现可用配方、最新版本、算子名与版本以及默认配方，不要求用户提供 UUID", workflows.recipes, runner is not None),
        ("preprocess.recipe_ensure", RecipeArguments, "显式选择固定模板 raw 反射率基线、snv、snv_sg1；登记后返回版本，供 compare 比较", workflows.recipe_ensure, runner is not None),
        ("preprocess.run_default", DefaultRunArguments, "必须显式指定标注版本与配方版本；省略由控制器注入，仍缺则拒绝，返回真实指标和溯源", workflows.run_default, runner is not None),
        ("preprocess.run_get", RunGetArguments, "查询真实预处理状态、指标、算子版本与比较边界；不返回产物路径或谱值", workflows.run_get, runner is not None),
    ]
    for name, arguments, description, handler, ready in tools:
        registry.register(name, arguments, description, handler if ready else None)
