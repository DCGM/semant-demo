from pydantic import BaseModel
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

