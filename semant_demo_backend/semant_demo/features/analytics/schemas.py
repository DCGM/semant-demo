"""Corpus overview (#254) and filtered distributions (#361): visualization-independent
document counts.

Every count is a number of distinct ``Documents`` objects. For an available dimension the
counts add up to the total: ``sum(bins or values) + other_count + unknown_count ==
total_documents``. An unavailable dimension (``available: false``) has no counts at all
(``null``), never zeros.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from semant_demo.features.documents.criteria import ChunkFilters, DocumentFilters

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
