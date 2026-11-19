"""Runtime recipe editing through the same service used by conversational tools."""
from typing import Annotated
from uuid import UUID

from fastapi import Header
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from spectrumagent.preprocess import submissions
from .preprocess import BatchItem, store_call


class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)


class DraftStep(DraftInput):
    op: str
    version: Annotated[int,Field(gt=0)]
    params: dict[str,JsonValue]


class DraftPipeline(DraftInput):
    steps: Annotated[list[DraftStep],Field(max_length=30)]


class DraftCreate(DraftInput):
    source_recipe_version_id: str | None = None
    new_plan: bool = False


class DraftUpdate(DraftInput):
    expected_revision: Annotated[int,Field(gt=0)]
    pipeline: DraftPipeline | None = None
    metadata: dict[str,str] | None = None


class DraftSave(DraftInput):
    expected_revision: Annotated[int,Field(gt=0)]
    recipe_id: str | None = None
    code: Annotated[str,Field(min_length=1,max_length=64)] | None = None
    name: Annotated[str,Field(min_length=1,max_length=80)] | None = None
    description: Annotated[str,Field(max_length=2000)] | None = None
    note: Annotated[str,Field(max_length=2000)] | None = None


class DraftConfirm(DraftInput):
    expected_revision: Annotated[int,Field(gt=0)]
    recipe_version_id: str
    inputs: Annotated[list[BatchItem],Field(min_length=1,max_length=32)]


class DraftExecute(DraftInput):
    confirmation_id: str
    inputs: Annotated[list[BatchItem],Field(min_length=1,max_length=32)]


class DraftRetry(DraftExecute):
    retry_of_submission: Annotated[str,Field(pattern=r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$')]


def add_draft_routes(router,runner):
    drafts = runner.drafts

    @router.get('/preprocess/sessions/{session_id}/drafts/current')
    def current(session_id: UUID):
        return drafts.get(str(session_id))

    @router.post('/preprocess/sessions/{session_id}/drafts')
    def create(session_id: UUID,body:DraftCreate):
        return drafts.create(str(session_id),**body.model_dump())

    @router.get('/preprocess/sessions/{session_id}/drafts/{draft_id}')
    def get(session_id:UUID,draft_id:UUID):
        return drafts.get(str(session_id),str(draft_id))

    @router.put('/preprocess/sessions/{session_id}/drafts/{draft_id}')
    def update(session_id:UUID,draft_id:UUID,body:DraftUpdate):
        return drafts.update(str(session_id),str(draft_id),body.expected_revision,
                             body.pipeline.model_dump() if body.pipeline else None,body.metadata)

    @router.post('/preprocess/sessions/{session_id}/drafts/{draft_id}/save')
    def save(session_id:UUID,draft_id:UUID,body:DraftSave,
             reference:Annotated[UUID|None,Header(alias='X-Submission-Ref')]=None):
        with submissions.execution_context(submissions.explicit_submission(str(reference) if reference else None,
                                                                          owner=str(session_id),source='ui_save')):
            return store_call(drafts.save,str(session_id),str(draft_id),**body.model_dump())

    @router.post('/preprocess/sessions/{session_id}/drafts/{draft_id}/confirm')
    def confirm(session_id:UUID,draft_id:UUID,body:DraftConfirm):
        return drafts.confirm(str(session_id),str(draft_id),body.expected_revision,body.recipe_version_id,
                              body.model_dump(mode='json')['inputs'],'ui_execute')

    @router.post('/preprocess/sessions/{session_id}/drafts/execute')
    def execute(session_id:UUID,body:DraftExecute,
                reference:Annotated[UUID|None,Header(alias='X-Submission-Ref')]=None):
        with submissions.execution_context(submissions.explicit_submission(str(reference) if reference else None,
                                                                          owner=str(session_id),source='ui_execute')):
            return drafts.execute(runner,str(session_id),body.confirmation_id,body.model_dump(mode='json')['inputs'])

    @router.post('/preprocess/sessions/{session_id}/drafts/retry')
    def retry(session_id:UUID,body:DraftRetry,
              reference:Annotated[UUID,Header(alias='X-Submission-Ref')]):
        with submissions.execution_context(submissions.explicit_submission(str(reference),owner=str(session_id),source='ui_retry')):
            return drafts.retry(runner,str(session_id),body.confirmation_id,body.model_dump(mode='json')['inputs'],body.retry_of_submission)

    @router.delete('/preprocess/recipes/{recipe_id}')
    def delete(recipe_id:UUID):
        return store_call(runner.recipes.set_deleted,str(recipe_id),True)

    @router.post('/preprocess/recipes/{recipe_id}/restore')
    def restore(recipe_id:UUID):
        return store_call(runner.recipes.set_deleted,str(recipe_id),False)
