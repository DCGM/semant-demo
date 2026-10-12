"""Identity of the HTTP request being served, for correlating its structured logs."""
from contextvars import ContextVar

current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)
"""Set by ``RequestTelemetryMiddleware`` for the duration of each request."""
