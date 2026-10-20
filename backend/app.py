"""HTTP contract: public health; Bearer authentication for everything else."""

import asyncio
import secrets
from contextlib import asynccontextmanager, suppress
from threading import Event

import structlog
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.identity import EngineIdentity
from backend.database import open_database
from backend.handshake import remove_if_owned
from backend.paths import AppPaths
from backend.smoke import ensure_sample, run_smoke

log = structlog.get_logger("engine.http")


def create_app(paths: AppPaths, identity: EngineIdentity) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        paths.create_directories()
        connection = open_database(paths.database)
        connection.execute("PRAGMA journal_mode=WAL")
        app.state.database = connection  # Shared connection for the application lifetime.
        try:
            app.state.sample = await asyncio.to_thread(ensure_sample, paths.testdata)
            yield
        finally:
            try:
                connection.close()
            finally:
                remove_if_owned(paths.handshake, identity.boot_id, phase="lifespan")

    async def authenticate(request: Request, call_next):
        if request.url.path != "/health":
            expected = f"Bearer {identity.token}".encode("ascii")
            supplied = request.headers.get("authorization", "").encode("utf-8")
            if not secrets.compare_digest(supplied, expected):
                log.warning("authentication_rejected", path=request.url.path)
                return JSONResponse(
                    {"error": "UNAUTHORIZED", "detail": "需要本次引擎握手中的 Bearer token。"},
                    status_code=401, headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    async def inject_smoke_identity(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/smoke":
            response.headers["X-SpectrumAgent-Boot-Id"] = identity.boot_id
            response.headers["X-SpectrumAgent-Pid"] = str(identity.pid)
        return response

    # Explicit outer-to-inner order: rejected authentication never reaches injection.
    app = FastAPI(
        title="SpectrumAgent foundation", version="0.1.0", lifespan=lifespan,
        docs_url=None, redoc_url=None, openapi_url=None,
        middleware=[
            Middleware(BaseHTTPMiddleware, dispatch=authenticate),
            Middleware(BaseHTTPMiddleware, dispatch=inject_smoke_identity),
        ],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"error": "INVALID_REQUEST", "detail": str(exc)}, status_code=422
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": "HTTP_ERROR", "detail": str(exc.detail)}, status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.get("/health")
    async def health():
        return identity.health()

    @app.get("/smoke")
    async def smoke(request: Request, blocks: int = Query(default=1, ge=1, le=64)):
        cancellation = Event()

        async def observe_disconnect():
            while not cancellation.is_set():
                if await request.is_disconnected():
                    cancellation.set()
                    return
                await asyncio.sleep(0.01)

        observer = asyncio.create_task(observe_disconnect())
        try:
            result = await run_smoke(request.app.state.sample, blocks, cancellation)
            if result.cancelled:
                log.info("smoke_cancelled", completed_blocks=result.completed_blocks, blocks=blocks)
                return JSONResponse(result.cancelled_payload(), status_code=409)
            log.info("smoke_completed", blocks=blocks, **result.metrics)
            return result.metrics
        except asyncio.CancelledError:
            cancellation.set()
            raise
        except Exception:
            log.exception("smoke_failed")
            return JSONResponse(
                {"error": "SMOKE_FAILED", "detail": "ENVI/SNV 冒烟失败，请查看引擎日志。"},
                status_code=500,
            )
        finally:
            cancellation.set()
            observer.cancel()
            with suppress(asyncio.CancelledError):
                await observer

    return app
