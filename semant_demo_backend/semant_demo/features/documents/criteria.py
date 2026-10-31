"""Search criteria (#526): the one definition of what Search, document browsing and Analytics
filter by, how requested filters are validated and normalized, and which predicates they
mean (docs/EXPLORATION.md).

* ``DocumentFilters`` restrict documents by their bibliographic metadata: publication year,
  title, source library and **document language** (``Documents.language``).
* ``ChunkFilters`` restrict text chunks by their stored values: **chunk language**
  (``Chunks.language``) and the configured classifications (``Chunks.<dimension>``,
  ``features/search/filters.TASK_CLASSES``). No year (the chunk year is a copy of the
  document's, #153) and no named entities.
* ``SearchCriteria`` is an optional text query with both. Retrieval settings (method, limit,
  vectors) belong to each endpoint's own request; user collections, tags and annotations are
  not search criteria.

Different filters combine with AND; the values of one filter are alternatives (OR).

Chunk filters are exact categorical matches; missing values cannot be selected. Passages
(chunk Search) need every chunk filter to hold on the **returned chunk** itself (same-chunk).
Document-level operations (browse, Analytics) will apply them per dimension: for each
filter, some chunk of the document matches it (#529, decided on #526). Until #529 stores the
values they need, they reject chunk filters (``ChunkFiltersUnavailable``, 422), never ignore
them or answer 0.

``document_conditions`` and ``chunk_conditions`` translate the filters into neutral
predicates on application property names. The Weaviate adapters render them for the
collection they query (``adapters/weaviate/criteria.py``). This module imports no other
feature, so Search, Documents and Analytics can all use it.
"""
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from semant_demo.core.errors import InvalidRequestError

MAX_TITLE_LENGTH = 100
MAX_TITLES = 10
MAX_TITLE_WORDS = 5
MIN_WORD_LENGTH = 2
MAX_FILTER_VALUES = 50
MAX_VALUE_LENGTH = 100
MAX_TEXT_QUERY_LENGTH = 1000

TITLE_WORD = re.compile(r"[^\W_]+")
"""A run of letters and digits: Weaviate's ``word`` tokenization splits text the same way."""

YEAR_PROPERTY = "yearIssued"
TITLE_PROPERTY = "title"
LIBRARY_PROPERTY = "library"
LANGUAGE_PROPERTY = "language"
"""``Documents.language`` in document conditions, ``Chunks.language`` in chunk conditions."""


def _invalid(message: str) -> PydanticCustomError:
    return PydanticCustomError("invalid_filter", message)


def _normalized_values(values: list[str]) -> list[str]:
    stripped = [v.strip() for v in values]
    if any(not v or len(v) > MAX_VALUE_LENGTH for v in stripped):
        raise _invalid(f"Filter values must be non-empty and at most {MAX_VALUE_LENGTH} characters long.")
    return sorted(set(stripped))


##########
# Models #
##########

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
        return _normalized_values(values)

    @model_validator(mode="after")
    def _ordered_years(self) -> "DocumentFilters":
        if self.year_min is not None and self.year_max is not None and self.year_min > self.year_max:
            raise _invalid("The first publication year must not be after the last one.")
        return self

    def title_alternatives(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(title.split()) for title in self.title_contains)


class ChunkFilters(BaseModel):
    """Which text chunks qualify: every given filter must match (AND), each by one of its values
    (OR). Values are the stored ones, matched exactly; a request may name them in any case and
    gets the configured spelling back (``validate_chunk_filters``). Missing values cannot be
    selected. Normalized: trimmed, de-duplicated and sorted."""
    model_config = ConfigDict(extra="forbid")

    languages: list[str] = Field(default_factory=list, max_length=MAX_FILTER_VALUES)
    """Language codes of the chunk text (``Chunks.language``), not of its document."""
    classifications: dict[str, list[str]] = Field(default_factory=dict)
    """Configured classification (``GET /api/search/filters``, e.g. ``complexity``) -> accepted
    values (e.g. ``["easy"]``); each listed classification needs at least one value."""

    @field_validator("languages")
    @classmethod
    def _languages(cls, values: list[str]) -> list[str]:
        return _normalized_values(values)

    @field_validator("classifications")
    @classmethod
    def _classifications(cls, classifications: dict[str, list[str]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for name, values in classifications.items():
            if not values:
                raise _invalid(f"The chunk filter '{name}' needs at least one value.")
            if len(values) > MAX_FILTER_VALUES:
                raise _invalid(f"A chunk filter takes at most {MAX_FILTER_VALUES} values.")
            normalized[name.strip()] = _normalized_values(values)
        return dict(sorted(normalized.items()))

    def is_empty(self) -> bool:
        return not self.languages and not self.classifications


class SearchCriteria(BaseModel):
    """The submitted query and filters shared by Search, document browsing and Analytics
    (docs/EXPLORATION.md). Retrieval settings belong to each endpoint's request."""
    model_config = ConfigDict(extra="forbid")

    text_query: str | None = Field(None, max_length=MAX_TEXT_QUERY_LENGTH)
    """Free text; blank means none. Not the document-title filter."""
    document_filters: DocumentFilters = Field(default_factory=DocumentFilters)
    chunk_filters: ChunkFilters = Field(default_factory=ChunkFilters)

    @field_validator("text_query")
    @classmethod
    def _text_query(cls, text: str | None) -> str | None:
        return text.strip() or None if text is not None else None


##############
# Validation #
##############

@dataclass(frozen=True)
class ChunkVocabulary:
    """The values chunk filters may select, as configured (``features/search/filters``)."""
    languages: tuple[str, ...] = ()
    classifications: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


class InvalidChunkFilterError(InvalidRequestError):
    """A chunk filter names a classification or a value that is not configured (400)."""


class ChunkFiltersUnavailable(Exception):
    """The operation cannot apply chunk filters yet (422): rejected, never ignored or answered with 0."""

    def __init__(self, operation: str):
        super().__init__(
            f"{operation} cannot be restricted by chunk filters (chunk language or classifications) yet; "
            "remove them or search passages instead.")


def reject_chunk_filters(filters: ChunkFilters | None, operation: str) -> None:
    """Document-level operations until #529: raises ``ChunkFiltersUnavailable`` for any chunk filter."""
    if filters is not None and not filters.is_empty():
        raise ChunkFiltersUnavailable(operation)


def validate_chunk_filters(filters: ChunkFilters, vocabulary: ChunkVocabulary) -> ChunkFilters:
    """``filters`` with every value in its configured spelling; raises ``InvalidChunkFilterError``
    for a classification or value that is not configured. Values are compared ignoring case."""
    def canonical(name: str, values: Sequence[str], allowed: Sequence[str]) -> list[str]:
        by_key = {value.casefold(): value for value in allowed}
        for value in values:
            if value.casefold() not in by_key:
                raise InvalidChunkFilterError(
                    f"Invalid chunk filter value: '{value}' is not a valid option for '{name}'. "
                    f"Valid choices are: {', '.join(sorted(allowed))}.")
        return sorted({by_key[value.casefold()] for value in values})

    unknown = sorted(set(filters.classifications) - set(vocabulary.classifications))
    if unknown:
        raise InvalidChunkFilterError(
            f"Invalid chunk filter: '{unknown[0]}' is not a configured classification. "
            f"Available classifications are: {', '.join(sorted(vocabulary.classifications))}.")
    return ChunkFilters(
        languages=canonical("languages", filters.languages, vocabulary.languages),
        classifications={name: canonical(name, values, vocabulary.classifications[name])
                         for name, values in filters.classifications.items()})


##############
# Predicates #
##############

@dataclass(frozen=True)
class NumberRange:
    """The property's value lies from ``minimum`` to ``maximum``, both inclusive (either may be
    open). A record without a value never matches."""
    prop: str
    minimum: int | None = None
    maximum: int | None = None


@dataclass(frozen=True)
class ContainsWords:
    """For at least one alternative, every word of it occurs inside some word of the property's
    text (``like("*word*")`` per word), in any order. Case-insensitive and diacritics-sensitive
    with ``word`` tokenization. The words must contain no ``*`` or ``?``, which ``like`` reads
    as wildcards."""
    prop: str
    alternatives: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class AnyOf:
    """The property equals one of the values. ``equal`` follows the property's tokenization:
    with ``word``, ``"ces"`` also matches ``"CES"``; with ``field``, only surrounding
    whitespace is ignored."""
    prop: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class CategoryIn:
    """The property (one value or a list) holds one of ``values`` exactly. ``others`` are the
    remaining configured values of the same filter: where the store matches by word, a value
    whose words all occur in another value (``easy`` in ``very_easy``) would otherwise also
    match that one (``adapters/weaviate/criteria.py``)."""
    prop: str
    values: tuple[str, ...]
    others: tuple[str, ...] = ()


Condition = NumberRange | ContainsWords | AnyOf | CategoryIn


def document_conditions(filters: DocumentFilters) -> list[Condition]:
    """The predicates on document properties that ``filters`` mean."""
    conditions: list[Condition] = []
    if filters.year_min is not None or filters.year_max is not None:
        conditions.append(NumberRange(YEAR_PROPERTY, filters.year_min, filters.year_max))
    if filters.title_contains:
        conditions.append(ContainsWords(TITLE_PROPERTY, filters.title_alternatives()))
    if filters.libraries:
        conditions.append(AnyOf(LIBRARY_PROPERTY, tuple(filters.libraries)))
    if filters.languages:
        conditions.append(AnyOf(LANGUAGE_PROPERTY, tuple(filters.languages)))
    return conditions


def chunk_conditions(filters: ChunkFilters, vocabulary: ChunkVocabulary) -> list[CategoryIn]:
    """The predicates on chunk properties that validated ``filters`` mean; all hold on one chunk."""
    def category(prop: str, values: Sequence[str], allowed: Sequence[str]) -> CategoryIn:
        return CategoryIn(prop, tuple(values), tuple(v for v in allowed if v not in values))

    conditions = []
    if filters.languages:
        conditions.append(category(LANGUAGE_PROPERTY, filters.languages, vocabulary.languages))
    for name, values in filters.classifications.items():
        conditions.append(category(name, values, vocabulary.classifications.get(name, ())))
    return conditions
