from pydantic import BaseModel
from typing import Literal
from semant_demo.schemas import TagSpan


class SuggestSpansRequest(BaseModel):
    """Request body for AI span suggestion endpoints."""
    collection_id: str
    document_id: str
    tag_ids: list[str]


class SuggestSpansSelectionRequest(BaseModel):
    """
    Request body for ``POST /api/ai/suggest_spans/selection``.

    The user has highlighted a passage and asked the AI to propose tags
    for *only that passage*. The selection may span multiple consecutive
    chunks; the frontend sends the chunk IDs in document order. Offsets
    are measured against the concatenation of those chunks' text:

    - ``selection_start`` — char offset measured from the start of the
      first chunk (so it is also the local offset inside that chunk).
    - ``selection_end`` — char offset across the concatenation (may
      exceed the first chunk's length when the selection extends into
      later chunks).

    Resulting auto spans are anchored on the first chunk in
    ``chunk_ids`` with ``start`` / ``end`` in the same coordinate
    system, mirroring how cross-chunk user spans are stored.
    """
    collection_id: str
    document_id: str
    chunk_ids: list[str]
    selection_start: int
    selection_end: int
    tag_ids: list[str]


class SuggestSpansSelectionResponse(BaseModel):
    """Result of a single selection-scoped AI suggestion run.

    ``chunk_id`` is the *anchor* chunk the spans are stored against
    (first chunk of the selection); cross-chunk spans will have ``end``
    greater than that chunk's text length.
    """
    chunk_id: str
    spans: list[TagSpan]
    error: str | None = None


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
    messages: list[SpanChatMessage]


class SpanChatDelta(BaseModel):
    """One NDJSON event streamed back during a span discussion."""
    delta: str | None = None
    done: bool | None = None
    error: str | None = None

