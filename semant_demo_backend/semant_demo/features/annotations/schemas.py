"""Inputs and results of the Annotations feature: tag definitions and span annotations."""
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

from semant_demo.schema.outcomes import WriteResult

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


class SpanType(str, Enum):
    pos = "pos"
    neg = "neg"
    auto = "auto"


class TagSpan(BaseModel):
    id: str | None = None
    chunkId: str
    tagId: str
    start: int
    end: int
    type: SpanType | None = None
    # Optional metadata produced by AI/automatic taggers. Always None for
    # manual spans; populated when an LLM proposes a span via the Topicer
    # service. Stored alongside the span itself in the database.
    reason: str | None = None
    confidence: float | None = None


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


##################
# AI suggestions #
##################

class SuggestSpansRequest(BaseModel):
    """Request body for AI span suggestion endpoints."""
    collection_id: str
    document_id: str
    tag_ids: list[str]


class SuggestSpansSelectionRequest(BaseModel):
    """
    Request body for ``POST /api/ai/suggest_spans/selection``.

    The user has highlighted a passage and asked the AI to propose tags
    for *only that passage*. The selection may span multiple chunks of the
    collection; the frontend sends the chunk IDs in document order. Offsets
    are measured, in UTF-16 code units, against the concatenation of those
    chunks' text:

    - ``selection_start`` — offset measured from the start of the
      first chunk (so it is also the local offset inside that chunk).
    - ``selection_end`` — offset across the concatenation (may
      exceed the first chunk's length when the selection extends into
      later chunks).

    Each resulting auto span is anchored on the chunk where it starts, with
    ``start`` / ``end`` in that chunk's coordinates, as cross-chunk user spans
    are stored.
    """
    collection_id: str
    document_id: str
    chunk_ids: list[str]
    selection_start: int
    selection_end: int
    tag_ids: list[str]


class SuggestSpansChunkResult(BaseModel):
    """
    One NDJSON event emitted while AI suggestions are being generated
    (``event == "result"``).

    Frontend can use this to progressively render auto spans as each chunk
    finishes processing. ``spans`` are sent only after they were stored.
    """
    event: Literal["result"] = "result"

    chunk_id: str
    """ID of the chunk that was just processed (the anchor chunk of the spans)."""

    spans: list[TagSpan]
    """Auto-typed spans newly persisted in the database for this chunk."""

    error: str | None = None
    """Set if processing this chunk failed, or if some proposals could not be saved
    (then ``spans`` holds the ones that were saved and ``unsaved`` counts the rest), or
    if the chunk tag of a saved span (used by tag-filtered search) could not be updated."""

    unsaved: int = 0
    """Proposals returned by the provider that were not saved: storage failures or
    invalid proposals (outside the requested collection, document or tags, or offsets
    that do not describe the text sent to the provider)."""


class SuggestionRunOutcome(str, Enum):
    complete = "complete"
    """Every provider call succeeded and every valid proposal was saved with its chunk tag
    (also when there was nothing to propose). Invalid proposals may have been rejected."""
    partial = "partial"
    """Some provider calls or writes failed; the rest of the work was done and kept."""
    failed = "failed"
    """Nothing was saved and no provider call completed with all its proposals saved."""
    cancelled = "cancelled"
    """The request was cancelled or disconnected; never sent (the stream is gone), only
    reported to callers of the workflow and in the log."""


class SuggestSpansRunEnd(BaseModel):
    """
    The last NDJSON event of an AI suggestion stream (``event == "end"``): a summary of
    the run. A stream that ends without it was interrupted; spans already announced
    are saved, nothing more is.
    """
    event: Literal["end"] = "end"
    outcome: SuggestionRunOutcome = SuggestionRunOutcome.complete
    saved: int = 0
    """Spans saved (each was announced in a ``result`` event)."""
    rejected: int = 0
    """Invalid provider proposals, not saved."""
    save_failures: int = 0
    """Valid proposals whose storage write failed (a timed-out write may have landed)."""
    search_tag_failures: int = 0
    """Saved spans whose chunk tag (tag-filtered search) could not be updated."""
    provider_failures: int = 0
    """Provider calls that failed (their chunks or tags got no proposals)."""
    error: str | None = None
    """Why the run did not complete, if it did not."""


class DeleteAutoSpansRequest(BaseModel):
    """
    Request body for bulk deletion of unresolved AI proposals
    (``type == auto``) within a single (collection, document) scope.
    """
    collection_id: str
    document_id: str
    tag_ids: list[str]


class DeleteAutoSpansResponse(WriteResult):
    """Result of a bulk auto-span deletion; ``succeeded`` lists the deleted span ids."""
    deleted: int
