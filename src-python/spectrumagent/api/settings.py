"""Non-sensitive LLM settings and a write-only process-memory credential."""
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, SecretStr

from spectrumagent.agent.llm import LLMSettings, has_api_key, read_settings, set_api_key, write_settings
from spectrumagent.api.project_paths import install_project_paths


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    key: SecretStr


def make_router(paths):
    database = paths.database
    router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
    install_project_paths(router, paths)

    def current():
        return {**read_settings(database).model_dump(), "has_key": has_api_key()}

    @router.get("/llm")
    def get_llm():
        return current()

    @router.put("/llm")
    def put_llm(request: LLMSettings):
        write_settings(database, request)
        return current()

    @router.put("/llm/key")
    def put_key(request: KeyRequest):
        set_api_key(request.key.get_secret_value())
        return {"has_key": has_api_key()}

    return router
