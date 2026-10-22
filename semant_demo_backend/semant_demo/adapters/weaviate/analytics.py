"""Document counts for the corpus overview (#254): native aggregates over ``Documents``.

Only aggregates are run: no objects, texts or vectors are read, and documents are counted
directly (never through their chunks). A single-valued property is described by the number
of documents that have a value (``known``, empty strings included) and the documents per
distinct value, most frequent first; documents without a value are ``total - known``.
Optional conditions (#361) restrict every count to the same documents: one filter is built
once and applied to the total and to each grouped aggregate. Weaviate's ``is_none`` filter needs an indexed null state, which the deployed collections
lack, so missing values are never counted directly.

The collection name is resolved through an alias for the schema read (the deployment serves
``Documents`` as an alias of ``Documents_test``). Never creates or alters a collection.
"""
import asyncio
from dataclasses import dataclass
from typing import Literal, Sequence

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter, Metrics

from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames

ValueKind = Literal["text", "number"]

_DATA_TYPES: dict[ValueKind, set[str]] = {"text": {"text"}, "number": {"int", "number"}}


@dataclass(frozen=True)
class Unavailable:
    """The property cannot be counted: not declared (``missing``) or not a single value of the
    expected kind (``unsupported_type``, e.g. ``text[]``, where a document has several values)."""
    reason: Literal["missing", "unsupported_type"]


@dataclass(frozen=True)
class NumberRange:
    """The property's value lies from ``minimum`` to ``maximum``, both inclusive (either may be
    open). A document without a value never matches."""
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


Condition = NumberRange | ContainsWords | AnyOf

_CONDITION_KINDS: dict[type, ValueKind] = {NumberRange: "number", ContainsWords: "text", AnyOf: "text"}


class UnavailableFilter(Exception):
    """A condition names a property that the store does not declare or that is not a single
    value of the expected kind; the documents cannot be filtered by it (never answered with 0)."""

    def __init__(self, prop: str, reason: Literal["missing", "unsupported_type"]):
        detail = "is not recorded" if reason == "missing" else "is not recorded as a single value"
        super().__init__(f"Documents cannot be filtered by {prop}: this corpus database {detail}.")
        self.prop = prop
        self.reason = reason


@dataclass(frozen=True)
class ValueCounts:
    known: int
    """Documents with a value of the property."""
    groups: list[tuple[str | float, int]]
    """(value, documents) per distinct value, most documents first; at most the requested limit."""
    complete: bool
    """False when the limit cut off further values."""


@dataclass(frozen=True)
class DocumentCounts:
    total: int
    properties: dict[str, ValueCounts | Unavailable]


class CorpusAnalyticsRepository:
    def __init__(self, client: WeaviateAsyncClient, collection_names: CollectionNames):
        self.client = client
        self.collection_names = collection_names

    def _documents(self):
        return self.client.collections.get(self.collection_names.document_collection_name)

    async def _property_types(self) -> dict[str, str]:
        name = await resolve_collection(self.client, self.collection_names.document_collection_name)
        config = await self.client.collections.get(name).config.get()
        return {prop.name: prop.data_type.value for prop in config.properties}

    async def count_documents(self, properties: dict[str, ValueKind], group_limit: int,
                              conditions: Sequence[Condition] = ()) -> DocumentCounts:
        """The number of documents meeting every condition and, for each property, their value
        counts (at most ``group_limit`` values each). One aggregate reads the total and every
        property's ``known`` count together, one grouped aggregate per property runs alongside.
        Raises ``UnavailableFilter`` when a condition's property cannot be filtered."""
        types = await self._property_types()
        return await self._count(where(conditions, types), properties, types, group_limit)

    async def count_documents_per_value(self, prop: str, values: Sequence[str], properties: dict[str, ValueKind],
                                        group_limit: int, conditions: Sequence[Condition] = ()) -> dict[str, DocumentCounts]:
        """``count_documents`` for each value of ``prop`` separately: the documents meeting every
        condition that also equal the value (``AnyOf``, so the property's tokenization applies;
        values that match the same documents must be passed once). All values run concurrently.
        Weaviate groups by one property only, so this is how two properties are crossed."""
        types = await self._property_types()
        counts = await asyncio.gather(*(
            self._count(where([*conditions, AnyOf(prop, (value,))], types), properties, types, group_limit)
            for value in values))
        return dict(zip(values, counts))

    async def _count(self, filters, properties: dict[str, ValueKind], types: dict[str, str],
                     group_limit: int) -> DocumentCounts:
        result: dict[str, ValueCounts | Unavailable] = {}
        countable: dict[str, str] = {}
        for prop, kind in properties.items():
            unavailable = _unavailable(types.get(prop), kind)
            if unavailable:
                result[prop] = Unavailable(unavailable)
            else:
                countable[prop] = types[prop]

        documents = self._documents()
        metrics = [_count_metric(prop, data_type) for prop, data_type in countable.items()]
        overall, *grouped_all = await asyncio.gather(
            documents.aggregate.over_all(filters=filters, total_count=True, return_metrics=metrics or None),
            *(documents.aggregate.over_all(filters=filters, group_by=GroupByAggregate(prop=prop, limit=group_limit),
                                           total_count=True) for prop in countable))
        for prop, grouped in zip(countable, grouped_all):
            groups = [(group.grouped_by.value, group.total_count or 0) for group in grouped.groups]
            result[prop] = ValueCounts(known=overall.properties[prop].count or 0, groups=groups,
                                       complete=len(groups) < group_limit)
        return DocumentCounts(total=overall.total_count or 0, properties=result)


def _unavailable(data_type: str | None, kind: ValueKind) -> Literal["missing", "unsupported_type"] | None:
    if data_type is None:
        return "missing"
    return None if data_type in _DATA_TYPES[kind] else "unsupported_type"


def where(conditions: Sequence[Condition], types: dict[str, str]):
    """One Weaviate filter requiring every condition (``None`` without conditions). ``types``
    are the declared data types; a range on an ``int`` property is compared with whole
    numbers and on a ``number`` property with floats, as Weaviate expects each."""
    parts = []
    for condition in conditions:
        unavailable = _unavailable(types.get(condition.prop), _CONDITION_KINDS[type(condition)])
        if unavailable:
            raise UnavailableFilter(condition.prop, unavailable)
        prop = Filter.by_property(condition.prop)
        if isinstance(condition, NumberRange):
            value = int if types[condition.prop] == "int" else float
            if condition.minimum is not None:
                parts.append(prop.greater_or_equal(value(condition.minimum)))
            if condition.maximum is not None:
                parts.append(prop.less_or_equal(value(condition.maximum)))
        elif isinstance(condition, ContainsWords):
            parts.append(Filter.any_of([Filter.all_of([prop.like(f"*{word}*") for word in words])
                                        for words in condition.alternatives]))
        else:
            parts.append(Filter.any_of([prop.equal(value) for value in condition.values]))
    return Filter.all_of(parts) if parts else None


def _count_metric(prop: str, data_type: str):
    metric = Metrics(prop)
    if data_type == "text":
        return metric.text(count=True)
    if data_type == "int":
        return metric.integer(count=True)
    return metric.number(count=True)
