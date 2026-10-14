"""Document counts for the corpus overview (#254): native aggregates over ``Documents``.

Only aggregates are run: no objects, texts or vectors are read, and documents are counted
directly (never through their chunks). A single-valued property is described by the number
of documents that have a value (``known``, empty strings included) and the documents per
distinct value, most frequent first; documents without a value are ``total - known``.
Weaviate's ``is_none`` filter needs an indexed null state, which the deployed collections
lack, so missing values are never counted directly.

The collection name is resolved through an alias for the schema read (the deployment serves
``Documents`` as an alias of ``Documents_test``). Never creates or alters a collection.
"""
import asyncio
from dataclasses import dataclass
from typing import Literal

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Metrics

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

    async def count_documents(self, properties: dict[str, ValueKind], group_limit: int) -> DocumentCounts:
        """The number of documents and, for each property, its value counts (at most
        ``group_limit`` values each). One aggregate reads the total and every property's
        ``known`` count together; then one grouped aggregate per property, concurrently."""
        types = await self._property_types()
        result: dict[str, ValueCounts | Unavailable] = {}
        countable: dict[str, str] = {}
        for prop, kind in properties.items():
            data_type = types.get(prop)
            if data_type is None:
                result[prop] = Unavailable("missing")
            elif data_type not in _DATA_TYPES[kind]:
                result[prop] = Unavailable("unsupported_type")
            else:
                countable[prop] = data_type

        documents = self._documents()
        metrics = [_count_metric(prop, data_type) for prop, data_type in countable.items()]
        overall = await documents.aggregate.over_all(total_count=True, return_metrics=metrics or None)
        grouped_all = await asyncio.gather(*(documents.aggregate.over_all(
            group_by=GroupByAggregate(prop=prop, limit=group_limit), total_count=True) for prop in countable))
        for prop, grouped in zip(countable, grouped_all):
            groups = [(group.grouped_by.value, group.total_count or 0) for group in grouped.groups]
            result[prop] = ValueCounts(known=overall.properties[prop].count or 0, groups=groups,
                                       complete=len(groups) < group_limit)
        return DocumentCounts(total=overall.total_count or 0, properties=result)


def _count_metric(prop: str, data_type: str):
    metric = Metrics(prop)
    if data_type == "text":
        return metric.text(count=True)
    if data_type == "int":
        return metric.integer(count=True)
    return metric.number(count=True)
