"""10.1 only: projects, structured labels and the read-only plastic catalog."""
from fastapi import APIRouter

from spectrumagent.annotation.labels import LabelRequest, LabelStore, plastic_catalog


LABEL_PATHS = {"/api/v1/projects", "/api/v1/labels", "/api/v1/catalog/plastic"}


def make_router(store: LabelStore):
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

    return router
