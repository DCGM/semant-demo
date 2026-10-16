"""Corpus overview response (#254): visualization-independent document counts.

Every count is a number of distinct ``Documents`` objects. For an available dimension the
counts add up to the total: ``sum(bins or values) + other_count + unknown_count ==
total_documents``. An unavailable dimension (``available: false``) has no counts at all
(``null``), never zeros.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    """Documents without a year, or with one that is not a whole number from 1 to 9999."""


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
