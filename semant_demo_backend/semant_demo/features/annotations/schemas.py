"""Inputs and results of the Annotations feature: tag definitions and span annotations."""
from uuid import UUID

from pydantic import BaseModel, model_validator

from semant_demo.schema.outcomes import WriteResult
from semant_demo.schemas import SpanType, TagSpan

class Tag(BaseModel):
    id: UUID
    name: str
    shorthand: str
    color: str
    pictogram: str
    definition: str
    examples: list[str]

class PostTag(BaseModel):
    name: str
    shorthand: str
    color: str
    pictogram: str
    definition: str
    examples: list[str] = []

class PatchTag(BaseModel):
    name: str | None = None
    shorthand: str | None = None
    color: str | None = None
    pictogram: str | None = None
    definition: str | None = None
    examples: list[str] | None = None

    @model_validator(mode="after")
    def check_at_least_one_field_set(self) -> "PatchTag":
        # Null means "keep the current value"; tag fields cannot be cleared.
        if not self.model_dump(exclude_unset=True, exclude_none=True):
            raise ValueError("At least one field must be provided for update")
        return self


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


class TagSpanWriteResult(TagSpan, WriteResult):
    """
    A created or updated span with the outcome of the write. ``succeeded`` holds the span
    id. ``failed`` lists chunk tag updates (``update_chunk_tags``) that did not complete:
    the span is saved, but tag-filtered search does not reflect it until the span is
    saved again.
    """


class BulkUpdateSpansRequest(BaseModel):
    """
    Request body for bulk-applying the same :class:`PatchSpan` patch to many
    spans in a single round-trip. Used by the AI-assist "Approve / Reject all
    selected" action so the frontend doesn't have to fan out N PATCH calls.
    """
    span_ids: list[str]
    update: PatchSpan


class BulkUpdateSpansResponse(WriteResult):
    """Result of a bulk update: the updated spans, plus per-span failures (best effort)."""
    spans: list[TagSpan]


class DeleteSpansForTagsRequest(BaseModel):
    """
    Request body for bulk deletion of every span for the given tags within a
    single (collection, document) scope, regardless of ``type``.
    """
    collection_id: str
    document_id: str
    tag_ids: list[str]


class DeleteSpansForTagsResponse(WriteResult):
    """Result of a bulk per-tag deletion; ``succeeded`` lists the deleted span ids."""
    deleted: int


class TagSpanBatchRequest(BaseModel):
    chunk_ids: list[str] | None = None
    collection_id: str
