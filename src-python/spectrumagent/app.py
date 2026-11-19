"""Compose new routes around the unchanged foundation app and authentication."""
import secrets
import re
from time import monotonic
from uuid import uuid4
import structlog
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from backend.app import create_app as foundation_app
from spectrumagent.api.datasets import make_router
from spectrumagent.api.recycle import RecycleJobsMiddleware, make_router as make_recycle_router
from spectrumagent.api.annotations import LABEL_PATHS, make_router as make_label_router
from spectrumagent.api.preprocess import make_router as make_preprocess_router
from spectrumagent.api.settings import make_router as make_settings_router
from spectrumagent.api.agent import make_router as make_agent_router
from spectrumagent.api.models import make_router as make_models_router
from spectrumagent.api.dataset_versions import make_router as make_dataset_versions_router
from spectrumagent.api.training_sets import make_router as make_training_sets_router
from spectrumagent.api.experiments import make_router as make_experiments_router
from spectrumagent.experiments.service import ExperimentService
from spectrumagent.dataset_version.store import DatasetVersions
from spectrumagent.agent.llm import OpenAICompatibleClient
from spectrumagent.agent.tools import build_registry
from spectrumagent.agent.skill import ensure_workflow_skill, upgrade_builtin_sessions, _write
from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine
from spectrumagent.annotation.engines.diffusion import DiffusionEngine
from spectrumagent.annotation.session import SessionStore
from spectrumagent.annotation.prepare_batch import BatchPrepareService
from spectrumagent.annotation.segmentation_resources import SegmentationResources
from spectrumagent.data import DataError
from spectrumagent.preprocess.run import RunEngine
from spectrumagent.preprocess.compare import CompareEngine


def publish_agent_workflow(database, registry):
    """Startup self-check: ensure the built-in v2 skill exists and rebind v1 sessions.

    Returns the observable runtime version so callers can report which orchestration
    is actually running instead of inferring it from file timestamps.
    """
    with connect_database(database) as db, _write(db):
        skill = ensure_workflow_skill(db, registry)
        upgrade = upgrade_builtin_sessions(db, registry)
    return {
        "skill_name": skill["name"],
        "skill_version_id": skill["id"],
        "skill_version_no": skill["version_no"],
        "tool_catalogue_version": getattr(registry, "catalogue_version", 1),
        "tool_count": len(registry.snapshot()),
        "sessions_upgraded": upgrade["upgraded"],
    }


def create_app(paths, identity):
    app = foundation_app(paths, identity)
    registry = DatasetRegistry(paths.database)
    dataset_router = make_router(registry)
    app.include_router(dataset_router)
    app.state.dataset_registry = registry
    app.state.recycle = registry.recycle
    app.include_router(make_recycle_router(registry.recycle))
    app.add_middleware(RecycleJobsMiddleware, coordinator=registry.recycle.coordinator, token=identity.token)
    app.include_router(make_settings_router(paths))
    app.state.superpixel_engine = SuperpixelEngine(registry)
    app.state.annotation_sessions = SessionStore(registry, paths)
    app.state.segmentation_resources = SegmentationResources(paths, app.state.superpixel_engine,
                                                            app.state.annotation_sessions)
    app.state.diffusion_engine = DiffusionEngine(app.state.superpixel_engine, app.state.annotation_sessions)
    app.include_router(make_label_router(LabelStore(paths.database), app.state.superpixel_engine,
                                        app.state.annotation_sessions, app.state.diffusion_engine))
    app.state.preprocess_runner = RunEngine(registry, paths)
    from spectrumagent.preprocess.submissions import recover_interrupted
    recover_interrupted(paths.database)
    app.state.preprocess_compare = CompareEngine(app.state.preprocess_runner)
    app.include_router(make_preprocess_router(app.state.preprocess_runner, app.state.preprocess_compare))
    app.include_router(make_models_router(app.state.annotation_sessions, app.state.preprocess_runner, identity.boot_id))
    app.state.experiments = ExperimentService(paths)
    app.include_router(make_experiments_router(app.state.experiments))
    preview_image = next(route.endpoint for route in dataset_router.routes
                         if route.path == '/api/v1/datasets/{identifier}/preview')
    app.state.dataset_versions = DatasetVersions(registry, preview_image=preview_image)
    app.state.annotation_batch = BatchPrepareService(app.state.dataset_versions, app.state.superpixel_engine,
                                                    app.state.annotation_sessions)
    app.include_router(make_dataset_versions_router(app.state.dataset_versions))
    from spectrumagent.training_set.store import TrainingSets
    app.state.training_sets = TrainingSets(registry, paths)
    app.include_router(make_training_sets_router(registry, paths, store=app.state.training_sets))
    from spectrumagent.agent.session_migrations import initialize as initialize_sessions
    from spectrumagent.agent.sessions import SessionService
    initialize_sessions(paths.database)
    app.state.agent_sessions = SessionService(paths.database, app.state.dataset_versions, identity.boot_id)
    from spectrumagent.modeling.run import TrainingRuns
    from spectrumagent.modeling.registry import ModelRegistry
    from spectrumagent.modeling.inference import InferenceRuns
    app.state.training_runs = TrainingRuns(registry, paths)
    app.state.model_registry = ModelRegistry(registry, paths)
    app.state.inference_runs = InferenceRuns(registry, paths)
    app.state.agent_tools = build_registry(datasets=registry, runner=app.state.preprocess_runner,
                                          comparison=app.state.preprocess_compare, database=paths.database,
                                          sessions=app.state.annotation_sessions, diffusion=app.state.diffusion_engine,
                                          catalogue_version=2, batch_prepare=app.state.annotation_batch,
                                          training=app.state.training_runs, models=app.state.model_registry,
                                          inferences=app.state.inference_runs, versions=app.state.dataset_versions,
                                          engine=app.state.superpixel_engine, recycle=registry.recycle,
                                          training_sets=app.state.training_sets, paths=paths)
    app.state.agent_llm_factory = lambda session_id: OpenAICompatibleClient(paths.database, session_id=session_id)
    # Startup self-check: publish the built-in v2 skill and rebind sessions that still
    # hold the built-in v1 skill. Without this the upgrade only happens when a new
    # session is created, so an existing installation keeps running v1 forever.
    app.state.agent_bootstrap = publish_agent_workflow(paths.database, app.state.agent_tools)
    app.include_router(make_agent_router(paths.database, lambda: app.state.agent_tools,
                                        lambda session_id: app.state.agent_llm_factory(session_id),
                                        runtime_info=app.state.agent_bootstrap,
                                        session_service=app.state.agent_sessions,
                                        engine=app.state.superpixel_engine,
                                        annotations=app.state.annotation_sessions,
                                        batch=app.state.annotation_batch))
    original_validation_handler = app.exception_handlers[RequestValidationError]

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        # ServerErrorMiddleware is outside user middleware. Its 500 response
        # otherwise misses dataset_identity and masquerades as a stale engine.
        authenticated = secrets.compare_digest(request.headers.get('authorization','').encode('utf8'),
                                                ('Bearer '+identity.token).encode('ascii'))
        headers = {'X-SpectrumAgent-Boot-Id':identity.boot_id,'X-SpectrumAgent-Pid':str(identity.pid)} if authenticated else {}
        structlog.get_logger(__name__).error('request_failed', error_type=type(error).__name__, method=request.method)
        return JSONResponse({'error':'INTERNAL_ERROR','detail':'本机服务处理请求失败，请核对会话状态；已完成结果保留。','context':{}},
                            status_code=500,headers=headers)

    @app.exception_handler(DataError)
    async def data_error(request, error):
        payload=error.as_dict()
        if request.url.path.startswith('/api/v1/preprocess') or '/preprocess/' in request.url.path:
            from spectrumagent.data.validation import public_error
            payload=public_error(error)
        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            return JSONResponse(payload, status_code=status_code)
        if request.url.path in LABEL_PATHS:
            return JSONResponse(error.as_dict(), status_code=422)
        return JSONResponse(payload, status_code=404 if error.code == "DATASET_NOT_FOUND" else 400)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith("/api/v1/experiments"):
            return JSONResponse(DataError("INVALID_REQUEST", "实验配置不合法",
                                fields=[".".join(map(str, e["loc"])) for e in error.errors()]).as_dict(), status_code=400)
        if request.url.path.startswith('/api/v1/preprocess') or '/preprocess/' in request.url.path:
            from spectrumagent.data.validation import field_errors
            return JSONResponse(DataError('INVALID_REQUEST','预处理请求参数不合法',fields=field_errors(error)).as_dict(),status_code=400)
        if request.url.path.startswith("/api/v1/models"):
            return JSONResponse(DataError("INVALID_REQUEST", "建模请求参数不合法").as_dict(), status_code=400)
        if request.url.path.startswith("/api/v1/annotations/"):
            return JSONResponse(DataError("TOOL_ARGS_INVALID", "草稿请求参数不合法").as_dict(), status_code=400)
        if request.url.path.startswith("/api/v1/settings") or request.url.path.startswith("/api/v1/agent"):
            # Validation errors may contain a submitted key, even in extra fields
            # or malformed JSON. Never echo inputs through the foundation handler.
            return JSONResponse(DataError("INVALID_REQUEST", "请求参数不合法").as_dict(), status_code=400)
        if request.url.path in LABEL_PATHS:
            fields = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]
            return JSONResponse(DataError("INVALID_LABEL", "标签登记参数不合法", fields=fields).as_dict(), status_code=422)
        if request.url.path.startswith("/api/v1/datasets") or request.url.path.startswith("/api/v1/preprocess") or request.url.path.startswith("/api/v1/batch-deletions") or request.url.path.startswith("/api/v1/dataset-versions"):
            if (request.url.path.endswith("/annotations/save")
                    and any(e["loc"] == ("body", "note") for e in error.errors())):
                return JSONResponse(DataError("INVALID_VERSION_NOTE", "版本备注须为不超过 2000 字符的文本").as_dict(), status_code=400)
            return JSONResponse(DataError("INVALID_REQUEST", "数据接入请求参数不合法", fields=[".".join(map(str, e["loc"])) for e in error.errors()]).as_dict(), status_code=400)
        return await original_validation_handler(request, error)

    @app.middleware("http")
    async def dataset_identity(request, call_next):
        model_request = request.url.path.startswith("/api/v1/models")
        trace = request.headers.get("X-SpectrumAgent-Request-Id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", trace):
            trace = str(uuid4())
        started = monotonic()
        logger = structlog.get_logger("engine.model_transport")
        if model_request:
            logger.info("model_request_enter", request_id=trace, method=request.method, boot_id=identity.boot_id)
        try:
            response = await call_next(request)
        except BaseException:
            if model_request:
                logger.warning("model_request_aborted", request_id=trace, elapsed_ms=round((monotonic()-started)*1000))
            raise
        if model_request:
            response.headers["X-SpectrumAgent-Request-Id"] = trace
            logger.info("model_request_exit", request_id=trace, status=response.status_code,
                        elapsed_ms=round((monotonic()-started)*1000))
        if (request.url.path in LABEL_PATHS or request.url.path == "/api/v1/datasets" or request.url.path.startswith("/api/v1/datasets/") or request.url.path.startswith("/api/v1/preprocess") or request.url.path.startswith("/api/v1/settings") or request.url.path.startswith("/api/v1/agent") or request.url.path.startswith("/api/v1/annotations/") or request.url.path.startswith("/api/v1/models") or request.url.path.startswith("/api/v1/batch-deletions") or request.url.path.startswith("/api/v1/dataset-versions") or request.url.path.startswith("/api/v1/training-sets") or request.url.path.startswith("/api/v1/experiments")) and response.status_code != 401:
            response.headers["X-SpectrumAgent-Boot-Id"] = identity.boot_id
            response.headers["X-SpectrumAgent-Pid"] = str(identity.pid)
        return response

    return app
