"""Human-confirmed permanent deletion contracts; no agent tool can execute deletion."""
from typing import Annotated
from uuid import UUID
import secrets

from fastapi import APIRouter
from pydantic import ConfigDict, Field, StrictBool, StrictStr
from starlette.responses import JSONResponse

from spectrumagent.data import DataError

from .schemas import Envelope


class DeleteRequest(Envelope):
    confirm: StrictBool
    preview_token: Annotated[str, Field(min_length=1, max_length=2048)]


class BatchPreviewRequest(Envelope):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_ids: Annotated[list[StrictStr], Field(min_length=1)]


class BatchDeleteRequest(Envelope):
    model_config = ConfigDict(extra="forbid", strict=True)
    cube_ids: Annotated[list[StrictStr], Field(min_length=1)]
    confirm: StrictBool
    preview_token: Annotated[StrictStr, Field(min_length=1)]


class RecycleJobsMiddleware:
    """Keep the task lease until the complete response, including agent SSE, ends."""
    def __init__(self, app, *, coordinator, token):
        self.app, self.coordinator, self.token = app, coordinator, ('Bearer ' + token).encode()

    async def __call__(self, scope, receive, send):
        path = scope.get('path', '')
        authorization = dict(scope.get('headers', [])).get(b'authorization', b'')
        maintenance = path.endswith('/delete')
        if (scope['type'] != 'http' or not path.startswith('/api/v1/') or maintenance
                or not secrets.compare_digest(authorization, self.token)):
            return await self.app(scope, receive, send)
        lease = self.coordinator.job()
        try:
            lease.__enter__()
        except DataError as error:
            response = JSONResponse(error.as_dict(), status_code=error.status_code)
            return await response(scope, receive, send)
        try:
            return await self.app(scope, receive, send)
        finally:
            lease.__exit__(None, None, None)


def make_router(store):
    router = APIRouter(tags=['deletion'])

    @router.post('/api/v1/batch-deletions/preview')
    def preview_batch(request: BatchPreviewRequest):
        return store.preview_batch(**request.model_dump())

    @router.post('/api/v1/batch-deletions/delete')
    def delete_batch(request: BatchDeleteRequest):
        return store.delete_batch(**request.model_dump())

    @router.get('/api/v1/datasets/{identifier}/delete/preview')
    def preview(identifier: UUID):
        return store.preview(identifier)

    @router.post('/api/v1/datasets/{identifier}/delete')
    def delete(identifier: UUID, request: DeleteRequest):
        return store.delete(identifier, **request.model_dump())

    return router
