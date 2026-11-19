"""Conversation workflows: bounded scalar observations, server-owned geometry.

The v1 catalogue remains immutable. v2 provides discovery and explicit preview /
accept operations; neither spectral similarity nor an LLM supplies material truth.
"""
from copy import deepcopy
from spectrumagent.preprocess.recipes import pipeline_identity
from spectrumagent.preprocess.capabilities import AI_OPERATORS
from contextlib import nullcontext
from functools import wraps
import hashlib
import json
import re
import sqlite3
from uuid import UUID, uuid4

import numpy as np
from pydantic import Field, field_validator, model_validator
from typing import Annotated, Literal

from backend.database import connect_database
from spectrumagent.annotation.draft import conflict
from spectrumagent.annotation.engines.superpixels import Parameters
from spectrumagent.annotation.engines.diffusion import DEFAULT_THRESHOLD, DEFAULT_QUEUE_MIN_SIMILARITY
from spectrumagent.annotation.labels import LabelStore, CatalogRequest, CustomRequest, SchemaRequest, SchemaField
from spectrumagent.annotation.gestures import region_from_gesture
from spectrumagent.data import DataError
from spectrumagent.api.registry import display_names, safe_name
from spectrumagent.preprocess.migrations import BUILTIN_CODE, BUILTIN_PIPELINE
from spectrumagent.dataset_version.store import DatasetVersions
from . import ToolInput, Reference, CubeArguments, NoArguments, _run_summary


LIMIT = 50
Revision = Annotated[int, Field(ge=0)]


def _resource_operation(*, restore=True, required=False):
    def decorate(method):
        @wraps(method)
        def run(self, arguments):
            resources = getattr(self.sessions, 'resources', None)
            lease = resources.lease(arguments.cube_id, required=required, restore=restore) if resources and getattr(arguments, 'cube_id', None) else nullcontext()
            with lease:return method(self, arguments)
        return run
    return decorate


class ResolveArguments(ToolInput):
    query: Annotated[str, Field(min_length=1, max_length=200)]


class LabelAlias(ToolInput):
    alias: Reference
    class_code: Reference


class LabelsArguments(ToolInput):
    project_id: Reference | None = None
    cube_id: Reference | None = None  # Compatibility; never needed to select a project.
    aliases: list[LabelAlias] = Field(default_factory=list, max_length=30)
    class_codes: Annotated[list[Reference], Field(default_factory=list, max_length=30)]
    class_names: Annotated[list[Reference], Field(default_factory=list, max_length=30)]
    include_background: bool = True

    @model_validator(mode="after")
    def has_any_target(self):
        if not self.class_codes and not self.class_names and not self.aliases:
            raise ValueError("class_codes 与 class_names 至少提供一项")
        return self


class ProposeArguments(CubeArguments):
    class_code: Reference
    gesture_ref: Reference | None = None
    threshold: Annotated[float,Field(ge=-1,le=1)] = DEFAULT_THRESHOLD
    queue_min_similarity: Annotated[float,Field(ge=-1,le=1)] = DEFAULT_QUEUE_MIN_SIMILARITY


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


class AnnotationStatusArguments(ToolInput):
    cube_ids: Annotated[list[Reference], Field(min_length=1,max_length=32)]

    @field_validator('cube_ids')
    @classmethod
    def distinct_members(cls,values):
        if len(set(values))!=len(values):
            raise ValueError('需要不重复的数据集引用')
        return [str(UUID(value)) for value in values]


class RunGetArguments(ToolInput):
    run_id: Annotated[str,Field(pattern=r'^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$')]


class BatchToolItem(ToolInput):
    # Missing bindings must reach the handler's need_version response, not memory.
    cube_id: Reference | None = None
    annotation_version_id: Reference | None = None
    annotation_version_no: Annotated[int,Field(gt=0)] | None = None
    recipe_version_id: Reference | None = None


class BatchRunArguments(ToolInput):
    items: Annotated[list[BatchToolItem], Field(json_schema_extra={"maxItems": 32})] | None = None
    retry_of_submission: Annotated[str,Field(pattern=r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$',
        description='仅恢复失败成员时填原批次真实 submission_ref；首次执行省略或传 JSON null，不填占位文本')] | None = None

    @field_validator('retry_of_submission',mode='before')
    @classmethod
    def absent_retry(cls,value):
        # Some providers quote JSON null in this optional field. It carries no
        # identity: normalize only this exact absence marker, never real inputs.
        return None if value == 'null' else value


class VersionPreviewOptions(ToolInput):
    content_hash_dedup: bool = True
    preview_downsample: bool = True


class VersionPreviewArguments(ToolInput):
    cube_ids: Annotated[list[Reference], Field(min_length=1)]
    options: VersionPreviewOptions | None = None

    @field_validator("cube_ids")
    @classmethod
    def explicit_uuids(cls, values):
        return [str(UUID(value)) for value in values]


class VersionConfirmArguments(ToolInput):
    version_id: Reference

    @field_validator("version_id")
    @classmethod
    def explicit_uuid(cls, value):
        return str(UUID(value))


class PrepareBatchArguments(ToolInput):
    # 2026-11-13 ruling: segmentation takes an explicit cube scope. Version
    # determination/freezing belongs to the step before modeling, so no frozen
    # version is required here. The legacy version entry stays for that step.
    cube_ids: Annotated[list[Reference], Field(min_length=1)] | None = None
    dataset_version_id: Reference | None = None
    retry_of: Annotated[str, Field(pattern=r'^(?:b-[0-9a-f]{32}|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})$')] | None = None

    @field_validator('dataset_version_id')
    @classmethod
    def explicit_version_uuid(cls, value):
        return str(UUID(value)) if value is not None else None

    @field_validator('cube_ids')
    @classmethod
    def explicit_scope_uuids(cls, values):
        return [str(UUID(value)) for value in values] if values is not None else None

    @model_validator(mode='after')
    def one_scope(self):
        if self.cube_ids and self.dataset_version_id:
            raise ValueError('一次只能给出一种范围：cube_ids 或 dataset_version_id')
        return self


def _rows(database, query, arguments=()):
    with connect_database(database) as db:
        return db.execute(query, arguments).fetchall()


def dataset_catalog(datasets):
    rows = _rows(datasets.database, "SELECT id,payload,raw FROM dataset_registry ORDER BY rowid")
    names = display_names((identifier, json.loads(payload).get("name"), raw)
                          for identifier, payload, raw in rows)
    result = {"dataset_count": len(rows), "count": len(rows), "truncated": len(rows) > LIMIT}
    for index, (identifier, payload, _) in enumerate(rows[:LIMIT], 1):
        data = json.loads(payload)
        result.update({f"dataset_{index}_id": identifier, f"dataset_{index}_ref": f"D{index}",
                       f"dataset_{index}_name": names[identifier]})
        for key, value in zip(("n_lines", "n_samples", "n_bands"), data.get("shape", ())):
            result[f"dataset_{index}_{key}"] = value
    return result


def dataset_description(datasets, identifier):
    dataset, _ = datasets.get(identifier)
    return {"dataset_id": identifier, "cube_id": identifier, "display_name": datasets.display_names()[str(identifier)],
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
    def __init__(self, *, datasets, runner, comparison, sessions, diffusion, batch_prepare=None):
        self.datasets = datasets if datasets is not None else getattr(sessions, "registry", None)
        self.runner, self.comparison, self.sessions, self.diffusion = runner, comparison, sessions, diffusion
        if batch_prepare is None and sessions is not None and diffusion is not None:
            from spectrumagent.annotation.prepare_batch import BatchPrepareService
            batch_prepare = BatchPrepareService(DatasetVersions(self.datasets), diffusion.superpixels, sessions)
        self.batch_prepare = batch_prepare

    def prepare_batch(self, arguments):
        return self.batch_prepare.prepare(arguments.dataset_version_id, arguments.retry_of,
                                          cube_ids=arguments.cube_ids)

    def resolve(self, arguments):
        rows = _rows(self.datasets.database, "SELECT id,payload FROM dataset_registry ORDER BY rowid")
        query = arguments.query.strip().casefold()
        ordinal = re.fullmatch(r"(?:d|第)?(\d+)(?:项|个|个数据集)?", query)
        words = {"第一项": 1, "第一个": 1, "第一个数据集": 1, "第二项": 2, "第二个": 2,
                 "第三项": 3, "第三个": 3, "第一": 1, "第二": 2, "第三": 3}
        index = int(ordinal.group(1)) if ordinal else words.get(query)
        names = self.datasets.display_names()
        choices = [(i, identifier, names[identifier])
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

    @_resource_operation(restore=False)
    def _restore_draft_labels(self, cube_id):
        """Re-register labels a saved draft still paints but the registry lost.

        Drafts reference classes by code rather than label_id, so deleting or
        merging a label in the UI leaves the draft unrenderable. Restoring the
        exact code/name/color keeps the user's pixels instead of discarding them.
        """
        row = self.sessions.drafts.get(cube_id)
        if row is None:
            return []
        live = {item[0] for item in _rows(
            self.sessions.database,
            "SELECT l.code FROM label l JOIN dataset_registry d ON d.project_id=l.project_id WHERE d.id=?",
            (cube_id,))}
        missing = [item for item in row["document"].get("classes", []) if item.get("code") not in live]
        if not missing:
            return []
        project_id = _rows(self.sessions.database, "SELECT project_id FROM dataset_registry WHERE id=?", (cube_id,))[0][0]
        store = LabelStore(self.sessions.database)
        if not _rows(self.sessions.database, "SELECT id FROM label_schema WHERE project_id=? AND tree_path='材料'", (project_id,)):
            store.add(SchemaRequest(project_id=project_id, schema=SchemaField(name="材料", tree_path="材料", field_type="enum")))
        restored = []
        for item in missing:
            store.add(CustomRequest(project_id=project_id, code=item["code"], name=item.get("name") or item["code"],
                                    tree_path="材料", color_hex=item.get("color") or "#9aa7b2"))
            restored.append({"code": item["code"], "name": item.get("name") or item["code"]})
        return restored

    def context(self, arguments):
        cube_id = arguments.cube_id
        with self.sessions._lock:
            restored, reset = [], False
            try:
                state = self.sessions._state(cube_id)
            except DataError as error:
                if error.code != "LABEL_REMOVED":
                    raise
                restored = self._restore_draft_labels(cube_id)
                if not restored:
                    # Nothing persisted references the removed label: only the
                    # in-memory working copy is stale, so rebuild it from the draft.
                    self.sessions.forget(cube_id)
                    reset = True
                state = self.sessions._state(cube_id)
            labels = self.sessions.drafts.labels(cube_id)
            document = json.loads(state.document_json)
            dataset, _ = self.datasets.get(cube_id)
            latest = _rows(self.sessions.database,
                "SELECT id,version_no FROM annotation_version WHERE cube_id=? ORDER BY version_no DESC LIMIT 1", (cube_id,))
            summary = {"cube_id": cube_id, "display_name": self.datasets.display_names()[str(cube_id)], "revision": state.revision,
                       "n_regions": len(document["regions"]), "n_classes": len(labels),
                       "segmentation_ready": state.segments is not None,
                       "latest_annotation_version_id": latest[0][0] if latest else None,
                       "latest_annotation_version_no": latest[0][1] if latest else None,
                       "blank_pixels": int(np.count_nonzero(state.label_map == -1)),
                       "uncertain_pixels": int(np.count_nonzero(state.label_map == -2)),
                       "labeled_pixels": int(np.count_nonzero(state.label_map >= 0)),
                       "regions_truncated": len(document["regions"]) > LIMIT}
            saved_state=_rows(self.sessions.database,'SELECT annotation_version_id,draft_revision,document_sha256 FROM annotation_confirmation_state WHERE cube_id=?',(cube_id,))
            digest=hashlib.sha256(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            current_saved=bool(saved_state and latest and saved_state[0][0]==latest[0][0] and saved_state[0][1]==state.revision and saved_state[0][2]==digest)
            foreground=_rows(self.sessions.database,'SELECT COUNT(DISTINCT s.label_id) FROM sample_spectrum s JOIN label l ON l.id=s.label_id '
                             'WHERE s.version_id=? AND s.n_pixels>0 AND l.is_background=0',(latest[0][0],))[0][0] if latest else 0
            summary.update(annotation_saved=current_saved,saved_version_available=bool(latest),annotation_policy='foreground_with_optional_background',
                           effective_label_count=len({int(x) for x in np.unique(state.label_map) if x >= 0}),
                           saved_foreground_label_count=foreground,coverage_confirmation='not_recorded',
                           training_admission='saved_snapshot_available_preflight_required' if foreground else 'need_saved_foreground' if latest else 'need_saved_annotation')
            if restored:
                summary["restored_label_count"] = len(restored)
                for index, item in enumerate(restored, 1):
                    summary[f"restored_label_{index}_code"] = item["code"]
                    summary[f"restored_label_{index}_name"] = item["name"]
            if reset:
                summary["reset_working_state"] = True
            resources = getattr(self.sessions,'resources',None)
            if resources is not None:summary.update(resources.status(cube_id))
            else:summary.update(segmentation_ref=None,segmentation_durable=False,segmentation_recoverable=False)
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

    def status_batch(self, arguments):
        """Read each actual context; no prepare, assignment or save side effects."""
        from . import CubeArguments
        catalog=dataset_catalog(self.datasets)
        refs={catalog[f'dataset_{i}_id']:catalog[f'dataset_{i}_ref'] for i in range(1,min(catalog['count'],LIMIT)+1)}
        summary={'member_count':len(arguments.cube_ids),'checked_count':0,'error_count':0,'truncated':False}
        keys=('cube_id','display_name','annotation_saved','saved_version_available','latest_annotation_version_id',
              'latest_annotation_version_no','saved_foreground_label_count','labeled_pixels','blank_pixels',
              'uncertain_pixels','annotation_policy','coverage_confirmation','segmentation_ready',
              'segmentation_durable','segmentation_recoverable')
        for index,cube in enumerate(arguments.cube_ids,1):
            prefix=f'item_{index}_'
            summary[prefix+'cube_id']=cube
            if cube in refs:summary[prefix+'dataset_ref']=refs[cube]
            try:
                value=self.context(CubeArguments(cube_id=cube))
            except DataError as error:
                summary[prefix+'error']=error.code
                summary['error_count']+=1
                continue
            summary['checked_count']+=1
            summary.update({prefix+key:value.get(key) for key in keys})
            summary[prefix+'class_codes']='、'.join(value[f'class_{i}_code'] for i in range(1,LIMIT+1)
                if value.get(f'class_{i}_pixel_count',0)>0 and value.get(f'class_{i}_code'))
        return summary

    def prepare(self, arguments):
        params = Parameters()  # Registered platform/UI defaults, not LLM choices.
        segmentation, action = self.diffusion.superpixels.prepare_with_action(arguments.cube_id, self.sessions, params)
        return {"cube_id": arguments.cube_id, "status": "ready", "action": action, "profile": "annotation-default-v1",
                "n_segments": params.n_segments, "compactness": params.compactness,
                "pca_components": params.pca_components,
                "superpixel_count": int(segmentation.report["superpixel_count"]),
                "threshold": DEFAULT_THRESHOLD, "queue_min_similarity": DEFAULT_QUEUE_MIN_SIMILARITY,
                "source": "TASK-04 平台已登记默认值；仅准备分割，不识别材质"}

    @_resource_operation(restore=False)
    def ensure_labels(self, arguments):
        with self.sessions._lock:
            cube_id = arguments.cube_id
            project_id = arguments.project_id
            if cube_id:
                self.datasets.get(cube_id)
                actual = _rows(self.sessions.database, "SELECT project_id FROM dataset_registry WHERE id=?", (cube_id,))[0][0]
                if project_id and project_id != actual:
                    raise DataError('INVALID_REQUEST', '图片与项目不一致')
                project_id = actual
            projects = _rows(self.sessions.database, 'SELECT id FROM project')
            if project_id is None and len(projects) == 1:
                project_id = projects[0][0]
            if project_id not in {r[0] for r in projects}:
                return {'status': 'need_project', 'detail': '请明确创建标签的项目'}
            store = LabelStore(self.sessions.database)
            from spectrumagent.annotation.labels import plastic_catalog
            catalog = {item["code"]: item for item in plastic_catalog()}
            rows = _rows(self.sessions.database, "SELECT code,name FROM label WHERE project_id=?", (project_id,))
            existing = {row[0] for row in rows}
            code_by_name = {row[1]: row[0] for row in rows}
            from spectrumagent.annotation.aliases import normalized, resolve, add as add_alias
            for alias in arguments.aliases:
                add_alias(self.sessions.database, project_id, alias.alias, alias.class_code)
            for raw in arguments.class_names:
                code = resolve(self.sessions.database, project_id, raw)
                if code:
                    code_by_name[normalized(raw)] = code
            known = set(catalog) | {"BG"}
            wanted = set(arguments.class_codes)
            if wanted - existing - known:
                raise DataError("LABEL_NOT_FOUND", "class_codes 只接受材料目录中已登记的 code；若这是用户给出的类别名称（如中文），请把原名放进 class_names 重试，平台会生成占位 code")
            # User-supplied names are registered verbatim: Chinese names are never
            # transliterated and an unknown name gets a placeholder code, matching
            # the folder-import convention (L001...) for the user to confirm later.
            catalog_by_name = {item["name"]: code for code, item in catalog.items()}
            planned, used, serial = [], set(existing) | known | wanted, 1
            for name in dict.fromkeys(normalized(raw) for raw in arguments.class_names):
                if not name:
                    continue
                if name in code_by_name:
                    wanted.add(code_by_name[name])
                elif name in catalog_by_name:
                    wanted.add(catalog_by_name[name])
                else:
                    while f"L{serial:03d}" in used:
                        serial += 1
                    code = f"L{serial:03d}"
                    used.add(code)
                    planned.append((name, code))
            wanted.update(code for _, code in planned)
            if not _rows(self.sessions.database, "SELECT id FROM label_schema WHERE project_id=? AND tree_path='材料'", (project_id,)):
                store.add(SchemaRequest(project_id=project_id, schema=SchemaField(name="材料", tree_path="材料", field_type="enum")))
            missing = sorted((wanted | ({"BG"} if arguments.include_background else set())) - existing)
            catalog_codes = [code for code in missing if code in catalog]
            if catalog_codes:
                store.add(CatalogRequest(project_id=project_id, from_catalog="plastic", codes=catalog_codes))
            if "BG" in missing:
                store.add(CustomRequest(project_id=project_id, code="BG", name="背景", tree_path="材料/塑料/BG",
                                        color_hex="#9aa7b2", is_background=True))
            palette = ("#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2")
            created_labels = []
            for index, (name, code) in enumerate(planned):
                row = store.add(CustomRequest(project_id=project_id, code=code, name=name, tree_path="材料",
                                              color_hex=palette[(len(existing) + index) % len(palette)]))
                created_labels.append({"code": code, "name": name, "id": row["id"]})
            result = self.context(CubeArguments(cube_id=cube_id)) if cube_id else {'project_id': project_id}
            result.update(status="ready", project_id=project_id, created_label_count=len(missing),
                          resolved_class_codes=",".join(sorted(wanted)))
            for index, item in enumerate(created_labels, 1):
                result[f"created_label_{index}_code"] = item["code"]
                result[f"created_label_{index}_name"] = item["name"]
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

    @_resource_operation()
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
            if self.sessions.resources is not None:
                self.sessions.resources.ensure(state.segments.nbytes*4+(int(state.segments.max())+1)*512+8*1024**2,
                                               cube=str(cube_id))
            result = self.diffusion.generate(cube_id, self.sessions.resolve_gesture(cube_id, gesture_ref),
                threshold=arguments.threshold, queue_min_similarity=arguments.queue_min_similarity)
            state = self.sessions._state(cube_id)
            self._clear_previews(cube_id, state)
            candidate = result["candidate"]
            if not result["enqueued"]:
                # The existing queue guard deliberately withholds this overlay.
                # Do not issue an accept-able reference for an invisible region.
                return {"cube_id": cube_id, "status": "need_seed", "revision": state.revision,
                        "class_code": arguments.class_code, "below_queue_floor": True,
                        "pixel_count": candidate["pixel_count"], "min_similarity": candidate["min_similarity"],
                        "threshold": arguments.threshold, "queue_min_similarity": arguments.queue_min_similarity,
                        "detail": "该扩散区域低于入队相似度下限，未进入可接受预览且未修改草稿。请重新指认更有代表性的种子；相似度不是材质识别置信度。"}
            candidate_ref = "c-" + uuid4().hex
            if self.sessions.resources is not None:
                from spectrumagent.annotation.segmentation_resources import unique_bytes
                self.sessions.resources.ensure(unique_bytes(candidate)*2+65536,cube=str(cube_id))
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
                    "below_queue_floor": not result["enqueued"], "threshold": arguments.threshold,
                    "queue_min_similarity": arguments.queue_min_similarity,
                    "detail": "候选已预览，草稿尚未修改；相似度不是材质识别置信度。确认后才接受候选。"}

    @_resource_operation(required=True)
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

    @_resource_operation(restore=False)
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

    @_resource_operation()
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

    @_resource_operation(required=True)
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

    @_resource_operation(restore=False)
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

    @_resource_operation()
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
        result = {"recipe_count": len(items), "truncated": len(items) > LIMIT,
                  'ai_operators': ', '.join(name+'@1' for name in AI_OPERATORS),
                  'sg_parameter_rules': 'window 为正奇数；polyorder 非负且严格小于 window；order 为 1 或 2',
                  'sg_data_conditions': 'interp 窗口不得超过该步骤输入的有效波段数',
                  'baseline': '零附加步骤合法；反射率转换由运行前置，禁止加入配方'}
        for i, recipe in enumerate(items[:LIMIT], 1):
            version = recipe["versions"][-1]
            if recipe["code"] == BUILTIN_CODE:
                version = next((item for item in reversed(recipe["versions"]) if pipeline_identity(item["pipeline"])[0] == pipeline_identity(BUILTIN_PIPELINE)[0]), version)
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
            recipe = store.by_code(code)
            if recipe is not None and recipe['deleted']:
                raise DataError('RECIPE_DELETED','固定模板已在本次运行删除；需要用户明确恢复，不自动复活')
            if recipe is None:
                try:
                    recipe = store.create(code, name, "对话编排显式选择的固定模板；不宣称普遍最优", deepcopy(pipeline))
                except sqlite3.IntegrityError:
                    # A different process may have created the same fixed code.
                    recipe = store.by_code(code)
                    if recipe is None:
                        raise DataError('RECIPE_NOT_FOUND','模板登记冲突后仍无法找到配方') from None
                    if recipe['deleted']:
                        raise DataError('RECIPE_DELETED','固定模板已删除，不能自动恢复') from None
            version = next((item for item in reversed(recipe["versions"]) if pipeline_identity(item["pipeline"])[0] == pipeline_identity(pipeline)[0]), None)
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
        from . import check_run_error
        check_run_error(row)
        result = _run_summary(row)
        result.update(run_provenance(self.runner, row))
        return result

    def run_get(self, arguments):
        row = self.runner.get(arguments.run_id)
        return {**_run_summary(row), **run_provenance(self.runner, row)}

    def run_batch(self, arguments):
        items = arguments.model_dump()["items"]
        if not items:
            return {"status": "need_version", "missing": "items",
                    "detail": "请逐样品明确数据集、标注版本与配方版本，不采用记忆或最新版本。"}
        for item in items:
            if item.get('cube_id'):
                try:item['cube_id']=str(UUID(item['cube_id']))
                except ValueError:pass
        from ..tool_context import owner_session
        retained=0
        retry_submission=None
        retry_state=None
        if arguments.retry_of_submission:
            from spectrumagent.preprocess import submissions
            from spectrumagent.preprocess.retry import bind as bind_retry
            current=submissions.current_submission.get() or submissions.explicit_submission(owner=owner_session.get() or 'application')
            with connect_database(self.runner.database) as db:
                original_reference,retry_submission,retry_state=bind_retry(db,arguments.retry_of_submission,current,[item.get('cube_id') for item in items])
            retained=retry_state['retained_succeeded']
        for index, item in enumerate(items, 1):
            if item.get('annotation_version_no') is not None and item.get('cube_id'):
                with connect_database(self.runner.database) as db:
                    row=db.execute('SELECT id FROM annotation_version WHERE cube_id=? AND version_no=?',
                                   (item['cube_id'],item['annotation_version_no'])).fetchone()
                if row is None or item.get('annotation_version_id') not in (None,row[0]):
                    return {'status':'need_version','missing':f'item_{index}_annotation_version_id',
                            'detail':'标注版本号与真实引用不一致，本次批量未执行；请核对标注版本'}
                item['annotation_version_id']=row[0]
            for key in ("cube_id", "annotation_version_id", "recipe_version_id"):
                try:
                    if item[key] is None:
                        raise ValueError("missing")
                    item[key]=str(UUID(item[key]))
                except ValueError:
                    return {"status": "need_version", "missing": f"item_{index}_{key}",
                            "detail": "请明确本批每个样品的版本引用；不按序号猜测、不从记忆补入。"}
            with connect_database(self.runner.database) as db:
                checks=(('cube_id','SELECT 1 FROM dataset_registry WHERE id=?',(item['cube_id'],)),
                        ('annotation_version_id','SELECT 1 FROM annotation_version WHERE id=? AND cube_id=?',(item['annotation_version_id'],item['cube_id'])),
                        ('recipe_version_id','SELECT 1 FROM preprocess_recipe_version WHERE id=?',(item['recipe_version_id'],)))
                for key,sql,values in checks:
                    if db.execute(sql,values).fetchone() is None:
                        return {'status':'need_version','missing':f'item_{index}_{key}',
                                'detail':'引用不存在或不属于该样品，本次批量未执行；请从真实状态重新取得引用，或使用明确标注版本号'}
        items=[{key:item[key] for key in ('cube_id','annotation_version_id','recipe_version_id')} for item in items]
        if retry_submission:
            with submissions.execution_context(retry_submission):batch=self.runner.run_batch(items)
        else:batch = self.runner.run_batch(items)
        if batch.get('diagnostics'):
            diagnostic=batch['diagnostics'][0]
            raise DataError(diagnostic['error'],diagnostic['detail'],fields=diagnostic['fields'],
                            run_id=diagnostic['run_id'],completed_count=batch['succeeded'])
        summary = {"succeeded": batch["succeeded"], "failed": batch["failed"], "truncated": batch["truncated"],
                   'status':'partial' if batch['failed'] and batch['succeeded'] else 'failed' if batch['failed'] else 'succeeded'}
        if arguments.retry_of_submission:
            remaining=retry_state['remaining_failed']
            summary.update(retry_of_submission=original_reference,retained_succeeded=retained,remaining_failed=remaining)
            if remaining:summary['status']='partial' if retained+batch['succeeded'] else 'failed'
        from spectrumagent.preprocess import submissions
        submitted = submissions.current_submission.get()
        if submitted is not None:
            summary['submission_ref'] = submitted.submission_ref
        for index, item in enumerate(batch["items"], 1):
            summary.update({f"item_{index}_{key}": value for key, value in item.items()})
            if item["run_id"]:
                # Reuse the existing provenance projection, never the artifact document.
                row = self.runner.get(item["run_id"])
                from . import check_run_error
                check_run_error(row,completed_count=batch['succeeded'])
                summary.update({f"item_{index}_{key}": value for key, value in run_provenance(self.runner, row).items()})
        return summary

    def version_preview(self, arguments):
        row = DatasetVersions(self.datasets).preview(arguments.cube_ids,
            arguments.options.model_dump() if arguments.options is not None else None)
        frozen = _rows(self.datasets.database, "SELECT is_frozen FROM dataset_version WHERE id=?", (row["version_id"],))
        return {**{key: row[key] for key in ("version_id", "reused", "duplicate_of", "cube_count", "blocked")},
                "is_frozen": frozen[0][0]}

    def version_confirm(self, arguments):
        row = DatasetVersions(self.datasets).confirm(arguments.version_id)
        return {"version_id": row["dataset_version_id"], "is_frozen": row["is_frozen"], "confirmed_at": row["confirmed_at"]}

    def version_list(self, _):
        rows = DatasetVersions(self.datasets).list_frozen()
        summary = {"version_count": len(rows), "truncated": False}
        for index, row in enumerate(rows, 1):
            summary.update({f"version_{index}_{key}": value for key, value in row.items() if key != "cube_ids"})
            summary.update({f"version_{index}_cube_{j}_id": cube for j, cube in enumerate(row["cube_ids"], 1)})
        return summary


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
        ("annotations.status_batch",AnnotationStatusArguments,"只读核对明确数据列表的标注状态，每批最多32项；返回每项已保存版本、工作副本是否已保存、留白及分割状态，不生成分割、不赋类、不保存；全部范围超过32时继续下一批，不重复询问已明确范围",workflows.status_batch,sessions is not None),
        ("datasets.resolve", ResolveArguments, "按名称、唯一 UUID 前缀、D 序号或第一项解析数据集；歧义时返回匹配，不猜测", workflows.resolve, datasets is not None),
        ("annotations.context", CubeArguments, "当前标签、区域引用、草稿 revision、分割状态、最近手势、最新已保存版本；无几何和光谱", workflows.context, sessions is not None),
        ("annotations.prepare", CubeArguments, "用户授权默认参数时生成默认超像素；只分割，不识别材质", workflows.prepare, sessions is not None and diffusion is not None),
        ("annotations.prepare_batch", PrepareBatchArguments, "对本轮明确给出的cube_ids范围提交默认分割后台任务，返回accepted和task_id仅表示受理，真实进度与就绪由任务卡片查询；范围不冻结版本、不按最新或记忆补入、没有成员数上限；dataset_version_id为兼容入口，二选一不可同传；retry_of引用父任务或兼容旧回执；不识别材质、不保存标注", workflows.prepare_batch, workflows.batch_prepare is not None),
        ("annotations.ensure_labels", LabelsArguments, "确保项目共用标签及可选背景存在，不修改已有标签；project_id 指定项目，唯一项目可省略；已有 code 用 class_codes，新名称用 class_names 保留原名；仅用户明确声明的别名可通过 aliases 关联已有 code，不自动翻译或合并", workflows.ensure_labels, sessions is not None),
        ("annotations.propose", ProposeArguments, "按现有手势原谱相似扩散，仅预览 candidate_ref；无手势返回 need_seed，不猜测 PP 材质", workflows.propose, sessions is not None and diffusion is not None),
        ("annotations.apply_candidate", ApplyArguments, "用户接受预览后按引用与 revision 写入草稿；支持首笔 revision=0", workflows.apply, sessions is not None),
        ("annotations.reject_candidate", CandidateArguments, "用户说不要此候选时清预览引用；不修改草稿", workflows.reject, sessions is not None),
        ("annotations.set_background", RevisionArguments, "用户明确说其余背景时，仅将前景之外的留白标背景，保留已标类和不确定像素", workflows.background, sessions is not None),
        ("annotations.mark_region", MarkArguments, "按当前手势把区域标为不确定或擦除；服务器解析几何，不添加材质类别，支持首笔 revision=0", workflows.mark, sessions is not None),
        ("annotations.edit_region", EditArguments, "按上下文的区域引用改类或删除；不要向用户索要 region_id", workflows.edit, sessions is not None),
        ("annotations.undo", RevisionArguments, "撤销最近一次草稿修改，须当前 revision", workflows.undo, sessions is not None),
        ("preprocess.recipes", NoArguments, "列出可用配方及其最新版本；返回 recipe_i_version_id 供 run_default 绑定或 compare 使用，不要求用户提供 UUID", workflows.recipes, runner is not None),
        ("preprocess.recipe_ensure", RecipeArguments, "显式选择固定模板 raw 反射率基线、snv、snv_sg1；登记后返回 recipe_version_id，供 run_default 运行或 compare 比较", workflows.recipe_ensure, runner is not None),
        ("preprocess.run_default", DefaultRunArguments, "必须显式指定已确认的 annotation_version_id 与 recipe_version_id，或用户明确授权使用的本轮实际结果；候选发现不代表确认；缺一返回 need_version，不从记忆补入、不选最新或内置默认；返回真实指标和溯源", workflows.run_default, runner is not None),
        ("preprocess.run_get", RunGetArguments, "查询真实预处理状态、指标、算子版本与比较边界；不返回产物路径或谱值", workflows.run_get, runner is not None),
        ("preprocess.run_batch", BatchRunArguments, "按显式成员批量预处理，最多32项。标注可用真实annotation_version_id或已确认的annotation_version_no，由服务端按该cube精确解析；不猜UUID、不选最新。所有引用执行前核验。重试带retry_of_submission且items只列原失败成员及修正引用，成功成员保留。缺参返回need_version", workflows.run_batch, runner is not None),
        ("versions.preview", VersionPreviewArguments, "建模前一步：按显式 cube_ids 预览数据集版本；只返回版本与数量摘要，不返回源路径或谱值；批量分割与标注不需要先走这一步", workflows.version_preview, datasets is not None),
        ("versions.confirm", VersionConfirmArguments, "建模前一步：按显式 version_id 冻结既有预览版本；仅冻结，不绑定配方或预处理 run；分割标注阶段不要求冻结", workflows.version_confirm, datasets is not None),
        ("versions.list", NoArguments, "列出已冻结数据集版本及有序 cube 引用；不选最新、不列未冻结版本", workflows.version_list, datasets is not None),
    ]
    for name, arguments, description, handler, ready in tools:
        registry.register(name, arguments, description, handler if ready else None)
