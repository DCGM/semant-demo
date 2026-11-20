"""Document counts for the corpus overview (#254): native aggregates over ``Documents``; and
the counts of the passages included in a user collection (#807): native aggregates over
``Chunks``.

Only aggregates are run: no objects, texts or vectors are read, and documents are counted
directly (never through their chunks). A single-valued property is described by the number
of documents that have a value (``known``, empty strings included) and the documents per
distinct value, most frequent first; documents without a value are ``total - known``.
Optional conditions (#361) and a user collection (#622, the documents linked to it) restrict
every count to the same documents: one filter is built once (``_restriction``) and applied to
the total, to each grouped aggregate and to each per-value count.

The documents of a ranked search result (#619) are few (at most a configured cap) and named by
id: ``document_values`` reads the values of just those documents, in batches, for the service
to count; still no texts or vectors. Weaviate's ``is_none`` filter needs an indexed null state, which the deployed collections
lack, so missing values are never counted directly.

Access (#279): counts without a collection cover only public documents (``Documents.public``
true), the population of unscoped Search and Explore; the filter is part of every aggregate, so
no restricted or unknown document is ever counted. Counts and ``document_values`` with a
collection cover that (authorized) collection's documents whatever their rights.

The included passages of a user collection (#807) are the chunks linked to it
(``Chunks.userCollection``), counted directly: their total, their detected language and their
values of one classification (``text[]``: a passage counts once per distinct value it holds).
Like the collection's documents, they are counted whatever their documents' rights (#279):
only readers of the collection ask.

The collection name is resolved through an alias for the schema read (the deployment serves
``Documents`` as an alias of ``Documents_test``). Never creates or alters a collection.
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Literal, Sequence
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter, Metrics

from semant_demo.adapters.weaviate.criteria import UnavailableFilter, declared, where
from semant_demo.adapters.weaviate.documents import public_documents
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.documents.criteria import AnyOf, Condition, ContainsWords, NumberRange

__all__ = ["AnyOf", "Condition", "ContainsWords", "CorpusAnalyticsRepository", "DocumentCounts", "NumberRange",
           "PassageCounts", "READ_BATCH", "Unavailable", "UnavailableFilter", "ValueCounts", "where"]

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


@dataclass(frozen=True)
class PassageCounts:
    """The included passages of a user collection (#807) and their values of one property; in
    ``counts`` every number is of passages, not documents."""
    total: int
    counts: ValueCounts | Unavailable


READ_BATCH = 1000
"""Most ids one read by id names (``document_values``; ``ChunkSearchRepository.document_values``):
a ranked result may hold more than Weaviate returns at once (``QUERY_MAXIMUM_RESULTS``)."""

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

    async def _declared(self) -> tuple[dict[str, str], dict[str, str]]:
        return await declared(self.client, self.collection_names.document_collection_name)

    async def count_documents(self, properties: dict[str, ValueKind], group_limit: int,
                              conditions: Sequence[Condition] = (), collection_id: UUID | None = None) -> DocumentCounts:
        """The number of documents meeting every condition (and linked to the collection, if
        given) and, for each property, their value counts (at most ``group_limit`` values each).
        One aggregate reads the total and every property's ``known`` count together, one grouped
        aggregate per property runs alongside. Raises ``UnavailableFilter`` when a condition's
        property cannot be filtered."""
        types, tokenizations = await self._declared()
        return await self._count(_restriction(conditions, collection_id, types, tokenizations), properties, types,
                                 group_limit)

    async def count_documents_per_value(self, prop: str, values: Sequence[str], properties: dict[str, ValueKind],
                                        group_limit: int, conditions: Sequence[Condition] = (),
                                        collection_id: UUID | None = None) -> dict[str, DocumentCounts]:
        """``count_documents`` for each value of ``prop`` separately: the documents meeting every
        condition (and linked to the collection, if given) that also equal the value (``AnyOf``,
        so the property's tokenization applies; values that match the same documents must be
        passed once). At most ``PER_VALUE_CONCURRENCY`` values are counted at once, also across
        concurrent calls. Weaviate groups by one property only, so this is how two properties are
        crossed."""
        types, tokenizations = await self._declared()
        filters = [_restriction([*conditions, AnyOf(prop, (value,))], collection_id, types, tokenizations)
                   for value in values]

        async def count(value_filter) -> DocumentCounts:
            async with self.per_value_slots:
                return await self._count(value_filter, properties, types, group_limit)

        counts = await asyncio.gather(*(count(value_filter) for value_filter in filters))
        return dict(zip(values, counts))

    async def availability(self, properties: dict[str, ValueKind]) -> dict[str, Unavailable | None]:
        """For each document property, why it cannot be counted, or None when it can."""
        types, _ = await self._declared()
        return {prop: (Unavailable(reason) if (reason := _unavailable(types.get(prop), kind)) else None)
                for prop, kind in properties.items()}

    async def document_values(self, ids: Sequence[UUID], properties: Sequence[str], collection_id: UUID | None = None,
                              conditions: Sequence[Condition] = ()) -> dict[UUID, dict[str, Any]]:
        """The stored values of ``properties`` (each declared, see ``availability``) of the
        documents among ``ids`` that belong to the collection, if given (otherwise that are
        public), and meet every condition;
        the others, also ids of no document, are left out. Read in batches of ``READ_BATCH``.
        Raises ``UnavailableFilter`` when a condition's property cannot be filtered."""
        types, tokenizations = await self._declared()
        restriction = _restriction(conditions, collection_id, types, tokenizations)
        documents = self._documents()

        async def read(batch: Sequence[UUID]) -> list:
            by_ids = Filter.by_id().contains_any(list(batch))
            response = await documents.query.fetch_objects(
                filters=by_ids & restriction, limit=len(batch),
                return_properties=list(properties))
            return response.objects

        batches = await asyncio.gather(*(read(ids[i:i + READ_BATCH]) for i in range(0, len(ids), READ_BATCH)))
        return {UUID(str(o.uuid)): {prop: o.properties.get(prop) for prop in properties}
                for objects in batches for o in objects}

    # Included passages of a user collection (#807): aggregates over ``Chunks``, never over the
    # chunks of the collection's documents. No semaphore: only readers of the collection ask, and
    # one request sends at most three aggregates.

    def _chunks(self):
        return self.client.collections.get(self.collection_names.chunks_collection_name)

    def _included(self, collection_id: UUID):
        """The passages included in the collection (``Chunks.userCollection``), as
        ``CollectionStats.chunks_count`` counts them."""
        return Filter.by_ref(self.collection_names.user_collection_link_name).by_id().equal(collection_id)

    async def count_passage_languages(self, collection_id: UUID, prop: str, group_limit: int) -> PassageCounts:
        """The collection's included passages and their values of the single-valued text
        property ``prop`` (``known``: passages with a value, empty strings included)."""
        types, _ = await declared(self.client, self.collection_names.chunks_collection_name)
        chunks, included = self._chunks(), self._included(collection_id)
        reason = _unavailable(types.get(prop), "text")
        if reason:
            return PassageCounts(await _total(chunks, included), Unavailable(reason))
        overall, grouped = await asyncio.gather(
            chunks.aggregate.over_all(filters=included, total_count=True, return_metrics=[_count_metric(prop, "text")]),
            chunks.aggregate.over_all(filters=included, group_by=GroupByAggregate(prop=prop, limit=group_limit),
                                      total_count=True))
        groups = _groups(grouped)
        return PassageCounts(overall.total_count or 0, ValueCounts(known=overall.properties[prop].count or 0,
                                                                   groups=groups, complete=len(groups) < group_limit))

    async def count_passage_values(self, collection_id: UUID, prop: str, vocabulary: Sequence[str],
                                   group_limit: int) -> PassageCounts:
        """The collection's included passages and their values of the multi-valued ``text[]``
        property ``prop``: a passage counts once per distinct value it holds (groups are whole
        stored values), and ``known`` is the passages matching any value of ``vocabulary``. That
        filter matches words (``word`` tokenization, #533), so ``known`` is exact as long as every
        stored value is in the vocabulary: a passage then matches exactly when it holds a value."""
        types, _ = await declared(self.client, self.collection_names.chunks_collection_name)
        chunks, included = self._chunks(), self._included(collection_id)
        data_type = types.get(prop)
        if data_type != "text[]":
            return PassageCounts(await _total(chunks, included),
                                 Unavailable("missing" if data_type is None else "unsupported_type"))
        configured = Filter.all_of([included, Filter.by_property(prop).contains_any(list(vocabulary))])
        total, known, grouped = await asyncio.gather(
            _total(chunks, included),
            _total(chunks, configured) if vocabulary else _zero(),
            chunks.aggregate.over_all(filters=included, group_by=GroupByAggregate(prop=prop, limit=group_limit),
                                      total_count=True))
        groups = _groups(grouped)
        return PassageCounts(total, ValueCounts(known=known, groups=groups, complete=len(groups) < group_limit))

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
            groups = _groups(grouped)
            result[prop] = ValueCounts(known=overall.properties[prop].count or 0, groups=groups,
                                       complete=len(groups) < group_limit)
        return DocumentCounts(total=overall.total_count or 0, properties=result)


def _restriction(conditions: Sequence[Condition], collection_id: UUID | None, types: dict[str, str],
                 tokenizations: dict[str, str]):
    """The one filter of the counted documents: every condition and, with a collection, a link
    to it (``Documents.collection``, as the collection's document list and ``CollectionStats``
    read it); without a collection, the public documents only (#279)."""
    criteria = where(conditions, types, tokenizations)
    scope = (public_documents() if collection_id is None
             else Filter.by_ref("collection").by_id().equal(collection_id))
    return scope if criteria is None else Filter.all_of([scope, criteria])


async def _total(collection, filters) -> int:
    return (await collection.aggregate.over_all(filters=filters, total_count=True)).total_count or 0


async def _zero() -> int:
    return 0


def _groups(grouped) -> list[tuple[str | float, int]]:
    return [(group.grouped_by.value, group.total_count or 0) for group in grouped.groups]


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
