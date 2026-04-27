from pydantic import BaseModel

from semant_demo.schemas import SpanType

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