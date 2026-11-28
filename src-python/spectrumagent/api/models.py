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
    evaluation_protocol: Literal["nested_group_cv", "exploratory_group_cv"] | None = None
    sample_groups: dict[StrictStr, StrictStr] | None = None

    @model_validator(mode="after")
    def compatible_split(self):
        if (self.task == "classification") != (self.split_strategy == "none"):
            raise ValueError("分类无外层划分；回归须显式指定外层划分")
        return self


class EmptyTrainingAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ContinueTraining(EmptyTrainingAction):
    job_id: StrictStr


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
    band_selection: Literal["ipls"] | None = None
    recipe_version_id: StrictStr | None = None
    evaluation_protocol: Literal["nested_group_cv", "exploratory_group_cv"] | None = None
    sample_groups: dict[StrictStr, StrictStr] | None = None

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
    preprocess_run_id: StrictStr | None = None
    annotation_version_id: StrictStr | None = None


class ClassificationOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scope: Literal["pixel", "sample"] = "pixel"
    population: Literal["accepted", "all_labeled"] = "accepted"
    normalization: Literal["count", "row", "column"] = "count"
    opacity: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.85
    offset: Annotated[StrictInt, Field(ge=0)] = 0
    limit: Annotated[StrictInt, Field(ge=1, le=50)] = 5
    cube_index: Annotated[StrictInt, Field(ge=0)] = 0
    layer: Literal["prediction", "truth", "errors", "rejected", "confidence", "base"] = "prediction"
    level: Annotated[StrictInt, Field(ge=0, le=20)] = 0
    tile_x: Annotated[StrictInt, Field(ge=0)] = 0
    tile_y: Annotated[StrictInt, Field(ge=0)] = 0
    row: Annotated[StrictInt, Field(ge=0)] = 0
    column: Annotated[StrictInt, Field(ge=0)] = 0
    end_row: Annotated[StrictInt, Field(ge=1)] | None = None
    end_column: Annotated[StrictInt, Field(ge=1)] | None = None
    all_cubes: StrictBool = False
    true_label: Annotated[StrictInt, Field(ge=0)] | None = None
    predicted_label: Annotated[StrictInt, Field(ge=-2)] | None = None
    hidden: Annotated[list[StrictInt], Field(max_length=256)] = Field(default_factory=list)
    colors: dict[StrictStr, Annotated[StrictStr, Field(pattern=r"^#[0-9a-fA-F]{6}$")]] = Field(default_factory=dict)
    repeats: Annotated[StrictInt, Field(ge=2, le=20)] = 5
    comparison_id: StrictStr | None = None
    model_id: StrictStr | None = None
    prediction_id: StrictStr | None = None
    annotation_version_id: StrictStr | None = None
    task_id: StrictStr | None = None
    name: Annotated[StrictStr, Field(min_length=1, max_length=200)] | None = None
    cube_ids: Annotated[list[StrictStr], Field(max_length=1000)] = Field(default_factory=list)
    threshold: Annotated[float, Field(ge=0, lt=1, allow_inf_nan=False)] | None = None
    cloud: StrictBool = False
    clear: StrictBool = False
    format: Literal["bundle", "html", "pdf", "docx", "json", "csv", "png", "svg"] = "bundle"
    figure: Annotated[StrictStr, Field(pattern=r"^[a-z0-9_-]{1,80}$")] = "confusion-pixel"


def make_router(sessions, runner, boot_id=None):
    router = APIRouter(prefix="/api/v1/models", tags=["models"])
    runs = TrainingRuns(runner.registry, sessions.paths)
    from spectrumagent.modeling.training_jobs import jobs_for
    training_jobs = jobs_for(runner.registry, sessions.paths, boot_id)
    targets = SampleTargets(runner.registry.database)
    models = ModelRegistry(runner.registry, sessions.paths)
    inferences = InferenceRuns(runner.registry, sessions.paths)
    from spectrumagent.modeling.classification_operations import operations_for
    classification = operations_for(runner.registry, sessions.paths)

    def guarded(action):
        try:
            return action()
        except ModelingError:
            raise
        except DataError as error:
            raise ModelingError(error.code, "模型输入不可用") from error
        except (OSError, ValueError) as error:
            raise ModelingError("MODEL_INPUT_UNAVAILABLE", "模型输入或产物不可用") from error

    @router.post("/classification/{evaluation_id}/{action}")
    def classification_operation(evaluation_id: str, action: Literal["curves", "map", "pixel", "coefficients", "importance",
            "compare", "interpret", "register", "baseline", "infer", "task", "cancel", "retry", "export", "threshold", "choices", "evaluate_prediction"],
            body: ClassificationOperation):
        return guarded(lambda: classification.perform(evaluation_id, action, body))

    @router.get("/classification-exports/{export_id}")
    def classification_download(export_id: str):
        from backend.database import connect_database
        from pathlib import Path
        from fastapi.responses import FileResponse
        from spectrumagent.modeling.evaluation import Evaluations
        with connect_database(runner.registry.database) as db:
            row = db.execute("SELECT path,sha256 FROM classification_export WHERE id=?", (export_id,)).fetchone()
        if not row:
            raise ModelingError("EXPORT_NOT_FOUND", "导出文件不存在")
        path = Path(row[0])
        if not path.is_file() or Evaluations.file_hash(path) != row[1]:
            raise ModelingError("ARTIFACT_HASH_MISMATCH", "导出文件缺失或被修改")
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

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

    @router.put("/training-jobs/{job_id}", status_code=202)
    def submit_training(job_id: str, body: ClassificationRequest):
        return guarded(lambda: training_jobs.submit(job_id, body.model_dump()))

    @router.get("/training-jobs/{job_id}")
    def training_status(job_id: str):
        return training_jobs.status(job_id)

    @router.get('/training-jobs')
    def training_list():
        return training_jobs.list()

    @router.get('/training-jobs/{job_id}/events')
    def training_events(job_id: str, after: Annotated[int, Field(ge=0)] = 0,
                        limit: Annotated[int, Field(ge=1, le=50)] = 50):
        return training_jobs.events(job_id, after, limit)

    @router.post('/training-jobs/{job_id}/cancel')
    def cancel_training(job_id: str, body: EmptyTrainingAction):
        return training_jobs.cancel(job_id)

    @router.post('/training-jobs/{job_id}/continue', status_code=202)
    def continue_training(job_id: str, body: ContinueTraining):
        return guarded(lambda: training_jobs.resume(job_id, body.job_id))

    @router.get('/training-jobs/{job_id}/partial')
    def partial_training(job_id: str):
        return training_jobs.partial(job_id)

    @router.get('/training-jobs/{job_id}/export')
    def training_diagnostic(job_id: str, kind: Literal['events', 'partial']):
        from fastapi.responses import StreamingResponse
        from spectrumagent.modeling.evaluation import encode
        receipt = training_jobs.status(job_id)
        if kind == 'partial':
            document = {'kind': 'training_diagnostic', 'complete': False, 'receipt': receipt,
                        'partial': training_jobs.partial(job_id)}
            chunks = iter([encode(document).encode('utf-8')])
        else:
            def history():
                yield (encode({'kind': 'training_event_log', 'receipt': receipt, 'through_seq': receipt['event_cursor']})+'\n').encode('utf-8')
                cursor = 0
                while cursor < receipt['event_cursor']:
                    page = training_jobs.events(job_id, cursor, 50)
                    if not page['events']: break
                    for event in page['events']:
                        if event['seq'] <= receipt['event_cursor']:
                            yield (encode(event)+'\n').encode('utf-8')
                    cursor = page['cursor']
            chunks = history()
        return StreamingResponse(chunks, media_type='application/octet-stream')

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
