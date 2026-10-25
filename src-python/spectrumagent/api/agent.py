"""R9/R10 Agent HTTP adapters: preflight failures or finite SSE event streams."""
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from spectrumagent.agent.llm import OpenAICompatibleClient, _json
from spectrumagent.agent.state import AgentStore, StateMachine


class AgentInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CreateSession(AgentInput):
    pass


class ContentMessage(AgentInput):
    content: Annotated[str, Field(min_length=1)]


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


def make_router(database, tools, llm_factory=None):
    router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
    store = AgentStore(database)
    factory = llm_factory or (lambda session_id: OpenAICompatibleClient(database, session_id=session_id))

    @router.post("/sessions")
    def create_session(body: CreateSession):
        return store.create_session()

    @router.post("/sessions/{session_id}/messages", response_class=StreamingResponse,
                 responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}})
    def message(session_id: str, body: ContentMessage | CheckMessage | PlanMessage):
        machine = StateMachine(store, session_id, factory(session_id), tools())
        events = machine.message(**body.model_dump())  # Preflight precedes the response.
        def encode():
            try:
                for event, data in events:
                    yield "event: " + event + "\ndata: " + _json(data) + "\n\n"
            finally:
                events.close()
        return StreamingResponse(encode(), media_type="text/event-stream")

    @router.get("/sessions/{session_id}/steps")
    def steps(session_id: str):
        columns = ("seq", "tool", "status", "arguments_json", "result_digest", "result_summary", "latency_ms", "created_at")
        return {"session_id": session_id, "steps": [{key: row[key] for key in columns} for row in store.steps(session_id)]}

    return router
