"""Shared, JSON-safe failures for models, readers, and HTTP adapters."""
from pydantic import BaseModel, ConfigDict, JsonValue


class DataErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str
    detail: str
    context: dict[str, JsonValue]


class DataError(Exception):
    def __init__(self, code: str, detail: str, **context: JsonValue):
        self.payload = DataErrorPayload(error=code, detail=detail, context=context)
        super().__init__(detail)

    @property
    def code(self) -> str:
        return self.payload.error

    def as_dict(self) -> dict:
        return self.payload.model_dump(mode="json")
