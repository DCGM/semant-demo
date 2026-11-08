"""Search HTTP models and the neutral retrieval inputs passed to the search adapter.

The dataclasses at the end name application fields and options only; the adapter decides
how they map to stored properties, references and query calls.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from semant_demo.features.documents.criteria import ChunkFilters, Condition, DocumentFilters, SearchCriteria
from semant_demo.features.documents.schemas import DocumentChunk, Document
from semant_demo.features.quota.schemas import QuotaExhaustedResponse


class SearchType(str, Enum):
    text = "text"
    vector = "vector"
    hybrid = "hybrid"


class FilterType(str, Enum):
    nominal = "nominal"
    interval = "interval"


class NominalFilterValue(BaseModel):
    user_form: str
    backend_form: str


class SearchFilter(BaseModel):
    id: str
    name: str
    type: FilterType
    description: str
    target_property: str
    values: list[NominalFilterValue] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None


class SearchFilterInput(BaseModel):
    id: str
    values: list[str | int | float] | str | int | float | None = None
    min_value: int | float | datetime | None = None
    max_value: int | float | datetime | None = None


class SearchFiltersResponse(BaseModel):
    filters: list[SearchFilter]


class SearchVectorInfo(BaseModel):
    """A configured search vector as clients see it (``vectors.py``)."""
    id: str
    name: str
    description: str = ""


class SearchVectorsResponse(BaseModel):
    default_vector: str
    """Id of the vector used when a request selects none."""
    vectors: list[SearchVectorInfo]


class SummaryRequestBase(BaseModel):
    """Which summaries to generate. The server chooses the model (the search_summary tier)."""
    search_title_generate: bool = True
    search_title_prompt: str | None = None
    # upper bound on number of words in the title
    search_title_brevity: int | None = None

    search_summary_generate: bool = True
    search_summary_prompt: str | None = None
    # upper bound on number of words in the summary
    search_summary_brevity: int | None = None

    search_results_summary_generate: bool = True
    search_results_summary_prompt: str | None = None
    # upper bound on number of words in the summary
    search_results_summary_brevity: int | None = None


class SearchRequest(SummaryRequestBase):
    query: str
    limit: int = 10
    user_collection_id: str | None = None
    type: SearchType = SearchType.hybrid
    hybrid_search_alpha: float = 0.5
    search_llm_filter: bool = False

    # The shared search criteria filters (features/documents/criteria.py, #526): applied inside
    # retrieval; every chunk filter must hold on the returned chunk. Either these or the older
    # ``filters`` and ``min_year``/``max_year``/``language`` fields, not both (400).
    document_filters: DocumentFilters | None = None
    chunk_filters: ChunkFilters | None = None

    # Older filter fields, kept for existing clients.
    filters: list[SearchFilterInput] | None = None

    min_year: int | None = None
    max_year: int | None = None
    min_date: datetime | None = None
    max_date: datetime | None = None
    language: str | None = None

    tag_uuids: list[str]
    positive: bool
    automatic: bool

    is_hyde: bool = False  # variable which indicates if query is document

    # Configured search vector (GET /api/search/vectors) of vector and hybrid search;
    # None selects the default. Text search uses no vector.
    vector: str | None = None


class SearchResultChunk(DocumentChunk):
    """
    A search hit: the chunk, its document and optional generated summaries. ``text`` is
    display text (``service.display_text``: hyphenated line breaks joined), not the
    canonical stored text; span offsets do not apply to it. The document view reads
    canonical text (``DocumentDetail``).

    ``metadata`` holds the chunk's stored classifications (``filters.TASK_CLASSES``) that
    have values: property name -> values, in ``TASK_CLASSES`` order.

    ``origin`` is ``"web"`` for a web search result that a RAG answer used (#370): not a
    corpus chunk, so there is no document or chunk window to open; its ids are made up for
    that answer only.
    """
    query_title: str | None = None
    query_summary: str | None = None
    summary: str | None = None
    document_object: Document
    metadata: dict[str, list[str]] = {}
    origin: Literal["corpus", "web"] = "corpus"


MAX_PASSAGE_PAGE = 100
"""Most passages one ``POST /api/search/passages`` or ``/api/search/passages/read`` returns."""


class PassageSearchRequest(BaseModel):
    """A passage search (#605, #611, docs/EXPLORATION.md): its ranking and first page.

    The criteria need a text query: filter-only browsing of passages is deferred. Every
    chunk filter holds on the returned chunk itself (same-chunk) and every document filter on
    its document. The remaining fields are retrieval options, not criteria. Without
    ``user_collection_id`` the public corpus is searched, also anonymously.
    """
    model_config = ConfigDict(extra="forbid")

    criteria: SearchCriteria
    limit: int = Field(20, ge=1, le=MAX_PASSAGE_PAGE)
    """Size of the first page: the passages of this many leading ranked ids are read in full."""
    type: SearchType = SearchType.hybrid
    hybrid_search_alpha: float = Field(0.5, ge=0, le=1)
    vector: str | None = None
    """Configured search vector (``GET /api/search/vectors``); None: the default."""
    user_collection_id: str | None = None
    """Search only the chunks of this collection (read access needed)."""

    @model_validator(mode="after")
    def _text_query_required(self) -> "PassageSearchRequest":
        if self.criteria.text_query is None:
            raise PydanticCustomError(
                "text_query_required", "Passages need a text query; browsing passages by filters alone is not supported.")
        return self


class PassageSearchResponse(BaseModel):
    """The ranking of one passage search, its first page and what the ranking covers.

    The search ranks at most ``retrieval_limit`` passages once (best first, ``ranked_ids``);
    later pages read slices of those ids (``POST /api/search/passages/read``) instead of
    ranking again, and visualizations of the same search can describe the same population.
    ``bounded`` is ``False`` when the ranking holds every matching passage (then
    ``total_count`` is their number) and ``True`` when the limit cut it (more passages match
    but are not retrievable). Vector and hybrid search rank every passage that passes the
    filters, so they are bounded unless the filters leave fewer than the limit.
    """
    ranked_ids: list[UUID]
    """The ranked passage ids, best first, each once; at most ``retrieval_limit``."""
    items: list[SearchResultChunk]
    """The passages of the first ``read_count`` ranked ids, in that order; a passage gone or
    without a document by the time it is read is left out."""
    read_count: int
    """How many leading ``ranked_ids`` this answer read; the next page starts there."""
    retrieval_limit: int
    bounded: bool
    total_count: int | None
    """The number of matching passages; None when ``bounded``."""
    criteria: SearchCriteria
    """The applied criteria, normalized (as ``SearchRequest`` echoes them)."""
    vector: str | None = None
    """The search vector used; None for text search."""
    time_spent: float


class PassageReadRequest(BaseModel):
    """Passages of an earlier passage search by id (#611): a later page of its ``ranked_ids``.

    ``criteria`` and ``user_collection_id`` are those of the search. Access is checked again
    and the passages are read under the same restrictions as the search's ranking (the text
    query ranks nothing here), so an id the search could not have returned is never answered.
    """
    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(min_length=1, max_length=MAX_PASSAGE_PAGE)
    criteria: SearchCriteria
    user_collection_id: str | None = None


class PassageReadResponse(BaseModel):
    items: list[SearchResultChunk]
    """The requested passages that still match the search, in the requested order, each once;
    the others (deleted, outside the scope, no longer matching the filters) are left out."""
    time_spent: float


MAX_DOCUMENT_PAGE = 100
"""Most documents one ``POST /api/search/documents`` or ``/api/search/documents/read`` returns."""

DocumentOrder = Literal["year_asc", "metadata_then_text"]
"""``year_asc`` (no text query): publication year, oldest first, then document id; documents
without a year after all dated ones, by id. ``metadata_then_text`` (a text query, #607): the
documents whose bibliographic metadata matches the query, by metadata relevance, then the other
documents by their best-matching chunk, in the chunk search's order."""

DocumentMatch = Literal["metadata", "text"]
"""Why a document is a result of a text query: its bibliographic metadata (title, subtitle,
authors, publisher) holds every word of the query (``metadata``), or one of its chunks matches it
(``text``). A metadata match may also have a matching chunk."""


class DocumentSearchRequest(BaseModel):
    """Documents matching search criteria (#606, #607, docs/EXPLORATION.md).

    The filters decide which documents are eligible: document filters hold on the document, and
    chunk filters apply per dimension: for each, some chunk of the document has one of its values
    (different filters may be met by different chunks), answered from the documents' chunk-value
    summaries as last recomputed (#529). Without ``user_collection_id`` the public corpus is
    searched, also anonymously.

    Without a text query, the eligible documents are paged in a stable order (``offset``).
    With one, it ranks them once, independently of the filters (``metadata_then_text``): the
    best chunk of a document need not satisfy the chunk filters. The answer holds the whole
    bounded ranking and its first ``limit`` documents; later pages are read by id
    (``POST /api/search/documents/read``), so ``offset`` must be 0. ``type``,
    ``hybrid_search_alpha`` and ``vector`` select how chunks are ranked, as for passages.
    """
    model_config = ConfigDict(extra="forbid")

    criteria: SearchCriteria
    limit: int = Field(20, ge=1, le=MAX_DOCUMENT_PAGE)
    offset: int = Field(0, ge=0)
    """Position of the page in ``order`` without a text query; ``offset + limit`` is at most
    ``retrieval_limit``. Must be 0 with a text query."""
    type: SearchType = SearchType.hybrid
    hybrid_search_alpha: float = Field(0.5, ge=0, le=1)
    vector: str | None = None
    """Configured search vector (``GET /api/search/vectors``); None: the default."""
    user_collection_id: str | None = None
    """Only the documents of this collection (read access needed)."""

    @model_validator(mode="after")
    def _ranked_from_the_start(self) -> "DocumentSearchRequest":
        if self.criteria.text_query is not None and self.offset:
            raise PydanticCustomError(
                "offset_with_text_query",
                "A text query ranks the documents once; read later pages by id (POST /api/search/documents/read).")
        return self


class RankedDocument(BaseModel):
    """One document of a text query's ranking: why it matched and its best-matching chunk, if any."""
    id: UUID
    match: DocumentMatch
    chunk_id: UUID | None = None
    """The document's best-matching chunk in the chunk ranking: the evidence of a ``text`` match,
    and of a ``metadata`` match when one of its chunks also ranked. It need not satisfy the chunk
    filters."""


class DocumentHit(BaseModel):
    """A document result: the document, and for a text query why it matched and its best chunk."""
    document: Document
    match: DocumentMatch | None = None
    """None without a text query."""
    chunk: SearchResultChunk | None = None
    """The best-matching chunk (``RankedDocument.chunk_id``), when there is one and it can still be
    read; display text, as in passage results."""


class DocumentRetrieval(BaseModel):
    """How a text query ranked the documents, and whether each part covers everything it matches."""
    metadata_limit: int
    """Most metadata matches retrieved (``SEARCH_DOCUMENTS_METADATA_LIMIT``)."""
    metadata_bounded: bool
    """More documents match by metadata than ``metadata_limit``."""
    chunk_limit: int
    """Most chunks ranked to find the documents matching by text (``SEARCH_DOCUMENTS_CHUNK_LIMIT``)."""
    chunk_bounded: bool
    """More chunks match than ``chunk_limit``, so more documents may match by text. Vector and hybrid
    search match every chunk of the eligible documents."""
    ranked_chunks: int
    """Chunks of the ranking (at most ``chunk_limit``)."""
    type: SearchType
    vector: str | None = None
    """The search vector used; None for text search."""


class DocumentSearchResponse(BaseModel):
    """The documents matching the criteria: one page and what the whole result covers.

    ``eligible_count`` is the exact number of documents the filters admit (a count, not an
    estimate or a sample). Without a text query those are the results: ``total_count`` equals
    it and the first ``retrieval_limit`` of them in ``order`` can be paged through by ``offset``
    (Weaviate reads no result past ``QUERY_MAXIMUM_RESULTS``); ``bounded`` when more match.

    With a text query, ``ranked`` is its bounded ranking of distinct documents and ``items`` its
    first ``read_count`` entries in full. ``bounded`` is ``True`` when a retrieval limit
    (``retrieval``) cut it; ``total_count`` is the number of matching documents only when it did
    not (then every eligible document that matches is ranked), else None: the ranking is a lower
    bound and ``eligible_count`` an upper one. A chart of the result counts ``total_count``
    documents without a text query and the ranked documents with one (#528), never the page.
    """
    items: list[DocumentHit]
    """The page, in ``order``; with a text query, a ranked document that is gone or no longer
    eligible by the time it is read is left out."""
    offset: int
    next_offset: int | None
    """Offset of the next page without a text query; None when this page ends the matching or the
    reachable documents, and always with a text query (read by id)."""
    total_count: int | None
    eligible_count: int
    retrieval_limit: int
    """Without a text query, the most documents that can be paged through; with one, the most
    documents the ranking can hold (``metadata_limit + chunk_limit``)."""
    bounded: bool
    order: DocumentOrder
    ranked: list[RankedDocument] | None = None
    """A text query's ranking, best first, each document once; None without a text query."""
    read_count: int = 0
    """How many leading ``ranked`` entries ``items`` read; the next page starts there."""
    retrieval: DocumentRetrieval | None = None
    """How a text query ranked the documents; None without one."""
    criteria: SearchCriteria
    """The applied criteria, normalized (chunk values in their configured spelling)."""
    time_spent: float


class DocumentReadRequest(BaseModel):
    """Documents of an earlier text-query document search (#607): a later page of its ``ranked``.

    ``criteria`` and ``user_collection_id`` are those of the search. Access is checked again and
    the documents are read under the same eligibility, so an entry the search could not have
    returned is never answered; an evidence chunk is read only when it belongs to the document.
    """
    model_config = ConfigDict(extra="forbid")

    ranked: list[RankedDocument] = Field(min_length=1, max_length=MAX_DOCUMENT_PAGE)
    criteria: SearchCriteria
    user_collection_id: str | None = None


class DocumentReadResponse(BaseModel):
    items: list[DocumentHit]
    """The requested documents that are still eligible, in the requested order, each once."""
    time_spent: float


class SearchResponse(BaseModel):
    results: list[SearchResultChunk]
    # Optional overall query-based summary of the results
    results_summary: str | None = None
    search_request: SearchRequest
    time_spent: float
    search_log: list[str]
    # The search vector used (the selected or default one); None for text search.
    vector: str | None = None
    # Problems that did not prevent the results, e.g. failed optional summaries.
    warnings: list[str] = []
    # Set when the requested titles/summaries were skipped because the caller's daily AI
    # allowance had no room for them; the results are complete (warnings says so too).
    quota_exhausted: QuotaExhaustedResponse | None = None


#############################
# Neutral retrieval inputs #
#############################

class Op(str, Enum):
    equal = "equal"
    greater_or_equal = "greater_or_equal"
    less_or_equal = "less_or_equal"
    contains_any = "contains_any"


@dataclass(frozen=True)
class FieldCondition:
    """A chunk matches when its (or its document's) ``field`` satisfies ``op`` with ``value``."""
    field: str
    op: Op
    value: Any


@dataclass(frozen=True)
class TagFilter:
    """Chunks carrying any of ``tag_ids`` as a suggested (automatic) or approved (positive) tag.

    Only the enabled kinds are matched; at least one is enabled.
    """
    tag_ids: tuple[UUID, ...]
    automatic: bool
    positive: bool


@dataclass(frozen=True)
class ChunkQuery:
    """One retrieval: all conditions must hold (AND)."""
    text: str
    mode: SearchType
    limit: int
    alpha: float = 0.5
    """Hybrid weighting between vector (1.0) and keyword (0.0) scores."""
    vector: list[float] | None = None
    """Query embedding; required for vector and hybrid modes."""
    target_vector: str | None = None
    """Stored named vector that ``vector`` is compared with; required with ``vector``."""
    collection_id: UUID | None = None
    tags: TagFilter | None = None
    conditions: tuple[FieldCondition, ...] = ()
    """Older filters (``SearchRequest.filters`` and the legacy fields)."""
    document_conditions: tuple[Condition, ...] = ()
    """Search criteria predicates on the chunk's document (``features/documents/criteria.py``),
    also on its chunk-value summaries (#529) for document-level chunk filters (#607)."""
    document_collection_id: UUID | None = None
    """Only chunks whose document belongs to this collection (all its chunks, #607); unlike
    ``collection_id``, which selects the chunks linked to a collection themselves."""
    chunk_conditions: tuple[Condition, ...] = ()
    """Search criteria predicates that the returned chunk itself must satisfy (same-chunk)."""
