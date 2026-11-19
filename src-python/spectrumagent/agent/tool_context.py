"""Request-local server identity, never an argument offered to the model."""
from contextvars import ContextVar

owner_session = ContextVar('tool_owner_session', default=None)
