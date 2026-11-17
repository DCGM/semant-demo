"""Inputs and results of the Annotations feature: tag definitions and span annotations."""
from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from semant_demo.core.outcomes import WriteResult
from semant_demo.features.documents.criteria import DocumentFilters
from semant_demo.features.quota.schemas import QuotaExhaustedResponse


class AnnotationChunk(BaseModel):
    """Internal, not an HTTP model: a chunk's position in its document and its canonical
    text, for offset checks and derived data; its stored absolute position (#463,
    ``features/documents/positions.py``) when read, otherwise ``None``."""
    id: UUID
    document_id: UUID | None
    order: int
    text: str
    start_char: int | None = None
    start_word: int | None = None
    word_open_at_start: bool | None = None


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
    editVersion: int = 0
    """Span writes (type, tag, offsets) since creation (#460); 0 for spans never written
    since. Sent back as ``expected_version`` so a collaborator's intervening write is
    refused instead of overwritten."""
    attributeVersion: int = 0
    """Attribute assignments written since creation; sent back with an assignment (#331). The
    values themselves are on concordance rows (``AnnotationListRow.attributes``), approved only."""


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
    chunkId: str | None = None
    """Moves the span to another chunk of its document and collection (its start moved
    there, #436): ``start`` and ``end`` are then required and count from that chunk. Only
    for a single span (``PATCH /api/tag_spans/{id}``), not in bulk updates."""


class EnrichmentStatus(str, Enum):
    """State of a span's derived text, context and positions (#328)."""
    ready = "ready"
    failed = "failed"
    """Derivation was attempted and could not read the source text; retrying may succeed."""
    invalid = "invalid"
    """The stored offsets do not describe the document's text (e.g. older data); only an
    edit of the span can fix it."""


class VectorStatus(str, Enum):
    """State of a span's contextual vector (#328)."""
    pending = "pending"
    """No vector for the current revision yet (none configured, or not attempted)."""
    ready = "ready"
    failed = "failed"
    """Embedding or storing the vector failed; the backfill or saving again retries."""


class AnnotationOrigin(str, Enum):
    """How an annotation came to exist (#460), independent of its current ``type``."""
    manual = "manual"
    ai = "ai"
    unknown = "unknown"
    """Saved before provenance was recorded; nothing is invented for it."""


class AnnotationProvenance(BaseModel):
    """Who created, last reviewed (approve/reject) and last changed an annotation, and
    when (#460): the current state only, no history. User ids are stored; the client
    resolves names. Absent values were not recorded (``origin`` ``unknown``: saved before)."""
    origin: AnnotationOrigin = AnnotationOrigin.unknown
    createdBy: UUID | None = None
    createdAt: datetime | None = None
    reviewedBy: UUID | None = None
    reviewedAt: datetime | None = None
    lastEditedBy: UUID | None = None
    lastEditedAt: datetime | None = None
    aiRunId: UUID | None = None
    """The AI suggestion run that proposed it (``origin`` ``ai``); kept through approval."""


PROVENANCE_FIELDS = tuple(AnnotationProvenance.model_fields)


class AnnotationRow(BaseModel):
    """Internal, not an HTTP model yet: a span with its derived fields (#328), as read for
    concordance (KWIC) rows and semantic search, without reading its source chunks.

    Stored values, including derived data of an older revision; the Annotations service
    hides derived fields that are not current (``service.list_annotation_rows``)."""
    id: UUID
    chunkId: UUID | None = None
    tagId: UUID | None = None
    documentId: UUID | None = None
    start: int | None = None
    end: int | None = None
    type: SpanType | None = None
    revision: int | None = None
    """Boundary changes counted from creation (1); ``None`` for spans saved before #328 (0)."""
    text: str | None = None
    leftContext: str | None = None
    rightContext: str | None = None
    documentStartChar: int | None = None
    documentEndChar: int | None = None
    documentStartWord: int | None = None
    documentEndWord: int | None = None
    enrichmentStatus: EnrichmentStatus | None = None
    enrichedRevision: int | None = None
    derivationVersion: int | None = None
    vectorStatus: VectorStatus | None = None
    vectorRevision: int | None = None
    vectorConfig: str | None = None
    sortKeyVersion: str | None = None
    sortKeyRevision: int | None = None
    """The collation of the stored sort keys and the revision they were computed for (#666,
    ``collation.py``); read only when the collection holds them."""
    distance: float | None = None
    """Vector distance, for semantic and similar ranking (#664)."""
    score: float | None = None
    """Hybrid score, for hybrid ranking (#664)."""
    documentTitle: str | None = None
    documentYear: int | None = None
    """Joined from the document per page of rows (not copied onto annotations)."""
    editVersion: int | None = None
    origin: AnnotationOrigin | None = None
    createdBy: UUID | None = None
    createdAt: datetime | None = None
    reviewedBy: UUID | None = None
    reviewedAt: datetime | None = None
    lastEditedBy: UUID | None = None
    lastEditedAt: datetime | None = None
    aiRunId: UUID | None = None
    """Provenance (#460), read only when the collection holds it."""
    attributeValues: list[str] | None = None
    attributeVersion: int | None = None
    """Accepted attribute assignments (#331, ``features/annotations/attribute_codec.py``), read only when the
    collection holds them."""

    def provenance(self) -> AnnotationProvenance:
        return AnnotationProvenance(**{k: getattr(self, k) for k in PROVENANCE_FIELDS
                                       if getattr(self, k) is not None})


class TextScope(str, Enum):
    """Where the words of a lexical annotation query must occur (#663). Each word must occur
    inside a word of one of the scope's fields, ignoring case; different words may occur in
    different fields. Word containment, not a phrase or a literal substring. Words are runs of
    letters and digits of the query composed to NFC, as the corpus text is stored; stored text in
    decomposed form (a letter followed by a combining mark) is split at the mark by Weaviate's
    word tokenization, so such a letter cannot be searched."""
    annotation = "annotation"
    """The annotated text."""
    context = "context"
    """The stored left or right context (up to 200 characters on each side, #328)."""
    both = "both"
    """The annotated text or either context."""


SCOPE_FIELDS = {
    TextScope.annotation: ("text",),
    TextScope.context: ("leftContext", "rightContext"),
    TextScope.both: ("text", "leftContext", "rightContext"),
}
"""The stored text fields a lexical query (and hybrid's BM25, #664) searches per ``TextScope``."""


class AnnotationQuery(BaseModel):
    """Internal: the stored-field conditions of a concordance query (#329), all required.
    ``words``: each must occur in a field of ``text_scope``, inside one of its words; only text
    ``ready`` under ``derivation_version`` is searched, so text left from an older revision
    or policy does not match."""
    tag_ids: list[UUID] | None = None
    types: list[SpanType]
    words: list[str] = []
    text_scope: TextScope = TextScope.annotation
    derivation_version: int | None = None
    ids: list[UUID] | None = None
    """Only these annotations (a selection whose matching members are asked for, #459)."""
    attribute_values: dict[UUID, list[UUID]] = {}
    """Attribute id -> value ids (#331): an annotation matches an attribute when it has any of its
    values; every attribute must match."""
    attribute_unassigned: list[UUID] = []
    """Attributes the annotation must have no accepted value of."""
    vector_config: str | None = None
    """Only annotations with a ``ready`` vector of this configuration and text ``ready`` under
    ``derivation_version`` (ranked retrieval, #664). Whether the vector belongs to the current
    revision cannot be filtered in Weaviate; the caller checks it per row (``vector_current``)."""
    sort_key_version: str | None = None
    """Only annotations whose sort keys are of this version (#666: counting the sortable ones)."""
    holds_value: str | None = None
    """Only approved annotations holding this ``<attribute id>:<value id>`` element (#666: one
    partition of the attribute sort)."""
    holds_none_of: list[str] = []
    """Only annotations holding none of these elements, or not approved (whose values are not
    shown, as for ``attribute_unassigned``)."""
    near_ids: list[UUID] | None = None
    """Proximity (#333): only these annotations, or, with ``near_free_except``, also every
    annotation outside those documents."""
    near_free_except: list[UUID] | None = None
    """Proximity ``absent`` (#333): the documents holding a neighbor."""


class VectorRanking(BaseModel):
    """Internal: how a ranked annotation query orders the annotations its ``AnnotationQuery``
    selects (#664): nearest to ``vector`` in ``target_vector``, or, with ``text``, Weaviate hybrid
    of that vector and BM25 of ``text`` on ``fields`` weighted by ``alpha`` (1: vector only)."""
    target_vector: str
    vector: list[float]
    text: str | None = None
    fields: tuple[str, ...] = ()
    alpha: float = 0.5
    exclude: UUID | None = None
    """Never this annotation (the source of Find similar)."""


class AnnotationSort(str, Enum):
    """Order of concordance rows; each ends with the annotation id, so it is total."""
    document = "document"
    """Document title (missing last), year, document id, then position in the document."""
    year = "year"
    """Document year (missing last), then as ``document``."""
    text = "text"
    """Annotated text in Czech dictionary order (its ``textSortKey``, #666), or, on a store
    without sort keys, as Weaviate orders the text; rows without a key first, last when
    descending."""
    left = "left"
    """Left context from the annotation outwards (its nearest word first; ``leftSortKey``, #666);
    rows without a key first, last when descending."""
    right = "right"
    """Right context in reading order (``rightSortKey``, #666); rows without a key as ``left``."""
    attribute = "attribute"
    """Values of the attribute ``sort_attribute`` in its value order, active values before
    retired ones, then document order (#666); an annotation holding several sorts once, by its
    first value; annotations without a value (and not approved ones) last. Descending reverses
    the value order only."""


class TextStatus(str, Enum):
    """Whether a concordance row's text and context are shown (#328)."""
    ready = "ready"
    pending = "pending"
    """Not derived for the annotation's current revision yet (e.g. saved before #328)."""
    failed = "failed"
    """Reading the source text failed; saving the annotation again retries."""
    invalid = "invalid"
    """The stored offsets do not fit the document's text; only an edit can fix it."""


class AnnotationListRow(BaseModel):
    """One concordance (KWIC) row: an annotation with its stored text and context (#329).

    ``start``/``end`` are the authoritative UTF-16 offsets on the anchor chunk ``chunkId``.
    ``text``, ``leftContext`` and ``rightContext`` are present only when ``textStatus`` is
    ``ready``. ``documentAvailable`` is false when the annotation's document cannot be read
    (deleted from the corpus); title and year are then absent."""
    id: UUID
    tagId: UUID | None = None
    type: SpanType | None = None
    chunkId: UUID | None = None
    documentId: UUID | None = None
    start: int | None = None
    end: int | None = None
    revision: int
    textStatus: TextStatus
    text: str | None = None
    leftContext: str | None = None
    rightContext: str | None = None
    documentAvailable: bool
    documentTitle: str | None = None
    documentYear: int | None = None
    editVersion: int = 0
    """The version a write of this annotation expects (#460)."""
    provenance: AnnotationProvenance = Field(default_factory=AnnotationProvenance)
    attributes: dict[UUID, list[UUID]] = {}
    """Accepted attribute values (#331): attribute id -> value ids."""
    attributeVersion: int = 0
    """The version an attribute assignment of this annotation expects."""
    neighbors: list["NearNeighbor"] = []
    """Proximity filter (#333): the nearest neighbor annotations that made this row match (at most
    ``MAX_NEAR_EXPLAINED``), nearest first; empty without the filter or with ``absent``."""


MAX_NEAR_EXPLAINED = 3


class NearNeighbor(BaseModel):
    """A neighbor annotation that made a row match the proximity filter (#333), placed relative to
    the row's annotation so it can be marked in the row's text: ``start``/``end`` are UTF-16
    offsets from the annotation's first character (negative: before it, in or beyond the left
    context; from the annotation's length on: in or beyond the right context). The stored contexts
    are the exact document text next to the annotation, so these offsets index them directly."""
    id: UUID
    tagId: UUID | None = None
    start: int
    end: int


class RetrievalMode(str, Enum):
    """How an annotation query selects and orders annotations (#664)."""
    lexical = "lexical"
    """Every annotation matching the filters (``q``: words, ``TextScope``), in an ``AnnotationSort``."""
    semantic = "semantic"
    """The ``k`` nearest in meaning to ``q``: its query embedding against the stored contextual vectors."""
    hybrid = "hybrid"
    """The ``k`` best by Weaviate hybrid of the contextual vector and BM25 of ``q`` on the fields of
    ``text_scope``, with the fixed weight ``HYBRID_ALPHA``."""
    similar = "similar"
    """The ``k`` nearest to the stored vector of the annotation ``similar_to``; no embedding call.
    ``q`` stays a lexical filter."""


DEFAULT_TOP_K = 100
MAX_TOP_K = 500
HYBRID_ALPHA = 0.5
"""Weight of the vector in hybrid annotation retrieval (BM25: ``1 - HYBRID_ALPHA``); Weaviate's
relative-score fusion. The default of passage search."""


class AnnotationRanking(BaseModel):
    """The retrieval mode of an annotation query (#664). Ranked modes return at most ``k``
    annotations by relevance among those matching every filter (filters apply before ranking),
    only those with a current vector of the configured model."""
    model_config = ConfigDict(extra="forbid")

    mode: RetrievalMode = RetrievalMode.lexical
    k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    """Ranked modes: at most this many annotations; ignored by ``lexical``."""
    similar_to: UUID | None = None
    """Mode ``similar``: the source annotation, of the same collection."""
    include_source: bool = False
    """Mode ``similar``: rank the source too (excluded by default)."""

    @model_validator(mode="after")
    def _source(self) -> "AnnotationRanking":
        if (self.mode == RetrievalMode.similar) != (self.similar_to is not None):
            raise ValueError("similar_to is required by mode similar and only allowed with it")
        if self.include_source and self.mode != RetrievalMode.similar:
            raise ValueError("include_source is only allowed with mode similar")
        return self

    @property
    def ranked(self) -> bool:
        return self.mode != RetrievalMode.lexical


class ResultKind(str, Enum):
    complete = "complete"
    """Every matching annotation; ``total`` is their exact number."""
    top_k = "top_k"
    """At most ``k`` annotations by relevance; ``total`` is how many were returned."""


class VectorCoverage(BaseModel):
    """Of the annotations matching a ranked query's filters, how many could be ranked (#664)."""
    matching: int
    """Annotations matching the filters (in mode ``similar`` the source too, when it matches)."""
    with_vector: int
    """Of them, those with a vector of the configured model for their current text and revision.
    Pending, failed and stale vectors cannot be ranked. A vector stored ``ready`` but for an older
    revision is found only among the ranked candidates, so this count may be slightly high when
    the result is truncated."""


class AnnotationResultSet(BaseModel):
    """What a page of annotations is a page of (#664)."""
    kind: ResultKind = ResultKind.complete
    mode: RetrievalMode = RetrievalMode.lexical
    k: int | None = None
    """Ranked modes: the requested ``k``."""
    truncated: bool = False
    """Ranked modes: more than ``k`` annotations could have been ranked."""
    coverage: VectorCoverage | None = None
    """Ranked modes."""


class ProximityCoverage(BaseModel):
    """What a proximity filter could evaluate (#333)."""
    primary: int
    """Annotations matching the other filters in documents holding a neighbor, whose positions
    were compared."""
    unknown: int
    """Of them, those left out because their position, or (``absent``) a neighbor's in their
    document, is not known for the current text: they neither match nor prove absence."""
    neighbors: int
    """Neighbor annotations found."""
    neighbors_unpositioned: int
    """Of them, those without current positions, which could not be compared."""


class AnnotationPage(BaseModel):
    """One page of a collection's concordance rows and the number of all rows of the result:
    every match (``complete``) or the ranked top ``k`` (``top_k``), in relevance order then id."""
    rows: list[AnnotationListRow]
    total: int
    offset: int
    limit: int
    result: AnnotationResultSet = Field(default_factory=AnnotationResultSet)
    proximity: ProximityCoverage | None = None
    """With a proximity filter (#333)."""
    unsortable: int | None = None
    """Text and context sorts (#666): rows of the result without current sort keys (not derived or
    not yet backfilled), placed as rows without a key; ``None`` for other orders."""


class AnnotationCounts(BaseModel):
    """How many annotations a collection holds per type (of some tags only, when asked), e.g.
    what deleting a tag or the collection would delete along (#479)."""
    approved: int
    """``pos``: manual or approved."""
    suggestions: int
    """``auto``: AI suggestions not yet approved or rejected."""
    rejected: int
    """``neg``: rejected suggestions."""


class AnnotatedDocument(BaseModel):
    """A document with annotations matching a concordance query, for the source and year
    filters (#329). ``available`` is false when the document cannot be read. ``library`` and
    ``language`` are the stored ``Documents`` values the library and language filters match
    (#663), absent when the document has none."""
    id: UUID
    title: str | None = None
    year: int | None = None
    library: str | None = None
    language: str | None = None
    count: int
    available: bool


MAX_RESOLVED_IDS = 5000
"""Annotations "select all matches" may resolve at once (#459); more is refused."""
MAX_REVIEW_BATCH = 200
"""Annotations one review request may change (#459); a client sends larger selections in parts."""
MAX_ATTRIBUTE_FILTERS = 20
"""Attributes one concordance query may filter by (#331), with values or as unassigned."""
MAX_ATTRIBUTE_FILTER_VALUES = 200
"""``<attribute id>:<value id>`` pairs one concordance query may filter by (#331), all attributes together."""


MAX_QUERY_TEXT_LENGTH = 500
"""Characters of a lexical annotation query (at most ``_MAX_WORDS`` words are searched)."""


MAX_NEAR_DISTANCE = 100_000
"""Largest distance (words or characters) a proximity filter may ask for (#333)."""


class NearRelation(str, Enum):
    """How a neighbor annotation must lie relative to the listed (primary) annotation (#333).
    Both are half-open document intervals ``[start, end)`` (``documentStart*``/``documentEnd*``)."""
    within = "within"
    """The gap between the two spans is at most ``distance`` ``unit``s: ``max(0, sB - eA, sA - eB)``,
    measured between span boundaries (never centers); adjacent and overlapping spans have gap 0."""
    overlaps = "overlaps"
    """The spans share at least one character."""
    contains = "contains"
    """The listed annotation's characters include all of the neighbor's."""
    contained_by = "contained_by"
    """The neighbor's characters include all of the listed annotation's."""
    same_document = "same_document"
    """Anywhere in the same document."""


class NearDirection(str, Enum):
    """Where a ``within`` neighbor lies, by characters (#333)."""
    either = "either"
    """Either side, overlapping too."""
    before = "before"
    """The neighbor ends at or before the listed annotation starts."""
    after = "after"
    """The neighbor starts at or after the listed annotation ends."""


class DistanceUnit(str, Enum):
    words = "words"
    """Whole words between the spans (#463: a word partly covered by a span counts as covered)."""
    chars = "chars"
    """UTF-16 code units between the spans."""


class NearFilter(BaseModel):
    """Proximity (#333): only annotations with (or, ``absent``, without) a neighbor annotation of
    the same document that matches ``tag_ids``/``types``/``attribute_values`` and lies in
    ``relation`` to it. An annotation is never its own neighbor and is listed once however many
    neighbors match. Positions are the stored document-relative intervals (#463), so chunks outside
    the user collection count; annotations without current positions never match (and, with
    ``absent``, neither do annotations of a document holding a neighbor without positions)."""
    model_config = ConfigDict(extra="forbid")

    tag_ids: list[UUID] | None = None
    """Neighbor tags; any tag when absent."""
    types: list[SpanType] | None = None
    """Neighbor types; default ``pos`` and ``auto``."""
    attribute_values: list[str] = Field(default=[], max_length=MAX_ATTRIBUTE_FILTER_VALUES)
    """Neighbor attribute values, as ``AnnotationFilters.attribute_values`` (approved neighbors only)."""
    relation: NearRelation = NearRelation.within
    distance: int = Field(default=50, ge=0, le=MAX_NEAR_DISTANCE)
    """``within``: the largest gap."""
    unit: DistanceUnit = DistanceUnit.words
    direction: NearDirection = NearDirection.either
    """``within`` only."""
    absent: bool = False
    """Only annotations with no such neighbor."""

    @model_validator(mode="after")
    def _direction(self) -> "NearFilter":
        if self.direction != NearDirection.either and self.relation != NearRelation.within:
            raise ValueError("direction is only allowed with relation within")
        return self


class AnnotationFilters(BaseModel):
    """The annotation query (#663): which of a collection's annotations the concordance lists,
    a selection resolves (#459) and the source filter offers, one definition for all of them.
    Different filters combine with AND; the values of one filter are alternatives (OR), except
    attributes (below).

    Document metadata is filtered by the shared ``DocumentFilters`` of Search, document browsing
    and Analytics (#526): the same validation and predicates select the same documents. They are
    evaluated against the documents of the matching annotations, joined per query, never copied
    onto annotations (ADR 0009)."""
    model_config = ConfigDict(extra="forbid")

    tag_ids: list[UUID] | None = None
    types: list[SpanType] | None = None
    """Default ``pos`` and ``auto``; rejected ``neg`` only when asked."""
    q: str | None = Field(default=None, max_length=MAX_QUERY_TEXT_LENGTH)
    """Lexical and ``similar`` modes: words that must each occur in a field of ``text_scope``, inside
    one of its words, ignoring case. ``semantic`` and ``hybrid``: the query ranked by (#664), required."""
    text_scope: TextScope = TextScope.annotation
    document_ids: list[UUID] | None = None
    document_filters: DocumentFilters = Field(default_factory=DocumentFilters)
    """Publication year range, title, library and document language of the annotation's document."""
    attribute_values: list[str] = Field(default=[], max_length=MAX_ATTRIBUTE_FILTER_VALUES)
    """Stored form ``<attribute id>:<value id>`` (#331): values of one attribute match any, different
    attributes all."""
    attribute_unassigned: list[UUID] = Field(default=[], max_length=MAX_ATTRIBUTE_FILTERS)
    """Only annotations without an accepted value of these attributes."""
    near: NearFilter | None = None
    """Only annotations with (or without) a neighbor annotation in a relation (#333)."""


class AnnotationIdsRequest(AnnotationFilters):
    """The annotation query whose matching annotation ids to resolve (#459). ``within``: only
    these annotations, to learn which members of a selection the filters show."""
    within: list[UUID] | None = Field(default=None, max_length=MAX_RESOLVED_IDS)
    ranking: AnnotationRanking = Field(default_factory=AnnotationRanking)
    """A ranked mode resolves exactly its top ``k`` ids (#664), never every filter match."""


class AnnotationIds(BaseModel):
    """The ids of all annotations matching a query when it was resolved (by id); the caller
    keeps them as a fixed set, so later changes of the filters or annotations never widen it.
    ``versions``: each one's ``editVersion`` then, which review actions send back (#460)."""
    ids: list[UUID]
    versions: dict[UUID, int] = {}
    attribute_versions: dict[UUID, int] = {}
    result: AnnotationResultSet = Field(default_factory=AnnotationResultSet)
    """Whether ``ids`` are every match or a ranked top ``k`` (#664)."""
    """Each one's ``attributeVersion`` then, which attribute assignments send back (#331)."""


class ReviewAction(str, Enum):
    approve = "approve"
    """Set type ``pos`` (confirmed)."""
    reject = "reject"
    """Set type ``neg``: kept as a rejected example, not deleted."""
    retag = "retag"
    """Move to ``tag_id`` of the same collection; the type is kept."""
    delete = "delete"


class AnnotationReviewRequest(BaseModel):
    """One review action for some annotations of the collection (#459)."""
    action: ReviewAction
    annotation_ids: list[UUID] = Field(min_length=1, max_length=MAX_REVIEW_BATCH)
    expected_versions: dict[UUID, int]
    """The ``editVersion`` of every annotation as the client knows it (#460): an annotation
    written since is not changed (``edit_conflict``)."""
    tag_id: UUID | None = None
    """The new tag; required for ``retag`` and only allowed there."""

    @model_validator(mode="after")
    def check_request(self) -> "AnnotationReviewRequest":
        if (self.tag_id is not None) != (self.action == ReviewAction.retag):
            raise ValueError("tag_id is required for retag and not allowed for other actions")
        if any(i not in self.expected_versions for i in self.annotation_ids):
            raise ValueError("expected_versions must give the version of every annotation")
        return self


class AnnotationValues(BaseModel):
    """Values of an annotation a review or boundary edit changed, as an undo puts them back
    (#461): only the fields that are set. ``chunk_id``, ``start`` and ``end`` are its range
    (offsets counted from that chunk, as ``PatchSpan``); ``chunk_id`` needs both offsets."""
    type: SpanType | None = None
    tag_id: UUID | None = None
    chunk_id: UUID | None = None
    start: int | None = None
    end: int | None = None

    @model_validator(mode="after")
    def check_values(self) -> "AnnotationValues":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Give at least one value to restore")
        if self.chunk_id is not None and (self.start is None or self.end is None):
            raise ValueError("chunk_id needs start and end")
        return self


class AnnotationRestoreItem(BaseModel):
    id: UUID
    expected_version: int
    """The ``editVersion`` the change being undone saved: an annotation written since is
    not restored (``edit_conflict``)."""
    values: AnnotationValues


class AnnotationRestoreRequest(BaseModel):
    """Undo of the last review or boundary change (#461): the previous values of up to
    ``MAX_REVIEW_BATCH`` annotations, each with the version the change left it at."""
    items: list[AnnotationRestoreItem] = Field(min_length=1, max_length=MAX_REVIEW_BATCH)

    @model_validator(mode="after")
    def check_items(self) -> "AnnotationRestoreRequest":
        if len({i.id for i in self.items}) != len(self.items):
            raise ValueError("Each annotation can be restored once per request")
        return self


class AnnotationReviewResult(WriteResult):
    """The outcome of a review action per annotation (best effort, ADR 0002; nothing is
    rolled back). ``succeeded``: annotations changed or deleted, and those already as the
    action asks. ``failed``: ``update_span`` / ``delete_span`` (``uncertain`` when the
    write timed out and may have been applied), ``find_annotation`` (no such annotation in
    the collection, e.g. deleted meanwhile), ``edit_conflict`` (written by someone else
    since the expected version; not changed), and best-effort steps of changed
    annotations whose change was saved (``derive_annotation``, ``embed_annotation``).
    ``versions``: the ``editVersion`` of each changed annotation after the action, and the
    current one of each conflicting annotation.
    ``previous``: for each annotation the action changed, the values it changed as they were
    before, which ``annotations/restore`` puts back (undo, #461); none for a deletion."""
    versions: dict[UUID, int] = {}
    previous: dict[UUID, AnnotationValues] = {}


class TagSpanWriteResult(TagSpan, WriteResult):
    """
    A created or updated span with the outcome of the write. ``succeeded`` holds the span
    id. ``failed`` lists the later steps that did not complete; the span is saved either
    way, and saving it again retries them: ``derive_annotation`` (its stored text, context and
    positions could not be updated), ``embed_annotation`` (its contextual vector could
    not be computed or stored; semantic search leaves the span out) and, for a span moved
    to another chunk, ``update_chunk_reference`` (collection statistics may still count it
    on its old chunk).
    """


class BulkUpdateSpansRequest(BaseModel):
    """
    Request body for bulk-applying the same :class:`PatchSpan` patch to many
    spans in a single round-trip. Used by the AI-assist "Approve / Reject all
    selected" action so the frontend doesn't have to fan out N PATCH calls.
    All spans must belong to ``collection_id``.
    """
    collection_id: str
    span_ids: list[str]
    update: PatchSpan
    expected_versions: dict[str, int] | None = None
    """``editVersion`` per span id as the client knows it (#460); spans without one are
    written unchecked."""


class BulkUpdateSpansResponse(WriteResult):
    """Result of a bulk update: the updated spans, plus per-span failures (best effort).
    ``conflicts``: the current state of the spans written by someone else since their
    expected version (failure ``edit_conflict``; not changed)."""
    spans: list[TagSpan]
    conflicts: list[TagSpan] = []


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
    config_name: str | None = None
    """The Topicer configuration to use, one of ``GET /api/ai/topicer_configs``; ``None``:
    the server default (#189)."""


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
    config_name: str | None = None
    """As :attr:`SuggestSpansRequest.config_name`."""


class TopicerConfigsResponse(BaseModel):
    """The Topicer configurations AI suggestions may use (#189)."""
    configs: list[str]
    """Names of the configurations Topicer has loaded, as Topicer lists them."""
    default_config: str
    """The server default (``TOPICER_CONFIG_NAME``), used when a request names none."""


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
    if the derived text or vector of a saved span could not be updated."""

    unsaved: int = 0
    """Proposals returned by the provider that were not saved: storage failures or
    invalid proposals (outside the requested collection, document or tags, or offsets
    that do not describe the text sent to the provider)."""


class SuggestionRunOutcome(str, Enum):
    complete = "complete"
    """Every provider call succeeded and every valid proposal was saved with its derived data
    (also when there was nothing to propose). Invalid proposals may have been rejected."""
    partial = "partial"
    """Some provider calls or writes failed; the rest of the work was done and kept."""
    failed = "failed"
    """Nothing was saved and no provider call completed with all its proposals saved."""
    cancelled = "cancelled"
    """The request was cancelled or disconnected; never sent (the stream is gone), only
    reported to callers of the workflow and in the log."""


class SuggestTagLimit(BaseModel):
    """An optimized-mode tag whose Topicer stream reached the per-tag chunk limit."""
    tag_id: str
    tag_name: str
    max_chunks: int
    """The limit applied (``TOPICER_MAX_CHUNKS_PER_TAG``)."""
    processed_chunks: int
    candidates_truncated: bool
    """More candidate chunks than ``max_chunks`` existed; they were excluded. False when
    the limit was reached exactly."""


class SuggestSpansRunEnd(BaseModel):
    """
    The last NDJSON event of an AI suggestion stream (``event == "end"``): a summary of
    the run. A stream that ends without it was interrupted; spans already announced
    are saved, nothing more is.

    A run is made of units charged to the daily AI allowance one by one: the document's
    chunks (thorough), the tags (optimized) or the one selection. A unit whose admission
    is refused is not started, nor any after it (``stop_reason == "quota_exhausted"``);
    units already started finish and their suggestions are kept.
    """
    event: Literal["end"] = "end"
    outcome: SuggestionRunOutcome = SuggestionRunOutcome.complete
    saved: int = 0
    """Spans saved (each was announced in a ``result`` event)."""
    rejected: int = 0
    """Invalid provider proposals, not saved."""
    save_failures: int = 0
    """Valid proposals whose storage write failed (a timed-out write may have landed)."""
    enrichment_failures: int = 0
    """Saved spans whose derived text or contextual vector (#328) could not be stored."""
    provider_failures: int = 0
    """Provider calls that failed (their chunks or tags got no proposals)."""
    error: str | None = None
    """Why the run did not complete, if it did not."""
    unit: Literal["chunk", "tag", "selection"] = "chunk"
    units_total: int = 0
    """Units the run would process (document chunks, tags, or 1)."""
    units_processed: int = 0
    """Units admitted and sent to Topicer."""
    stop_reason: Literal["quota_exhausted"] | None = None
    """Why the remaining units were not started."""
    quota_exhausted: QuotaExhaustedResponse | None = None
    """The refusal that stopped the run (its ``reset_at``), with ``stop_reason``."""
    max_chunks_per_tag: int | None = None
    """Optimized mode: the per-tag chunk limit sent to Topicer."""
    tag_limits: list[SuggestTagLimit] = Field(default_factory=list)
    """Optimized mode: the tags that reached ``max_chunks_per_tag``."""


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


class SpanChatMessage(BaseModel):
    """One message in a span-discussion chat history."""
    role: Literal["user", "assistant"]
    content: str


class DiscussSpanRequest(BaseModel):
    """
    Request body for ``POST /api/ai/discuss_span``.

    The frontend sends the full chat history each call (the new user turn is
    the last message). The backend resolves span / document / tag / chunk
    context server-side and prepends it as a system message. The span must belong to
    ``collection_id``.
    """
    collection_id: str
    span_id: str
    messages: list[SpanChatMessage]


class SpanChatDelta(BaseModel):
    """One NDJSON event streamed back during a span discussion."""
    delta: str | None = None
    done: bool | None = None
    error: str | None = None


##########################
# CSV export (#719)      #
##########################

class AnnotationExportScope(str, Enum):
    """Which annotations of a collection a CSV export holds (#719)."""
    selection = "selection"
    """The annotations ``annotation_ids`` (the workspace selection), whatever the current filters;
    every type. Ids that are no annotation of the collection (any more) are counted as missing."""
    filters = "filters"
    """Every annotation matching the annotation query ``filters`` (#663), never only a page."""
    collection = "collection"
    """Every annotation of the collection of the types ``types``; no other filter."""


class CsvDelimiter(str, Enum):
    comma = "comma"
    semicolon = "semicolon"
    """For spreadsheets whose regional settings use a decimal comma (e.g. Czech Excel)."""


class AnnotationExportRequest(BaseModel):
    """A CSV export of a collection's annotations (#719): one row per annotation, in no particular
    order; the annotations are resolved by id when the export starts. The identity,
    status, text, context, document position and accepted attribute columns are always present;
    the optional groups add columns only."""
    model_config = ConfigDict(extra="forbid")

    scope: AnnotationExportScope
    annotation_ids: list[UUID] | None = Field(default=None, max_length=MAX_RESOLVED_IDS)
    """Scope ``selection`` (required there, only allowed there)."""
    filters: AnnotationFilters | None = None
    """Scope ``filters`` (required there, only allowed there); lexical: every match."""
    types: list[SpanType] | None = None
    """Scope ``collection`` (required there, at least one; only allowed there)."""
    chunk_metadata: bool = False
    """Add the anchor chunk's language and configured classifications."""
    document_metadata: bool = True
    """Add the document's bibliographic fields (the document id is always present)."""
    provenance: bool = False
    """Add who created, reviewed and last changed each annotation, when, its revision and AI metadata."""
    delimiter: CsvDelimiter = CsvDelimiter.comma

    @model_validator(mode="after")
    def _scope_fields(self) -> "AnnotationExportRequest":
        given = {"annotation_ids": self.annotation_ids is not None, "filters": self.filters is not None,
                 "types": self.types is not None}
        needed = {AnnotationExportScope.selection: "annotation_ids", AnnotationExportScope.filters: "filters",
                  AnnotationExportScope.collection: "types"}[self.scope]
        if not given[needed]:
            raise ValueError(f"Scope {self.scope.value} needs {needed}")
        extra = [name for name, present in given.items() if present and name != needed]
        if extra:
            raise ValueError(f"Scope {self.scope.value} does not take {', '.join(extra)}")
        if self.scope == AnnotationExportScope.collection and not self.types:
            raise ValueError("Choose at least one annotation status to export")
        return self
