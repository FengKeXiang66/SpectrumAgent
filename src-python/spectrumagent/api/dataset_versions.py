"""Strict independent contracts for batch preview, confirmation and frozen reads."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

from spectrumagent.data import DataError


class VersionModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class DatasetVersionOptions(VersionModel):
    content_hash_dedup: StrictBool = True
    preview_downsample: StrictBool = True


class DatasetVersionPreviewRequest(VersionModel):
    cube_ids: Annotated[list[StrictStr], Field(min_length=1)]
    options: DatasetVersionOptions | None = None


class DatasetVersionConfirmRequest(VersionModel):
    version_id: UUID

    @field_validator('version_id', mode='before')
    @classmethod
    def json_uuid(cls, value):
        # FastAPI validates parsed JSON as Python input; UUID's strict mode
        # otherwise rejects even the canonical JSON string representation.
        return UUID(value) if isinstance(value, str) else value


class DatasetVersionFileReport(VersionModel):
    path: str
    status: Literal['通过', '告警', '阻断']
    wavelength_axis: list[float]
    bit_depth: int
    bytes: int
    warnings: list[str]


class DatasetVersionPreviewResponse(VersionModel):
    version_id: str
    reused: bool
    duplicate_of: str | None
    cube_count: int
    content_hash: str
    items: list[DatasetVersionFileReport]
    warnings: list[str]
    blocked: bool


class DatasetVersionConfirmResponse(VersionModel):
    dataset_version_id: str
    cube_ids: list[str]
    content_hash: str
    created_at: str
    actor: Literal['local']
    is_frozen: Literal[1]
    confirmed_at: str
    reused: bool


class DatasetVersionListItem(VersionModel):
    id: str
    content_hash: str
    cube_count: int
    created_at: str
    confirmed_at: str
    cube_ids: list[str]
    is_frozen: Literal[1]


def make_router(store):
    router = APIRouter(prefix='/api/v1/dataset-versions', tags=['dataset-versions'])

    @router.post('/preview', response_model=DatasetVersionPreviewResponse)
    def preview(request: DatasetVersionPreviewRequest):
        return store.preview(request.cube_ids, request.options.model_dump() if request.options else None)

    @router.post('/confirm', response_model=DatasetVersionConfirmResponse)
    def confirm(request: DatasetVersionConfirmRequest):
        return store.confirm(request.version_id)

    @router.get('', response_model=list[DatasetVersionListItem])
    def list_versions(frozen: bool = True):
        if not frozen:
            raise DataError('INVALID_REQUEST', '只支持列出已冻结数据集版本', frozen=frozen)
        return store.list_frozen()

    return router
