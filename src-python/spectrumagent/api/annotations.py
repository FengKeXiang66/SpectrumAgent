"""Projects/labels and the 10.2 superpixel endpoint; no annotation session."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from spectrumagent.annotation.labels import LabelRequest, LabelStore, plastic_catalog
from spectrumagent.annotation.engines.superpixels import DEFAULT_COMPACTNESS, Parameters, SuperpixelEngine


LABEL_PATHS = {"/api/v1/projects", "/api/v1/labels", "/api/v1/catalog/plastic"}


class SuperpixelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n_segments: Annotated[int, Field(strict=True, gt=0)] = 800
    compactness: Annotated[float, Field(gt=0, allow_inf_nan=False)] = DEFAULT_COMPACTNESS
    pca_components: Annotated[int, Field(strict=True, gt=0)] = 5
    force: StrictBool = False


def make_router(store: LabelStore, engine: SuperpixelEngine):
    router = APIRouter(prefix="/api/v1", tags=["annotation labels"])

    @router.get("/projects")
    def projects():
        return store.projects()

    @router.get("/labels")
    def labels(project_id: str):
        return store.tree(project_id)

    @router.post("/labels", status_code=201)
    def add_label(request: LabelRequest):
        return store.add(request)

    @router.get("/catalog/plastic")
    def catalog():
        return plastic_catalog()

    @router.post("/datasets/{identifier}/superpixels")
    def superpixels(identifier: UUID, request: SuperpixelRequest):
        params = Parameters(n_segments=request.n_segments, compactness=request.compactness,
                            pca_components=request.pca_components)
        return engine.generate(identifier, params, force=request.force).report

    return router
