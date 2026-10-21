"""Compose new routes around the unchanged foundation app and authentication."""
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from backend.app import create_app as foundation_app
from spectrumagent.api.datasets import make_router
from spectrumagent.api.annotations import LABEL_PATHS, make_router as make_label_router
from spectrumagent.api.preprocess import make_router as make_preprocess_router
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.labels import LabelStore
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine
from spectrumagent.annotation.engines.diffusion import DiffusionEngine
from spectrumagent.annotation.session import SessionStore
from spectrumagent.data import DataError
from spectrumagent.preprocess.run import RunEngine
from spectrumagent.preprocess.compare import CompareEngine


def create_app(paths, identity):
    app = foundation_app(paths, identity)
    registry = DatasetRegistry(paths.database)
    app.include_router(make_router(registry))
    app.state.superpixel_engine = SuperpixelEngine(registry)
    app.state.annotation_sessions = SessionStore(registry, paths)
    app.state.diffusion_engine = DiffusionEngine(app.state.superpixel_engine, app.state.annotation_sessions)
    app.include_router(make_label_router(LabelStore(paths.database), app.state.superpixel_engine,
                                        app.state.annotation_sessions, app.state.diffusion_engine))
    app.state.preprocess_runner = RunEngine(registry, paths)
    app.state.preprocess_compare = CompareEngine(app.state.preprocess_runner)
    app.include_router(make_preprocess_router(app.state.preprocess_runner, app.state.preprocess_compare))
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
        if request.url.path in LABEL_PATHS:
            fields = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]
            return JSONResponse(DataError("INVALID_LABEL", "标签登记参数不合法", fields=fields).as_dict(), status_code=422)
        if request.url.path.startswith("/api/v1/datasets") or request.url.path.startswith("/api/v1/preprocess"):
            if (request.url.path.endswith("/annotations/save")
                    and any(e["loc"] == ("body", "note") for e in error.errors())):
                return JSONResponse(DataError("INVALID_VERSION_NOTE", "版本备注须为不超过 2000 字符的文本").as_dict(), status_code=400)
            return JSONResponse(DataError("INVALID_REQUEST", "数据接入请求参数不合法", fields=[".".join(map(str, e["loc"])) for e in error.errors()]).as_dict(), status_code=400)
        return await original_validation_handler(request, error)

    @app.middleware("http")
    async def dataset_identity(request, call_next):
        response = await call_next(request)
        if (request.url.path in LABEL_PATHS or request.url.path == "/api/v1/datasets" or request.url.path.startswith("/api/v1/datasets/") or request.url.path.startswith("/api/v1/preprocess")) and response.status_code != 401:
            response.headers["X-SpectrumAgent-Boot-Id"] = identity.boot_id
            response.headers["X-SpectrumAgent-Pid"] = str(identity.pid)
        return response

    return app
