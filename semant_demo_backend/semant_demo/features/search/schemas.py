"""Search HTTP models and the neutral retrieval inputs passed to the search adapter.

The dataclasses at the end name application fields and options only; the adapter decides
how they map to stored properties, references and query calls.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from semant_demo.features.documents.criteria import ChunkFilters, Condition, DocumentFilters
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
