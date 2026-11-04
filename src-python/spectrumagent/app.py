"""Compose new routes around the unchanged foundation app and authentication."""
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
from spectrumagent.agent.llm import OpenAICompatibleClient
from spectrumagent.agent.tools import build_registry
from spectrumagent.agent.skill import ensure_workflow_skill, upgrade_builtin_sessions, _write
from backend.database import connect_database
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine
from spectrumagent.annotation.engines.diffusion import DiffusionEngine
from spectrumagent.annotation.session import SessionStore
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
    app.include_router(make_router(registry))
    app.state.dataset_registry = registry
    app.state.recycle = registry.recycle
    app.include_router(make_recycle_router(registry.recycle))
    app.add_middleware(RecycleJobsMiddleware, coordinator=registry.recycle.coordinator, token=identity.token)
    app.include_router(make_settings_router(paths.database))
    app.state.superpixel_engine = SuperpixelEngine(registry)
    app.state.annotation_sessions = SessionStore(registry, paths)
    app.state.diffusion_engine = DiffusionEngine(app.state.superpixel_engine, app.state.annotation_sessions)
    app.include_router(make_label_router(LabelStore(paths.database), app.state.superpixel_engine,
                                        app.state.annotation_sessions, app.state.diffusion_engine))
    app.state.preprocess_runner = RunEngine(registry, paths)
    app.state.preprocess_compare = CompareEngine(app.state.preprocess_runner)
    app.include_router(make_preprocess_router(app.state.preprocess_runner, app.state.preprocess_compare))
    app.include_router(make_models_router(app.state.annotation_sessions, app.state.preprocess_runner))
    app.state.agent_tools = build_registry(datasets=registry, runner=app.state.preprocess_runner,
                                          comparison=app.state.preprocess_compare, database=paths.database,
                                          sessions=app.state.annotation_sessions, diffusion=app.state.diffusion_engine,
                                          catalogue_version=2)
    app.state.agent_llm_factory = lambda session_id: OpenAICompatibleClient(paths.database, session_id=session_id)
    # Startup self-check: publish the built-in v2 skill and rebind sessions that still
    # hold the built-in v1 skill. Without this the upgrade only happens when a new
    # session is created, so an existing installation keeps running v1 forever.
    app.state.agent_bootstrap = publish_agent_workflow(paths.database, app.state.agent_tools)
    app.include_router(make_agent_router(paths.database, lambda: app.state.agent_tools,
                                        lambda session_id: app.state.agent_llm_factory(session_id),
                                        runtime_info=app.state.agent_bootstrap))
    original_validation_handler = app.exception_handlers[RequestValidationError]

    @app.exception_handler(DataError)
    async def data_error(request, error):
        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            return JSONResponse(error.as_dict(), status_code=status_code)
        if request.url.path in LABEL_PATHS:
            return JSONResponse(error.as_dict(), status_code=422)
        return JSONResponse(error.as_dict(), status_code=404 if error.code == "DATASET_NOT_FOUND" else 400)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
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
        if request.url.path.startswith("/api/v1/datasets") or request.url.path.startswith("/api/v1/preprocess") or request.url.path.startswith('/api/v1/recycle'):
            if (request.url.path.endswith("/annotations/save")
                    and any(e["loc"] == ("body", "note") for e in error.errors())):
                return JSONResponse(DataError("INVALID_VERSION_NOTE", "版本备注须为不超过 2000 字符的文本").as_dict(), status_code=400)
            return JSONResponse(DataError("INVALID_REQUEST", "数据接入请求参数不合法", fields=[".".join(map(str, e["loc"])) for e in error.errors()]).as_dict(), status_code=400)
        return await original_validation_handler(request, error)

    @app.middleware("http")
    async def dataset_identity(request, call_next):
        response = await call_next(request)
        if (request.url.path in LABEL_PATHS or request.url.path == "/api/v1/datasets" or request.url.path.startswith("/api/v1/datasets/") or request.url.path.startswith('/api/v1/recycle') or request.url.path.startswith("/api/v1/preprocess") or request.url.path.startswith("/api/v1/settings") or request.url.path.startswith("/api/v1/agent") or request.url.path.startswith("/api/v1/annotations/") or request.url.path.startswith("/api/v1/models")) and response.status_code != 401:
            response.headers["X-SpectrumAgent-Boot-Id"] = identity.boot_id
            response.headers["X-SpectrumAgent-Pid"] = str(identity.pid)
        return response

    return app
