"""Version-free desktop entry points."""
from uuid import UUID
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from spectrumagent.preprocess.schema import Pipeline
from spectrumagent.preprocess.current import CurrentWorkspace
from .preprocess import store_call


class RecipeUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pipeline: Pipeline


class ProcessInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recipe_id: UUID


def make_router(sessions, runner):
    workspace = CurrentWorkspace(sessions, runner)
    router = APIRouter(prefix='/api/v1/preprocess/current', tags=['current workspace'])

    @router.get('')
    def state():
        return workspace.state()

    @router.put('/recipes/{recipe_id}')
    def update_recipe(recipe_id: UUID, body: RecipeUpdate):
        store_call(runner.recipes.update_current, recipe_id, body.pipeline.model_dump())
        return workspace.state()

    @router.post('/datasets/{cube_id}/run')
    def process(cube_id: UUID, body: ProcessInput):
        return store_call(workspace.process, cube_id, body.recipe_id)

    return router
