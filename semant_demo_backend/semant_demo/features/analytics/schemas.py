"""Corpus overview (#254) and filtered distributions (#361): visualization-independent
document counts.

Every count is a number of distinct ``Documents`` objects. For an available dimension the
counts add up to the total: ``sum(bins or values) + other_count + unknown_count ==
total_documents``. An unavailable dimension (``available: false``) has no counts at all
(``null``), never zeros.
"""
import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

MAX_TITLE_LENGTH = 100
MAX_TITLES = 10
MAX_TITLE_WORDS = 5
MIN_WORD_LENGTH = 2
MAX_FILTER_VALUES = 50
MAX_VALUE_LENGTH = 100

TITLE_WORD = re.compile(r"[^\W_]+")
"""A run of letters and digits: Weaviate's ``word`` tokenization splits text the same way."""

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


def _invalid(message: str) -> PydanticCustomError:
    return PydanticCustomError("invalid_filter", message)


class DocumentFilters(BaseModel):
    """Which documents to count; every given filter must match (AND), and a document matching
    any of the listed titles, libraries (or languages) matches that filter (OR). No filters:
    every document. Echoed in the response normalized: trimmed, de-duplicated and sorted, with
    each title reduced to the words actually searched."""
    model_config = ConfigDict(extra="forbid")

    year_min: int | None = Field(None, ge=1)
    """First publication year, inclusive. A document without a valid year never matches a range."""
    year_max: int | None = Field(None, ge=1)
    """Last publication year, inclusive; at most the current year."""
    title_contains: list[Annotated[str, Field(max_length=MAX_TITLE_LENGTH)]] = Field(
        default_factory=list, max_length=MAX_TITLES)
    """Alternatives for ``Documents.title``; a document matches when it matches any of them. In
    one alternative, every word must occur inside some title word, in any order;
    case-insensitive, diacritics-sensitive. Split at anything but letters and digits; words
    shorter than 2 characters are ignored; at most 5 words; ``*`` and ``?`` are rejected."""
    libraries: list[str] = Field(default_factory=list, max_length=MAX_FILTER_VALUES)
    """Stored ``Documents.library`` codes."""
    languages: list[str] = Field(default_factory=list, max_length=MAX_FILTER_VALUES)
    """Stored ``Documents.language`` values; matched by word, ignoring case (``ces`` also matches ``CES``)."""

    @field_validator("year_min", "year_max")
    @classmethod
    def _not_in_the_future(cls, year: int | None) -> int | None:
        if year is not None and year > datetime.now(UTC).year:
            raise _invalid("A publication year cannot be after the current year.")
        return year

    @field_validator("title_contains")
    @classmethod
    def _titles(cls, titles: list[str]) -> list[str]:
        normalized: dict[str, str] = {}
        for title in titles:
            words = cls._title_words(title)
            # Matching ignores case, so an alternative repeated in another case adds nothing.
            normalized.setdefault(words.casefold(), words)
        return [normalized[key] for key in sorted(normalized)]

    @staticmethod
    def _title_words(title: str) -> str:
        if not title.strip():
            raise _invalid("A title filter must not be empty.")
        if "*" in title or "?" in title:
            raise _invalid("The title filter does not support wildcards (* or ?); enter whole or partial words.")
        words: list[str] = []
        for word in TITLE_WORD.findall(title):
            # Matching ignores case, so a word repeated in another case adds nothing.
            if len(word) >= MIN_WORD_LENGTH and word.casefold() not in {w.casefold() for w in words}:
                words.append(word)
        if not words:
            raise _invalid("Enter at least one title word of two or more letters or digits.")
        if len(words) > MAX_TITLE_WORDS:
            raise _invalid(f"The title filter takes at most {MAX_TITLE_WORDS} words.")
        return " ".join(words)

    @field_validator("libraries", "languages")
    @classmethod
    def _values(cls, values: list[str]) -> list[str]:
        stripped = [v.strip() for v in values]
        if any(not v or len(v) > MAX_VALUE_LENGTH for v in stripped):
            raise _invalid(f"Filter values must be non-empty and at most {MAX_VALUE_LENGTH} characters long.")
        return sorted(set(stripped))

    @model_validator(mode="after")
    def _ordered_years(self) -> "DocumentFilters":
        if self.year_min is not None and self.year_max is not None and self.year_min > self.year_max:
            raise _invalid("The first publication year must not be after the last one.")
        return self

    def title_alternatives(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(title.split()) for title in self.title_contains)


class CorpusDistributionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filters: DocumentFilters = Field(default_factory=DocumentFilters)


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
    total_documents: int
    computed_at: datetime
    available: bool
    unavailable_reason: UnavailableReason | None = None
    unavailable_property: Literal["library", "publication_year"] | None = None
    """Which of the two properties cannot be counted, when ``available`` is false."""
    rows: list[LibraryYears] | None = None
    """The libraries with most documents first (at most 20), then the remaining documents, if any."""
