from pydantic import BaseModel

from semant_demo.schemas import SpanType, TagSpan

class PostSpan(BaseModel):
    start: int
    end: int
    type: SpanType

    chunkId: str
    tagId: str

    # AI metadata, only populated for ``type == auto`` spans.
    reason: str | None = None
    confidence: float | None = None


class PatchSpan(BaseModel):
    start: int | None = None
    end: int | None = None
    type: SpanType | None = None

    tagId: str | None = None


class BulkUpdateSpansRequest(BaseModel):
    """
    Request body for bulk-applying the same :class:`PatchSpan` patch to many
    spans in a single round-trip. Used by the AI-assist "Approve / Reject all
    selected" action so the frontend doesn't have to fan out N PATCH calls.
    """
    span_ids: list[str]
    update: PatchSpan


class BulkUpdateSpansResponse(BaseModel):
    """Updated spans returned by a bulk update."""
    spans: list[TagSpan]


class DeleteSpansForTagsRequest(BaseModel):
    """
    Request body for bulk deletion of every span for the given tags within a
    single (collection, document) scope, regardless of ``type``.
    """
    collection_id: str
    document_id: str
    tag_ids: list[str]


class DeleteSpansForTagsResponse(BaseModel):
    """Result of a bulk per-tag deletion."""
    deleted: int