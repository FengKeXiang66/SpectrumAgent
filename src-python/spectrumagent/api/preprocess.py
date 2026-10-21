"""11.4 HTTP adapters: typed requests, existing stores/engines, bounded downloads."""
import json
from pathlib import PurePosixPath
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import FileResponse

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.preprocess.schema import Pipeline


MAX_ARTIFACT_BYTES = 8*1024*1024  # 11.4/R13 IPC response-size guard, bytes.


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
                        fields=[{"field": "recipe", "message": str(error)}]) from error
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
    def create_recipe(request: PreprocessCreateRequest):
        return store_call(store.create, request.code, request.name, request.description, request.pipeline, note=request.note)

    @router.get("/preprocess/recipes/{recipe_id}")
    def recipe(recipe_id: UUID):
        return store_call(store.get, str(recipe_id))

    @router.post("/preprocess/recipes/{recipe_id}/versions", status_code=201)
    def add_version(recipe_id: UUID, request: PreprocessVersionRequest):
        store_call(store.get, str(recipe_id))
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
    def create_run(identifier: UUID, request: PreprocessRunRequest):
        options = request.model_dump(exclude={"annotation_version_id", "recipe_version_id"}, exclude_none=True)
        return store_call(runner.run, str(identifier), str(request.annotation_version_id), str(request.recipe_version_id), **options)

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
        return store_call(runner.get, str(run_id))

    @router.post("/datasets/{identifier}/preprocess/compare")
    def compare(identifier: UUID, request: PreprocessCompareRequest):
        return store_call(comparison.compare, str(identifier), str(request.annotation_version_id),
                          [str(version) for version in request.recipe_version_ids])

    @router.get("/preprocess/runs/{run_id}/artifacts/{kind}")
    def artifact(run_id: UUID, kind: Literal["sample_spectra", "report"]):
        row = store_call(runner.get, str(run_id))
        entry = next((item for item in row["artifacts"] if item["kind"] == kind), None)
        if entry is None:
            raise not_found("ARTIFACT_NOT_FOUND", "此 run 没有该类产物", run_id=str(run_id), kind=kind)
        value = entry["relative_path"]
        relative = PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts or "\\" in value or ":" in value:
            raise DataError("INVALID_ARTIFACT_PATH", "产物须为 POSIX 相对路径")
        root = runner.paths.preprocessed.resolve()
        target = root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(root):
            raise DataError("INVALID_ARTIFACT_PATH", "产物路径越出输出根")
        if not target.is_file():
            raise not_found("ARTIFACT_NOT_FOUND", "产物文件不存在", run_id=str(run_id), kind=kind)
        size = target.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise DataError("ARTIFACT_TOO_LARGE", "产物超过 8 MiB 下载上限", size=size)
        return FileResponse(target, media_type="application/octet-stream" if kind == "sample_spectra" else "application/json",
                            filename=target.name)

    return router
