"""Reference-only modeling preflight endpoints, no spectra or artifact paths."""
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from spectrumagent.modeling.run import TrainingRuns
from spectrumagent.modeling import ModelingError
from spectrumagent.data import DataError


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_ids: list[StrictStr]
    annotation_version_ids: list[StrictStr]
    preprocess_run_ids: list[StrictStr]
    task: Literal["classification", "regression"]
    target: StrictStr
    cv_strategy: Literal["group_kfold", "random"]
    cv_folds: Annotated[StrictInt, Field(ge=2)]
    seed: StrictInt


def make_router(sessions, runner):
    router = APIRouter(prefix="/api/v1/models", tags=["models"])
    runs = TrainingRuns(runner.registry, sessions.paths)

    @router.post("/runs/preflight")
    def preflight(body: PreflightRequest):
        try:
            return runs.preflight(**body.model_dump())
        except ModelingError:
            raise
        except DataError as error:
            # Reader/operator contexts may contain local source paths. Keep only
            # their stable code at this reference-only HTTP boundary.
            raise ModelingError(error.code, "建模预检输入不可用") from error
        except OSError as error:
            raise ModelingError("SOURCE_CHANGED", "建模预检源文件不可用") from error

    @router.get("/runs/{run_id}")
    def get_run(run_id: str):
        return runs.get(run_id)

    @router.get("/runs")
    def list_runs(cube_id: str | None = None):
        return runs.list(cube_id)

    return router
