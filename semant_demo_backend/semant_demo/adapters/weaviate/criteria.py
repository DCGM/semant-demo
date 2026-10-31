"""Weaviate filters for the search-criteria predicates (``features/documents/criteria.py``).

One rendering serves every collection that is filtered by the criteria: ``Documents``
(Analytics counts and document browsing) and ``Chunks`` (Search). For chunks, document
predicates go through the ``document`` reference, which ``target`` names; the caller decides.

A predicate is checked against the property as the store declares it; one the store cannot
evaluate raises ``UnavailableFilter`` (422 at the routes), so a missing property is never
answered with zero matches.

Exact categories (``CategoryIn``): with ``field`` tokenization ``contains_any`` matches whole
values. With ``word`` tokenization (Weaviate's default, which the stored chunk classifications
have) it matches words, so ``easy`` also matches ``very_easy``. Such a value is then required
without each configured value that contains all of its words. A record holding both values
(``["easy", "very_easy"]``) cannot be told apart from one holding only the longer value, and is
not found by the shorter one. Stored values are also compared ignoring case there.
"""
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Literal

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.features.documents.criteria import AnyOf, CategoryIn, Condition, ContainsWords, NumberRange

DataTypes = Mapping[str, str]
"""Declared data type per property name (``"text"``, ``"text[]"``, ``"int"``, ``"number"``, ...)."""
Tokenizations = Mapping[str, str]
"""Declared tokenization per text property name (``"word"``, ``"field"``, ...)."""
Target = Callable[[str], object]
"""The filter target of a property name: ``Filter.by_property`` or a reference path to it."""

_ACCEPTED_TYPES: dict[type, set[str]] = {
    NumberRange: {"int", "number"},
    ContainsWords: {"text"},
    AnyOf: {"text"},
    CategoryIn: {"text", "text[]"},
}

_WORD = re.compile(r"[^\W_]+")
"""How ``word`` tokenization splits a value (into runs of letters and digits)."""


class UnavailableFilter(Exception):
    """A condition names a property that the store does not declare or that is not a single
    value of the expected kind; the records cannot be filtered by it (never answered with 0)."""

    def __init__(self, prop: str, reason: Literal["missing", "unsupported_type"], records: str = "Documents"):
        detail = "is not recorded" if reason == "missing" else "is not recorded as a single value"
        super().__init__(f"{records} cannot be filtered by {prop}: this corpus database {detail}.")
        self.prop = prop
        self.reason = reason


async def declared(client: WeaviateAsyncClient, collection: str) -> tuple[dict[str, str], dict[str, str]]:
    """(data types, tokenizations) of the collection's properties as the store declares them;
    the collection name may be an alias."""
    config = await client.collections.get(await resolve_collection(client, collection)).config.get()
    return ({p.name: p.data_type.value for p in config.properties},
            {p.name: p.tokenization.value for p in config.properties if p.tokenization is not None})


def unavailable(condition: Condition, types: DataTypes) -> Literal["missing", "unsupported_type"] | None:
    data_type = types.get(condition.prop)
    if data_type is None:
        return "missing"
    return None if data_type in _ACCEPTED_TYPES[type(condition)] else "unsupported_type"


def parts(conditions: Sequence[Condition], types: DataTypes, tokenizations: Tokenizations | None = None,
          target: Target = Filter.by_property, records: str = "Documents") -> list:
    """One Weaviate filter per condition (one per range bound). ``types`` are the declared data
    types: a range on an ``int`` property is compared with whole numbers and on a ``number``
    property with floats, as Weaviate expects each. Raises ``UnavailableFilter``."""
    result = []
    for condition in conditions:
        reason = unavailable(condition, types)
        if reason:
            raise UnavailableFilter(condition.prop, reason, records)
        prop = target(condition.prop)
        if isinstance(condition, NumberRange):
            value = int if types[condition.prop] == "int" else float
            if condition.minimum is not None:
                result.append(prop.greater_or_equal(value(condition.minimum)))
            if condition.maximum is not None:
                result.append(prop.less_or_equal(value(condition.maximum)))
        elif isinstance(condition, ContainsWords):
            result.append(Filter.any_of([Filter.all_of([prop.like(f"*{word}*") for word in words])
                                         for words in condition.alternatives]))
        elif isinstance(condition, AnyOf):
            result.append(Filter.any_of([prop.equal(value) for value in condition.values]))
        else:
            word = (tokenizations or {}).get(condition.prop, "word") != "field"
            result.append(_category(condition, prop, target, word))
    return result


def where(conditions: Sequence[Condition], types: DataTypes, tokenizations: Tokenizations | None = None,
          target: Target = Filter.by_property, records: str = "Documents"):
    """One Weaviate filter requiring every condition (``None`` without conditions)."""
    found = parts(conditions, types, tokenizations, target, records)
    if not found:
        return None
    return Filter.all_of(found) if len(found) > 1 else found[0]


def word_supersets(value: str, others: Sequence[str]) -> list[str]:
    """The ``others`` containing every word of ``value``, which ``word`` matching confuses with it."""
    words = set(_WORD.findall(value.casefold()))
    return [other for other in others
            if other.casefold() != value.casefold() and words <= set(_WORD.findall(other.casefold()))]


def _category(condition: CategoryIn, prop, target: Target, word: bool):
    if not word:
        return prop.contains_any(list(condition.values))
    alternatives = []
    for value in condition.values:
        match = prop.contains_any([value])
        confused = word_supersets(value, condition.others)
        alternatives.append(Filter.all_of([match, Filter.not_(target(condition.prop).contains_any(confused))])
                            if confused else match)
    return Filter.any_of(alternatives) if len(alternatives) > 1 else alternatives[0]
