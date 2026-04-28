from pydantic import BaseModel
from typing import Literal
from semant_demo.schemas import TagSpan


class SuggestSpansRequest(BaseModel):
    """Request body for AI span suggestion endpoints."""
    collection_id: str
    document_id: str
    tag_ids: list[str]


class SuggestSpansChunkResult(BaseModel):
    """
    One NDJSON event emitted while AI suggestions are being generated.

    Frontend can use this to progressively render auto spans as each chunk
    finishes processing.
    """
    chunk_id: str
    """ID of the chunk that was just processed."""

    spans: list[TagSpan]
    """Auto-typed spans newly persisted in the database for this chunk."""

    error: str | None = None
    """Set if processing this chunk failed; ``spans`` will be empty."""


class DeleteAutoSpansRequest(BaseModel):
    """
    Request body for bulk deletion of unresolved AI proposals
    (``type == auto``) within a single (collection, document) scope.
    """
    collection_id: str
    document_id: str
    tag_ids: list[str]


class DeleteAutoSpansResponse(BaseModel):
    """Result of a bulk auto-span deletion."""
    deleted: int


class SpanChatMessage(BaseModel):
    """One message in a span-discussion chat history."""
    role: Literal["user", "assistant"]
    content: str


class DiscussSpanRequest(BaseModel):
    """
    Request body for ``POST /api/ai/discuss_span``.

    The frontend sends the full chat history each call (the new user turn is
    the last message). The backend resolves span / document / tag / chunk
    context server-side and prepends it as a system message.
    """
    span_id: str
    collection_id: str
    messages: list[SpanChatMessage]


class SpanChatDelta(BaseModel):
    """One NDJSON event streamed back during a span discussion."""
    delta: str | None = None
    done: bool | None = None
    error: str | None = None

