"""Compose new routes around the unchanged foundation app and authentication."""
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from backend.app import create_app as foundation_app
from spectrumagent.api.datasets import make_router
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError


def create_app(paths, identity):
    app = foundation_app(paths, identity)
    app.include_router(make_router(DatasetRegistry(paths.database)))
    original_validation_handler = app.exception_handlers[RequestValidationError]

    @app.exception_handler(DataError)
    async def data_error(request, error):
        return JSONResponse(error.as_dict(), status_code=404 if error.code == "DATASET_NOT_FOUND" else 400)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith("/api/v1/datasets"):
            return JSONResponse(DataError("INVALID_REQUEST", "数据接入请求参数不合法", fields=[".".join(map(str, e["loc"])) for e in error.errors()]).as_dict(), status_code=400)
        return await original_validation_handler(request, error)

    @app.middleware("http")
    async def dataset_identity(request, call_next):
        response = await call_next(request)
        if (request.url.path == "/api/v1/datasets" or request.url.path.startswith("/api/v1/datasets/")) and response.status_code != 401:
            response.headers["X-SpectrumAgent-Boot-Id"] = identity.boot_id
            response.headers["X-SpectrumAgent-Pid"] = str(identity.pid)
        return response

    return app
