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
"""Most documents one ``POST /api/search/documents`` returns."""

DocumentOrder = Literal["year_asc"]
"""``year_asc``: publication year, oldest first, then document id; documents without a year
after all dated ones, by id."""


class DocumentSearchRequest(BaseModel):
    """Documents matching search criteria without a text query (#606, docs/EXPLORATION.md),
    one page of them in a stable order.

    Document filters hold on the document. Chunk filters apply per dimension: for each, some
    chunk of the document has one of its values (different filters may be met by different
    chunks), answered from the documents' chunk-value summaries as last recomputed (#529).
    Ranking documents by a text query is not available (#527): ``criteria.text_query`` must be
    absent. Without ``user_collection_id`` the public corpus is browsed, also anonymously.
    """
    model_config = ConfigDict(extra="forbid")

    criteria: SearchCriteria
    limit: int = Field(20, ge=1, le=MAX_DOCUMENT_PAGE)
    offset: int = Field(0, ge=0)
    """Position of the page in ``order``; ``offset + limit`` is at most ``retrieval_limit``."""
    user_collection_id: str | None = None
    """Browse only the documents of this collection (read access needed)."""

    @model_validator(mode="after")
    def _no_text_query(self) -> "DocumentSearchRequest":
        if self.criteria.text_query is not None:
            raise PydanticCustomError(
                "text_query_not_supported",
                "Documents are browsed by filters only; ranking documents by a text query is not supported yet.")
        return self


class DocumentSearchResponse(BaseModel):
    """One page of the documents matching the criteria and the whole population they belong to.

    ``total_count`` is the exact number of matching documents (a count, not an estimate or a
    sample). Weaviate reads no result past ``offset + limit = QUERY_MAXIMUM_RESULTS``, so only
    the first ``retrieval_limit`` documents in ``order`` can be paged through; ``bounded`` is
    ``True`` when more match than that (narrow the filters to reach the others). A chart of the
    population counts ``total_count`` documents (#528), not the page.
    """
    items: list[Document]
    """The page: at most ``limit`` documents from ``offset`` in ``order``."""
    offset: int
    next_offset: int | None
    """Offset of the next page; None when this page ends the matching or the reachable documents."""
    total_count: int
    retrieval_limit: int
    bounded: bool
    order: DocumentOrder
    criteria: SearchCriteria
    """The applied criteria, normalized (chunk values in their configured spelling)."""
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
    """Search criteria predicates on the chunk's document (``features/documents/criteria.py``)."""
    chunk_conditions: tuple[Condition, ...] = ()
    """Search criteria predicates that the returned chunk itself must satisfy (same-chunk)."""
