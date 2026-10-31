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
from weaviate.classes.query import Metrics

from semant_demo.adapters.weaviate.criteria import UnavailableFilter, declared, where
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.documents.criteria import AnyOf, Condition, ContainsWords, NumberRange

__all__ = ["AnyOf", "Condition", "ContainsWords", "CorpusAnalyticsRepository", "DocumentCounts", "NumberRange",
           "Unavailable", "UnavailableFilter", "ValueCounts", "where"]

ValueKind = Literal["text", "number"]

_DATA_TYPES: dict[ValueKind, set[str]] = {"text": {"text"}, "number": {"int", "number"}}


@dataclass(frozen=True)
class Unavailable:
    """The property cannot be counted: not declared (``missing``) or not a single value of the
    expected kind (``unsupported_type``, e.g. ``text[]``, where a document has several values)."""
    reason: Literal["missing", "unsupported_type"]


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


PER_VALUE_CONCURRENCY = 4
"""Most per-value counts (``count_documents_per_value``) running at once over all requests of
one repository, i.e. of the application: the endpoint using it is public, and each count
sends one aggregate per property plus one."""


class CorpusAnalyticsRepository:
    def __init__(self, client: WeaviateAsyncClient, collection_names: CollectionNames):
        self.client = client
        self.collection_names = collection_names
        self.per_value_slots = asyncio.Semaphore(PER_VALUE_CONCURRENCY)

    def _documents(self):
        return self.client.collections.get(self.collection_names.document_collection_name)

    async def _property_types(self) -> dict[str, str]:
        types, _ = await declared(self.client, self.collection_names.document_collection_name)
        return types

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
        values that match the same documents must be passed once). At most
        ``PER_VALUE_CONCURRENCY`` values are counted at once, also across concurrent calls.
        Weaviate groups by one property only, so this is how two properties are crossed."""
        types = await self._property_types()
        filters = [where([*conditions, AnyOf(prop, (value,))], types) for value in values]

        async def count(value_filter) -> DocumentCounts:
            async with self.per_value_slots:
                return await self._count(value_filter, properties, types, group_limit)

        counts = await asyncio.gather(*(count(value_filter) for value_filter in filters))
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


def _count_metric(prop: str, data_type: str):
    metric = Metrics(prop)
    if data_type == "text":
        return metric.text(count=True)
    if data_type == "int":
        return metric.integer(count=True)
    return metric.number(count=True)
