"""Corpus overview (#254), filtered distributions (#361) and distributions of a ranked search
result (#619): visualization-independent counts.

Every count is a number of distinct ``Documents`` objects. For an available dimension the
counts add up to the total: ``sum(bins or values) + other_count + unknown_count ==
total_documents``. An unavailable dimension (``available: false``) has no counts at all
(``null``), never zeros.
"""
from datetime import datetime
from typing import Literal

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from semant_demo.config import MAX_PASSAGES_LIMIT
from semant_demo.features.documents.criteria import ChunkFilters, DocumentFilters, SearchCriteria
from semant_demo.features.search.schemas import SearchType

UnavailableReason = Literal["missing_property", "unsupported_type"]
"""``missing_property``: the store declares no such document property; ``unsupported_type``:
it is not one value of the expected type (e.g. a list), so documents cannot be counted once."""


class YearBin(BaseModel):
    start: int
    """First year of the bin (inclusive)."""
    end_exclusive: int
    count: int


class PublicationYearDistribution(BaseModel):
    """Documents per decade of ``Documents.yearIssued``; bins run without gaps from the earliest
    to the latest represented decade (empty decades have count 0)."""
    available: bool
    unavailable_reason: UnavailableReason | None = None
    bin_width_years: int = 10
    bins: list[YearBin] | None = None
    unknown_count: int | None = None
    """Documents without a year, or with one that is not a whole number from 1 to the current year."""


class CategoryCount(BaseModel):
    value: str
    """The stored value, unchanged (e.g. ``"mzk"``, ``"ces"``); labels are the client's concern."""
    count: int


class CategoryDistribution(BaseModel):
    """Documents per stored value of one document property, most documents first."""
    available: bool
    unavailable_reason: UnavailableReason | None = None
    values: list[CategoryCount] | None = None
    other_count: int | None = None
    """Documents with a value beyond the listed ones (0 when every value is listed)."""
    unknown_count: int | None = None
    """Documents without a value, or with an empty one."""


class CorpusOverview(BaseModel):
    scope: Literal["searchable_corpus"]
    """The whole public corpus that Search covers, not a search result or a user collection."""
    unit: Literal["documents"]
    total_documents: int
    computed_at: datetime
    data_source: Literal["live_aggregation", "cached_aggregation"]
    """``live_aggregation``: computed from the store for this request; ``cached_aggregation``: an
    earlier request's result, served again (``computed_at`` says when it was computed)."""
    publication_year: PublicationYearDistribution
    libraries: CategoryDistribution = Field(description="Source digital library (``Documents.library``).")
    languages: CategoryDistribution = Field(
        description="Bibliographic language of the document (``Documents.language``), not of its text chunks.")


class CorpusDistributionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filters: DocumentFilters = Field(default_factory=DocumentFilters)
    chunk_filters: ChunkFilters = Field(default_factory=ChunkFilters)
    """Per dimension: a document counts when, for each filter, some chunk of it has one of the
    values, as its chunk-value summaries were last recomputed (#529). A corpus database without
    the summaries rejects them (422)."""


class YearCount(BaseModel):
    year: int
    count: int


class PublicationYearCounts(BaseModel):
    """Documents per publication year (``Documents.yearIssued``): only years with documents,
    ascending; the client groups them into wider bins."""
    available: bool
    unavailable_reason: UnavailableReason | None = None
    years: list[YearCount] | None = None
    unknown_count: int | None = None
    """Documents without a year, or with one that is not a whole number from 1 to the current year."""


class CorpusDistributions(BaseModel):
    """The documents matching ``filters``, counted by year, library and language. All counts
    describe the same documents; ``total_documents`` is their number."""
    scope: Literal["searchable_corpus"]
    unit: Literal["documents"]
    filters: DocumentFilters
    """The filters applied, normalized."""
    chunk_filters: ChunkFilters = Field(default_factory=ChunkFilters)
    """The chunk filters applied, normalized (configured spelling)."""
    total_documents: int
    computed_at: datetime
    data_source: Literal["live_aggregation", "cached_aggregation"]
    """Only the unfiltered distributions are served again (``cached_aggregation``)."""
    publication_year: PublicationYearCounts
    libraries: CategoryDistribution = Field(description="Source digital library (``Documents.library``).")
    languages: CategoryDistribution = Field(
        description="Bibliographic language of the document (``Documents.language``), not of its text chunks.")


class LibraryYears(BaseModel):
    """The documents of one library (or of the rest) per publication year."""
    library: str | None
    """The stored library code, trimmed; ``null`` for the row of the remaining documents."""
    kind: Literal["value", "unknown", "other_or_unknown"]
    """``value``: one library; ``unknown``: documents without a library; ``other_or_unknown``:
    documents without a library or of a library not listed (when there are more than listed)."""
    total_documents: int
    years: list[YearCount]
    """Only years with documents, ascending."""
    unknown_year_count: int
    """Documents of this row without a valid publication year (not in ``years``)."""


class LibraryYearDistribution(BaseModel):
    """The documents matching ``filters`` per source library and publication year: a document is
    counted in exactly one row and, with a valid year, in one year of it. The rows add up to
    ``total_documents``, and each year's counts add up to that year in the distributions."""
    scope: Literal["searchable_corpus"]
    unit: Literal["documents"]
    filters: DocumentFilters
    chunk_filters: ChunkFilters = Field(default_factory=ChunkFilters)
    total_documents: int
    computed_at: datetime
    available: bool
    unavailable_reason: UnavailableReason | None = None
    unavailable_property: Literal["library", "publication_year"] | None = None
    """Which of the two properties cannot be counted, when ``available`` is false."""
    rows: list[LibraryYears] | None = None
    """The libraries with most documents first (at most 20), then the remaining documents, if any."""


###########################################
# Distributions of a ranked result (#619) #
###########################################

ResultsMode = Literal["documents", "passages"]

MAX_RANKED_IDS = 2 * MAX_PASSAGES_LIMIT
"""Most ids a request may name at all; the configured limit of the mode is checked as well
(``RankedResultsDistributionsRequest``)."""


class RankingDescription(BaseModel):
    """How the search ranked the ids, as its answer reported it (``DocumentSearchResponse``:
    ``retrieval.type``, ``retrieval.vector``, ``bounded``; ``PassageSearchResponse``: the request's
    ``type``, ``vector``, ``bounded``). It describes the population and is echoed; it is not
    trusted for access or eligibility, which are checked again."""
    model_config = ConfigDict(extra="forbid")
    type: SearchType
    vector: str | None = None
    """The search vector; None for text search (a configured vector otherwise, None: the default)."""
    bounded: bool
    """A retrieval limit cut the ranking: more results match than it holds."""


class RankedResultsDistributionsRequest(BaseModel):
    """The ranked ids of one text-query search, as Documents or Passages Results hold them, with
    that search's criteria and collection. Every id once; at most the mode's retrieval limit
    (``SEARCH_DOCUMENTS_METADATA_LIMIT + SEARCH_DOCUMENTS_CHUNK_LIMIT`` documents,
    ``SEARCH_PASSAGES_LIMIT`` passages). A search without a text query is not a ranked result:
    its documents are charted by ``POST /api/analytics/corpus/distributions``, and filter-only
    passages are not supported."""
    model_config = ConfigDict(extra="forbid")

    mode: ResultsMode
    ids: list[UUID] = Field(max_length=MAX_RANKED_IDS)
    """Document ids (``ranked[].id``) for ``documents``, passage (chunk) ids (``ranked_ids``) for ``passages``."""
    criteria: SearchCriteria
    user_collection_id: str | None = None
    ranking: RankingDescription
    members: bool = False
    """Also return each counted result's values (``members``), to inspect a chart category
    within the ranking."""

    @model_validator(mode="after")
    def _ranked_result(self) -> "RankedResultsDistributionsRequest":
        if self.criteria.text_query is None:
            raise PydanticCustomError(
                "text_query_required",
                "Only the ranking of a text query is counted here; without one, count the matching documents "
                "(POST /api/analytics/corpus/distributions).")
        if len(set(self.ids)) != len(self.ids):
            raise PydanticCustomError("duplicate_ids", "Every ranked id must be named once.")
        return self


class RankingScope(BaseModel):
    """The ranking that was counted: as the client described it, with the server's limit."""
    type: SearchType
    vector: str | None
    bounded: bool
    """Reported by the client from its search answer; when true, the counts describe the retrieved
    results only, not every result that matches."""
    retrieval_limit: int
    """The most results a ranking of this mode holds (configured)."""


class ResultMember(BaseModel):
    """One counted result and the values it is counted under, in ranking order."""
    id: UUID
    """The document id (``documents``) or the passage id (``passages``)."""
    document_id: UUID
    year: int | None
    """The valid publication year; None when it is counted as unknown."""
    library: str | None
    """The stored library value; None when unknown (or not available)."""
    language: str | None
    """The stored document language; None when unknown (or not available)."""


class RankedResultsDistributions(BaseModel):
    """Counts of exactly the ranked results named by the request that are still eligible: never
    the corpus, never another search. ``total_count`` results in ``unit`` were counted;
    ``input_count - total_count`` (``missing_count``) were named but are gone, no longer match the
    criteria, or are outside the collection or access. For each available dimension the counts add
    up to ``total_count`` (``sum(values or years) + other_count + unknown_count``)."""
    scope: Literal["ranked_results"]
    mode: ResultsMode
    unit: Literal["documents", "passages"]
    """What each count counts: distinct documents, or passages (several passages of one document
    each count once)."""
    criteria: SearchCriteria
    """The applied criteria, normalized."""
    ranking: RankingScope
    input_count: int
    total_count: int
    missing_count: int
    distinct_documents: int
    """Distinct documents among the counted results: ``total_count`` for ``documents``, the
    distinct source documents of the passages for ``passages``."""
    computed_at: datetime
    publication_year: PublicationYearCounts
    """Results per publication year of their document."""
    libraries: CategoryDistribution = Field(description="Results per source digital library of their document.")
    languages: CategoryDistribution = Field(
        description="Results per bibliographic language of their document (``Documents.language``), not of the "
                    "passage text.")
    members: list[ResultMember] | None = None
    """The counted results in ranking order, when asked for."""
