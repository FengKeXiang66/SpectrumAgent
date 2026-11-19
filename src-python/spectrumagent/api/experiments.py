"""Synchronous numerical entry point; orchestration can call the same service."""
from fastapi import APIRouter
from fastapi.responses import FileResponse

from spectrumagent.experiments.schema import ExperimentConfig
from spectrumagent.experiments.service import ExperimentService


def make_router(service: ExperimentService):
    router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

    @router.get("/schema")
    def schema():
        return ExperimentConfig.model_json_schema()

    @router.post("/run")
    def run(body: ExperimentConfig):
        return service.run(body)

    @router.get("/{identifier}")
    def get(identifier: str):
        return service.get(identifier)

    @router.get("/{identifier}/artifacts/{name}")
    def artifact(identifier: str, name: str):
        return FileResponse(service.artifact(identifier, name), filename=name, content_disposition_type="inline")

    return router
