"""11.4 HTTP adapters: typed requests, existing stores/engines, bounded downloads."""
import json
from pathlib import PurePosixPath
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Response, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.responses import FileResponse, StreamingResponse

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.data.validation import public_result
from spectrumagent.preprocess.schema import Pipeline
from spectrumagent.preprocess.export import artifact_path, export_run
from spectrumagent.preprocess import submissions
from spectrumagent.preprocess.capabilities import capabilities


MAX_ARTIFACT_BYTES = 8*1024*1024  # 11.4/R13 IPC response-size guard, bytes.


def _export_chunks(target):
    with target.open("rb") as stream:
        yield from iter(lambda: stream.read(1024*1024), b"")


class PreprocessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


Note = Annotated[str, Field(strict=True, max_length=2000)]


class PreprocessCreateRequest(PreprocessInput):
    code: Annotated[str, Field(strict=True)]
    name: Annotated[str, Field(strict=True)]
    description: Annotated[str, Field(strict=True)] | None = None
    pipeline: Pipeline
    note: Note | None = None


class PreprocessVersionRequest(PreprocessInput):
    pipeline: Pipeline
    note: Note | None = None


class PreprocessRunRequest(PreprocessInput):
    annotation_version_id: UUID
    recipe_version_id: UUID
    block_size: Annotated[int, Field(strict=True, gt=0)] | None = None
    guard: Literal["clip", "keep", "error"] | None = None
    note: Note | None = None


class PreprocessCompareRequest(PreprocessInput):
    annotation_version_id: UUID
    recipe_version_ids: Annotated[list[UUID], Field(min_length=1)]


class BatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_id: UUID
    annotation_version_id: UUID
    recipe_version_id: UUID

    @field_validator("cube_id", "annotation_version_id", "recipe_version_id", mode="before")
    @classmethod
    def json_uuid(cls, value):
        return UUID(value) if isinstance(value, str) else value


class RunBatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: Annotated[list[BatchItem], Field(min_length=1, max_length=32)]

    @field_validator("items", mode="before")
    @classmethod
    def batch_limit(cls, value):
        if isinstance(value, list) and len(value) > 32:
            raise DataError("INVALID_REQUEST", "批量输入超过上限", fields=["items"],
                            limit=32, actual=len(value), reason="batch_too_large")
        return value

    @model_validator(mode="after")
    def unique_cubes(self):
        if len({item.cube_id for item in self.items}) != len(self.items):
            raise ValueError("duplicate cube_id")
        return self


class RunBatchItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_id: str
    run_id: str | None
    status: Literal["succeeded", "failed"]
    error_code: str | None


class RunBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: Annotated[list[RunBatchItemResult], Field(min_length=1, max_length=32)]
    succeeded: Annotated[int, Field(ge=0, le=32)]
    failed: Annotated[int, Field(ge=0, le=32)]
    truncated: Literal[False]
    diagnostics: list['BatchDiagnostic'] | None = None


class FieldDiagnostic(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    field:str
    rule:str
    expected:str
    message:str


class BatchDiagnostic(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    cube_id:str
    run_id:str|None
    error:str
    detail:str
    fields:Annotated[list[FieldDiagnostic],Field(max_length=8)]


RunBatchResult.model_rebuild()


def not_found(code, detail, **context):
    error = DataError(code, detail, **context)
    error.status_code = 404
    return error


def store_call(method, *args, **kwargs):
    """Adapt legacy bare ValueErrors at the HTTP boundary; preserve DataErrors."""
    try:
        return method(*args, **kwargs)
    except KeyError as error:
        raise not_found("RECIPE_NOT_FOUND", "配方不存在") from error
    except ValueError as error:
        raise DataError("INVALID_REQUEST", "配方参数不合法",
                        fields=[{"field": "recipe", "message": "请检查配方名称、参数与备注"}]) from error
    except sqlite3.IntegrityError as error:
        raise DataError("INVALID_REQUEST", "配方 code 重复或项目选用约束不满足") from error


def make_router(runner, comparison):
    router = APIRouter(prefix="/api/v1", tags=["preprocess"])
    store = runner.recipes

    def require_project(project_id):
        with connect_database(store.database) as db:
            if db.execute("SELECT 1 FROM project WHERE id=?", (str(project_id),)).fetchone() is None:
                raise not_found("PROJECT_NOT_FOUND", "项目不存在", project_id=str(project_id))

    @router.get("/preprocess/recipes")
    def recipes():
        return store_call(store.list)

    @router.post("/preprocess/recipes", status_code=201)
    def create_recipe(request: PreprocessCreateRequest, submission_ref: Annotated[UUID | None, Header(alias='X-Submission-Ref')] = None):
        with submissions.execution_context(submissions.explicit_submission(str(submission_ref) if submission_ref else None)):
            return store_call(store.create, request.code, request.name, request.description, request.pipeline, note=request.note)

    @router.get("/preprocess/recipes/{recipe_id}")
    def recipe(recipe_id: UUID):
        return store_call(store.get, str(recipe_id))

    @router.post("/preprocess/recipes/{recipe_id}/versions", status_code=201)
    def add_version(recipe_id: UUID, request: PreprocessVersionRequest, submission_ref: Annotated[UUID | None, Header(alias='X-Submission-Ref')] = None):
        store_call(store.get, str(recipe_id))
        with submissions.execution_context(submissions.explicit_submission(str(submission_ref) if submission_ref else None)):
            return store_call(store.add_version, str(recipe_id), request.pipeline, note=request.note)

    @router.post("/preprocess/projects/{project_id}/recipes/{recipe_id}")
    def select_recipe(project_id: UUID, recipe_id: UUID):
        require_project(project_id)
        store_call(store.get, str(recipe_id))
        return store_call(store.select_project, str(project_id), str(recipe_id))

    @router.delete("/preprocess/projects/{project_id}/recipes/{recipe_id}", status_code=204)
    def deselect_recipe(project_id: UUID, recipe_id: UUID):
        require_project(project_id)
        store_call(store.get, str(recipe_id))
        store_call(store.deselect_project, str(project_id), str(recipe_id))
        return Response(status_code=204)

    @router.get("/preprocess/projects/{project_id}/recipes")
    def project_recipes(project_id: UUID):
        require_project(project_id)
        return store_call(store.project_recipes, str(project_id))

    @router.post("/datasets/{identifier}/preprocess/runs")
    def create_run(identifier: UUID, request: PreprocessRunRequest, submission_ref: Annotated[UUID | None, Header(alias='X-Submission-Ref')] = None):
        options = request.model_dump(exclude={"annotation_version_id", "recipe_version_id"}, exclude_none=True)
        with submissions.execution_context(submissions.explicit_submission(str(submission_ref) if submission_ref else None)):
            return public_result(store_call(runner.run, str(identifier), str(request.annotation_version_id), str(request.recipe_version_id), **options))

    @router.post("/preprocess/runs/batch", response_model=RunBatchResult,response_model_exclude_unset=True)
    def create_run_batch(request: RunBatchBody, submission_ref: Annotated[UUID | None, Header(alias='X-Submission-Ref')] = None):
        with submissions.execution_context(submissions.explicit_submission(str(submission_ref) if submission_ref else None)):
            return runner.run_batch(request.model_dump(mode="json")["items"])

    @router.get('/preprocess/operators')
    def operators():
        return capabilities(runner.operators)

    @router.get('/preprocess/submissions/{submission_ref}')
    def submission_result(submission_ref: UUID,owner_session_id:Annotated[UUID|None,Query()]=None):
        owner = str(owner_session_id) if owner_session_id else 'application'
        with connect_database(store.database) as db:
            identifiers = [row[0] for row in db.execute('SELECT operation_id FROM business_operation '
                'WHERE submission_ref=? AND owner_session_id=? ORDER BY action_ref', (str(submission_ref),owner))]
        return public_result({'submission_ref':str(submission_ref), 'operations':[submissions.get(store.database, op, owner) for op in identifiers]})

    @router.post('/preprocess/operations/{operation_id}/check')
    def operation_check(operation_id: UUID,owner_session_id:Annotated[UUID|None,Query()]=None):
        return public_result(runner.check_operation(str(operation_id),str(owner_session_id) if owner_session_id else 'application'))

    @router.get("/datasets/{identifier}/preprocess/runs")
    def runs(identifier: UUID):
        runner.registry.get(str(identifier))
        with connect_database(runner.database) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(
                "SELECT id,status,b01_branch,input_fingerprint,created_at,finished_at,error FROM preprocess_run "
                "WHERE cube_id=? ORDER BY created_at DESC LIMIT 50", (str(identifier),))]
        for row in rows:
            error = row.pop("error")
            row["error_code"] = None if error is None else json.loads(error)["error"]
        return rows

    @router.get("/preprocess/runs/{run_id}")
    def run_details(run_id: UUID):
        return public_result(store_call(runner.get, str(run_id)))

    @router.post("/datasets/{identifier}/preprocess/compare")
    def compare(identifier: UUID, request: PreprocessCompareRequest, submission_ref: Annotated[UUID | None, Header(alias='X-Submission-Ref')] = None):
        with submissions.execution_context(submissions.explicit_submission(str(submission_ref) if submission_ref else None)):
            return public_result(store_call(comparison.compare, str(identifier), str(request.annotation_version_id),
                              [str(version) for version in request.recipe_version_ids]))

    @router.get("/preprocess/runs/{run_id}/artifacts/{kind}")
    def artifact(run_id: UUID, kind: Literal["sample_spectra", "report", "processed_cube"]):
        row = store_call(runner.get, str(run_id))
        entry = next((item for item in row["artifacts"] if item["kind"] == kind
                      and (kind != "processed_cube" or item["relative_path"].endswith(".img"))), None)
        if entry is None:
            raise not_found("ARTIFACT_NOT_FOUND", "此 run 没有该类产物", run_id=str(run_id), kind=kind)
        value = entry["relative_path"]
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts or "\\" in value or ":" in value:
            raise DataError("INVALID_ARTIFACT_PATH", "产物须为 POSIX 相对路径")
        root = runner.paths.artifact_root.resolve()
        target = root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(root):
            raise DataError("INVALID_ARTIFACT_PATH", "产物路径越出输出根")
        if not target.is_file():
            raise not_found("ARTIFACT_NOT_FOUND", "产物文件不存在", run_id=str(run_id), kind=kind)
        size = target.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise DataError("ARTIFACT_TOO_LARGE", "产物超过 8 MiB 下载上限", size=size)
        return FileResponse(target, media_type="application/json" if kind == "report" else "application/octet-stream",
                            filename=target.name)

    @router.post("/preprocess/runs/{run_id}/exports")
    def create_export(run_id: UUID):
        return store_call(export_run, runner, str(run_id))

    @router.get("/preprocess/runs/{run_id}/exports/{filename}")
    def download_export(run_id: UUID, filename: str):
        if (PurePosixPath(filename).name != filename or filename in {".", ".."}
                or "\\" in filename or ":" in filename):
            raise DataError("INVALID_ARTIFACT_PATH", "产物须为 POSIX 相对路径")
        row = store_call(runner.get, str(run_id))
        entry = next((item for item in row["artifacts"] if item["kind"] == "processed_cube"
                      and PurePosixPath(item["relative_path"]).name == filename), None)
        if entry is None and filename=='export_manifest.json':
            image=next((item for item in row['artifacts'] if item['kind']=='processed_cube'
                        and PurePosixPath(item['relative_path']).name=='processed_cube.img'),None)
            if image is not None:
                entry={'relative_path':str(PurePosixPath(image['relative_path']).with_name(filename))}
        if entry is None:
            raise not_found("ARTIFACT_NOT_FOUND", "此 run 没有该导出产物")
        target = artifact_path(runner.paths.artifact_root, entry["relative_path"])
        if not target.is_file():
            raise not_found("ARTIFACT_NOT_FOUND", "产物文件不存在")
        return StreamingResponse(_export_chunks(target), media_type="application/octet-stream",
                                 headers={"Content-Disposition": f'attachment; filename="{target.name}"'})

    from .recipe_drafts import add_draft_routes
    add_draft_routes(router,runner)
    return router
