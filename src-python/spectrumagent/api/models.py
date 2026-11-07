"""Modeling references, sample targets and PLS results; no local file paths."""
from typing import Annotated, Literal, Union

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, StrictBool, model_validator

from spectrumagent.modeling.run import TrainingRuns
from spectrumagent.modeling import ModelingError
from spectrumagent.data import DataError
from spectrumagent.modeling.dataset import SampleTargets
from spectrumagent.modeling.registry import ModelRegistry
from spectrumagent.modeling.inference import InferenceRuns


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_ids: list[StrictStr]
    annotation_version_ids: list[StrictStr]
    preprocess_run_ids: list[StrictStr]
    task: Literal["classification", "regression"]
    target: StrictStr
    cv_strategy: Literal["group_kfold", "random", "kfold", "loo"]
    cv_folds: Annotated[StrictInt, Field(ge=2)]
    seed: StrictInt
    split_strategy: Literal["ks", "spxy", "random", "stratified", "none"] = "none"

    @model_validator(mode="after")
    def compatible_split(self):
        if (self.task == "classification") != (self.split_strategy == "none"):
            raise ValueError("分类无外层划分；回归须显式指定外层划分")
        return self


class TargetValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: Annotated[float, Field(allow_inf_nan=False)]


class TargetCSV(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    project_id: StrictStr
    csv_text: Annotated[StrictStr, Field(max_length=2*1024*1024)]
    overwrite: StrictBool = False


class RegressionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    preprocess_run_ids: Annotated[list[StrictStr], Field(min_length=4)]
    target_schema_id: StrictStr
    task: Literal["regression"] = "regression"
    split_strategy: Literal["ks"] = "ks"
    test_ratio: Annotated[float, Field(gt=0, lt=1)] = 1/3
    cv_strategy: Literal["kfold", "loo"] = "kfold"
    cv_folds: Annotated[StrictInt, Field(ge=2)] = 5
    seed: StrictInt = 17
    n_components: Annotated[StrictInt, Field(ge=1)] | None = None
    max_components: Annotated[StrictInt, Field(ge=1)] | None = None


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_ids: list[StrictStr]
    annotation_version_ids: list[StrictStr]
    preprocess_run_ids: list[StrictStr]
    task: Literal["classification"]
    target: StrictStr
    cv_strategy: Literal["group_kfold"]
    cv_folds: Annotated[StrictInt, Field(ge=2)]
    seed: StrictInt
    split_strategy: Literal["none"] = "none"
    confidence_threshold: Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)] = 0
    n_components: Annotated[StrictInt, Field(ge=1, le=20)] | None = None
    max_components: Annotated[StrictInt, Field(ge=1, le=20)] | None = None

    @model_validator(mode="after")
    def label_target(self):
        if self.target != "label":
            raise ValueError("分类仅支持 label")
        return self


class RegisterModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: StrictStr
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] | None = None


class ModelStage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stage: Literal["experiment", "candidate", "production"]


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model_id: StrictStr
    cube_id: StrictStr
    preprocess_run_id: StrictStr
    annotation_version_id: StrictStr


def make_router(sessions, runner):
    router = APIRouter(prefix="/api/v1/models", tags=["models"])
    runs = TrainingRuns(runner.registry, sessions.paths)
    targets = SampleTargets(runner.registry.database)
    models = ModelRegistry(runner.registry, sessions.paths)
    inferences = InferenceRuns(runner.registry, sessions.paths)

    def guarded(action):
        try:
            return action()
        except ModelingError:
            raise
        except DataError as error:
            raise ModelingError(error.code, "模型输入不可用") from error
        except (OSError, ValueError) as error:
            raise ModelingError("MODEL_INPUT_UNAVAILABLE", "模型输入或产物不可用") from error

    @router.post("/registry")
    def register_model(body: RegisterModel):
        return guarded(lambda: models.register(body.run_id, body.name))

    @router.get("/registry")
    def list_models():
        return models.list()

    @router.put("/registry/{model_id}/stage")
    def set_model_stage(model_id: str, body: ModelStage):
        return models.set_stage(model_id, body.stage)

    @router.get("/registry/{model_id}/coefficients")
    def get_coefficients(model_id: str):
        return models.coefficients(model_id)

    @router.post("/inference-runs")
    def create_inference(body: InferenceRequest):
        return guarded(lambda: inferences.create(**body.model_dump()))

    @router.get("/inference-runs/{run_id}")
    def get_inference(run_id: str):
        return inferences.get(run_id)

    @router.get("/inference-runs/{run_id}/map")
    def get_inference_map(run_id: str):
        return guarded(lambda: inferences.map(run_id))

    @router.post("/sample-targets/import-csv")
    def import_targets(body: TargetCSV):
        return targets.import_csv(body.project_id, body.csv_text, overwrite=body.overwrite)

    @router.put("/sample-targets/{cube_id}/{schema_id}")
    def put_target(cube_id: str, schema_id: str, body: TargetValue):
        return targets.put(cube_id, schema_id, body.value)

    @router.get("/sample-targets")
    def list_targets(project_id: str | None = None):
        return targets.list(project_id)

    @router.post("/runs")
    def regression(body: Annotated[Union[RegressionRequest, ClassificationRequest], Field(discriminator="task")]):
        try:
            if body.task == "classification":
                return runs.classify(**body.model_dump())
            return runs.regress(**body.model_dump())
        except ModelingError:
            raise
        except (DataError, OSError, ValueError) as error:
            raise ModelingError(error.code if isinstance(error, DataError) else "INVALID_MODEL_INPUT", "回归输入不可用") from None

    @router.get("/runs/{run_id}/lv-sweep")
    def lv_sweep(run_id: str):
        return runs.artifact(run_id, "lv_sweep")

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
