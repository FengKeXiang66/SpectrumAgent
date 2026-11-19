"""Strict, independent training-set preview/freeze/read contracts."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from spectrumagent.training_set.store import TrainingSets


def _uuid(value):
    return str(UUID(value))


Identifier = Annotated[StrictStr, AfterValidator(_uuid)]


class TrainingSetModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class TrainingSetMemberInput(TrainingSetModel):
    cube_id: Identifier
    annotation_version_id: Identifier
    recipe_version_id: Identifier


class TrainingSetOptions(TrainingSetModel):
    content_hash_dedup: StrictBool = True


class TrainingSetPreviewRequest(TrainingSetModel):
    members: Annotated[list[TrainingSetMemberInput], Field(min_length=1)]
    options: TrainingSetOptions = Field(default_factory=TrainingSetOptions)
    source_note: Annotated[StrictStr, Field(max_length=2000)] | None = None

    @model_validator(mode='after')
    def unique_cubes(self):
        if len({member.cube_id for member in self.members}) != len(self.members):
            raise ValueError('训练集内每个样品只允许一个标注版本与配方')
        return self


class TrainingSetConfirmRequest(TrainingSetModel):
    version_id: Identifier


class TrainingSetVersion(TrainingSetModel):
    id: StrictStr
    content_hash: StrictStr
    created_at: StrictStr
    actor: Literal['local']
    is_frozen: Literal[0, 1]
    member_count: Annotated[StrictInt, Field(gt=0)]
    label_summary: dict[StrictStr, StrictInt]
    source_note: StrictStr | None
    confirmed_at: StrictStr | None


class TrainingSetGap(TrainingSetMemberInput):
    input_fingerprint: StrictStr


class TrainingSetMember(TrainingSetGap):
    # Reserved for B's sample_label path. A uses pixel annotation snapshots.
    label_id: StrictStr | None
    n_pixels: Annotated[StrictInt, Field(gt=0)]
    preprocess_run_id: StrictStr | None


class TrainingSetMembersResponse(TrainingSetModel):
    version_id: StrictStr
    members: list[TrainingSetMember]
    need_preprocess: list[TrainingSetGap]


class TrainingSetPreviewResponse(TrainingSetVersion, TrainingSetMembersResponse):
    reused: StrictBool
    duplicate_of: StrictStr | None


def make_router(registry, paths, store=None):
    # One store per process: its constructor runs migrations, so app assembly
    # must not create a second copy behind the tool layer's back.
    store = store or TrainingSets(registry, paths)
    router = APIRouter(prefix='/api/v1/training-sets', tags=['training-sets'])

    @router.post('/preview', response_model=TrainingSetPreviewResponse)
    def preview(request: TrainingSetPreviewRequest):
        return store.preview(request.model_dump())

    @router.post('/confirm', response_model=TrainingSetVersion)
    def confirm(request: TrainingSetConfirmRequest):
        return store.confirm(request.version_id)

    @router.get('', response_model=list[TrainingSetVersion])
    def list_versions():
        return store.list_frozen()

    @router.get('/{version_id}/members', response_model=TrainingSetMembersResponse)
    def members(version_id: Identifier):
        return store.resolve_members(version_id)

    return router
