"""R9/R10 Agent HTTP adapters: preflight failures or finite SSE event streams."""
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from spectrumagent.agent.llm import OpenAICompatibleClient, _json
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.skill import active_skill, ensure_workflow_skill, _write
from backend.database import connect_database


class AgentInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CreateSession(AgentInput):
    pass


class Workspace(AgentInput):
    cube_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
    gesture_ref: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")] | None = None


class ContentMessage(AgentInput):
    content: Annotated[str, Field(min_length=1)]
    workspace: Workspace | None = None


class CheckMessage(AgentInput):
    check_id: Annotated[str, Field(min_length=1)]
    decision: Literal["approve", "reject"]


class PlanApproval(AgentInput):
    plan_id: Annotated[str, Field(min_length=1)]
    action: Literal["approve"]


class PlanRejection(AgentInput):
    plan_id: Annotated[str, Field(min_length=1)]
    action: Literal["reject"]
    reason: Annotated[str, Field(min_length=1)]


class PlanChange(AgentInput):
    plan_id: Annotated[str, Field(min_length=1)]
    action: Literal["skip", "rollback"]
    step_ref: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1)]


PlanMessage = Annotated[PlanApproval | PlanRejection | PlanChange, Field(discriminator="action")]


def make_router(database, tools, llm_factory=None, runtime_info=None):
    router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
    store = AgentStore(database)
    factory = llm_factory or (lambda session_id: OpenAICompatibleClient(database, session_id=session_id))

    def describe_runtime(registry):
        """Report which orchestration is actually running, not a guessed version."""
        info = dict(runtime_info or {})
        info.setdefault("tool_catalogue_version", getattr(registry, "catalogue_version", 1))
        info.setdefault("tool_count", len(registry.snapshot()))
        return info

    @router.post("/sessions")
    def create_session(body: CreateSession):
        registry = tools()
        if getattr(registry, "catalogue_version", 1) == 2:
            try:
                with connect_database(database) as db, _write(db):
                    ensure_workflow_skill(db, registry)
            except Exception as error:
                if getattr(error, "code", None) == "SKILL_NOT_ACTIVE":
                    error.status_code = 409
                raise
        session = store.create_session()
        with connect_database(database) as db:
            skill = active_skill(db)
        session["skill_name"] = skill["name"]
        session["skill_version_no"] = skill["version_no"]
        session["runtime"] = describe_runtime(registry)
        return session

    @router.post("/sessions/{session_id}/messages", response_class=StreamingResponse,
                 responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}})
    def message(session_id: str, body: ContentMessage | CheckMessage | PlanMessage):
        machine = StateMachine(store, session_id, factory(session_id), tools())
        events = machine.message(**body.model_dump(exclude_none=True))  # Preflight precedes the response.
        def encode():
            try:
                for event, data in events:
                    yield "event: " + event + "\ndata: " + _json(data) + "\n\n"
            finally:
                events.close()
        return StreamingResponse(encode(), media_type="text/event-stream")

    @router.get("/runtime")
    def runtime():
        """Observable runtime version of the orchestration actually in use."""
        registry = tools()
        with connect_database(database) as db:
            try:
                skill = active_skill(db)
            except Exception:
                skill = {"name": None, "id": None, "version_no": None}
            sessions = db.execute(
                "SELECT s.id, v.name FROM agent_session s JOIN skill_version v ON v.id=s.skill_version_id"
            ).fetchall()
        by_skill = {}
        for _identifier, name in sessions:
            by_skill[name] = by_skill.get(name, 0) + 1
        info = describe_runtime(registry)
        info.update({
            "skill_name": skill["name"],
            "skill_version_id": skill["id"],
            "skill_version_no": skill["version_no"],
            "sessions_by_skill": by_skill,
        })
        return info

    @router.get("/sessions/{session_id}/steps")
    def steps(session_id: str):
        columns = ("seq", "tool", "status", "arguments_json", "result_digest", "result_summary", "latency_ms", "created_at")
        return {"session_id": session_id, "steps": [{key: row[key] for key in columns} for row in store.steps(session_id)]}

    return router
