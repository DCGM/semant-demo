"""Chunk retrieval: neutral ``ChunkQuery`` -> Weaviate BM25/near-vector/hybrid query -> chunks.

Owns filter translation, the choice of query call, the returned references/properties and
the mapping of result objects. Embeddings are computed by the caller (``query.vector``),
which also names the stored vector to compare with (``query.target_vector``); every
vector and hybrid query names it, so a collection with several named vectors works. No
provider is called and no configuration is read here.
"""
import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import Metrics
from weaviate.classes.query import Filter, HybridFusion, QueryReference

from semant_demo.adapters.weaviate import criteria
from semant_demo.adapters.weaviate.analytics import READ_BATCH
from semant_demo.adapters.weaviate.chunk_visibility import PROPERTY as DOCUMENT_PUBLIC_FLAG
from semant_demo.adapters.weaviate.documents import chunk_properties, public_documents
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.search.filters import TASK_CLASSES
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, SearchType, SearchResultChunk
from semant_demo.features.documents.schemas import Document

# Fields stored on the chunk's document, not on the chunk; filtered through the reference.
# ``yearIssued`` is not among them: the chunks store a copy (maintenance/chunk_year.py),
# because range predicates through the reference give wrong results (#153).
DOCUMENT_FIELDS = {
    "dateIssued", "documentType", "publisher", "placeTerm",
    "genre", "public", "url", "library", "title", "subTitle", "partNumber",
    "partName", "authors", "description", "keywords", "section", "region", "id_code"
}

# Document properties whose criteria predicates (``ChunkQuery.document_conditions``) are evaluated
# on the chunk's own copy, not through the reference (#153).
CHUNK_COPIES = {"yearIssued"}

# Document properties returned with each hit: the fields of the document model that the store's
# document collection has (``ChunkSearchRepository._document_properties``). Weaviate 1.40 refuses
# a query naming a property the schema lacks (1.34 ignored it), and stores differ (#312).
DOCUMENT_PROPERTIES = [name for name in Document.model_fields if name != "id"]

class ChunkSearchRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: CollectionNames,
                 fusion: HybridFusion | None = None, query_properties: Sequence[str] | None = None):
        self.client = client
        self.collectionNames = collectionNames
        self.fusion = fusion
        """Hybrid fusion; None: Weaviate's default (relative score). The application never sets
        it; the search relevance benchmark compares both (#712)."""
        self.query_properties = list(query_properties) if query_properties is not None else None
        """The properties BM25 (text and the keyword part of hybrid) searches, each optionally
        boosted (``"title^2"``); None: every text property, Weaviate's default. The application
        never sets it; the search relevance benchmark compares properties and boosts (#712)."""
        self._returned_document_properties: list[str] | None = None
        self._schema: tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]] | None = None

    async def _document_properties(self) -> list[str]:
        """``DOCUMENT_PROPERTIES`` that the document collection has; read once, then cached.

        A property added to the schema later is returned after the application restarts.
        """
        if self._returned_document_properties is None:
            config = await self.client.collections.get(self.collectionNames.document_collection_name).config.get(
                simple=True)
            stored = {p.name for p in config.properties}
            self._returned_document_properties = [name for name in DOCUMENT_PROPERTIES if name in stored]
        return self._returned_document_properties

    async def _declared(self) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
        """(document data types, document tokenizations, chunk data types, chunk tokenizations) by
        property name, as the store declares them; read once, then cached (a schema change needs a
        restart)."""
        if self._schema is None:
            document_types, document_tokenizations = await criteria.declared(
                self.client, self.collectionNames.document_collection_name)
            chunk_types, chunk_tokenizations = await criteria.declared(
                self.client, self.collectionNames.chunks_collection_name)
            self._schema = (document_types, document_tokenizations, chunk_types, chunk_tokenizations)
        return self._schema

    async def search(self, query: ChunkQuery) -> list[SearchResultChunk]:
        """Top ``query.limit`` chunks matching every condition, best first.

        Chunks without a document reference are left out. Raises ``criteria.UnavailableFilter``
        for a criteria predicate on a property the store does not declare (or not as expected).
        """
        result = await self._ranked(query, return_references=[QueryReference(
            link_on="document", return_properties=await self._document_properties())])
        return [hit for hit in map(_hit, result.objects) if hit is not None]

    async def ranked_ids(self, query: ChunkQuery) -> list[UUID]:
        """Ids of the top ``query.limit`` chunks matching every condition, best first; no
        properties or references are read. Pages of one ranking are slices of it (#605):
        Weaviate's hybrid ranking depends on the limit, and hybrid ``offset`` does not reach
        past its first results (measured on 1.40.1), so a page is never a query of its own."""
        result = await self._ranked(query, return_properties=[])
        return [obj.uuid for obj in result.objects]

    async def ranked_documents(self, query: ChunkQuery) -> list[tuple[UUID, UUID | None]]:
        """(chunk id, document id) of the top ``query.limit`` chunks matching every condition, best
        first; only the document reference is read. A document is ranked by its best chunk where
        it first appears (#607). Every hit is returned, a chunk without a document reference with
        ``None``: whether the limit cut the ranking is told by the hits, not by the documents found.

        Not Weaviate's ``group_by`` on the reference: on 1.40.1 BM25 and hybrid search return no
        groups at all, and vector search groups only the first ``limit`` chunks
        (``tests/integration/test_document_search_benchmark.py``)."""
        result = await self._ranked(query, return_properties=[],
                                    return_references=[QueryReference(link_on="document", return_properties=[])])
        hits: list[tuple[UUID, UUID | None]] = []
        for obj in result.objects:
            refs = (obj.references or {}).get("document")
            hits.append((obj.uuid, refs.objects[0].uuid if refs and refs.objects else None))
        return hits

    async def read_hits(self, ids: list[UUID], scope: ChunkQuery) -> list[SearchResultChunk]:
        """The chunks ``ids`` that match every condition of ``scope`` (its text, mode and limit
        do not apply) as search hits, in the order of ``ids``. Chunks gone meanwhile, outside
        the scope or without a document reference are left out: read under the ranking's own
        restrictions, ids from a client never reach a chunk that ranking could not (#611)."""
        if not ids:
            return []
        chunks = self.client.collections.get(self.collectionNames.chunks_collection_name)
        restrictions = await self._filter(scope)
        by_ids = Filter.by_id().contains_any(ids)
        result = await chunks.query.fetch_objects(
            filters=by_ids if restrictions is None else Filter.all_of([by_ids, restrictions]), limit=len(ids),
            return_references=[QueryReference(link_on="document", return_properties=await self._document_properties())])
        by_id = {obj.uuid: obj for obj in result.objects}
        hits = (_hit(by_id[i]) for i in ids if i in by_id)
        return [hit for hit in hits if hit is not None]

    async def document_values(self, ids: Sequence[UUID], scope: ChunkQuery,
                              properties: Sequence[str]) -> list[tuple[UUID, UUID, dict[str, Any]]]:
        """(chunk id, document id, the document's stored ``properties``) of the chunks ``ids`` that
        match every condition of ``scope``, as ``read_hits`` reads them (#619): chunks gone, outside
        the scope or without a document are left out, in the order of ``ids``. Only the document
        reference and the named document properties are read (no text, no vectors), in batches of
        ``READ_BATCH`` ids; every property must be declared on the documents."""
        chunks = self.client.collections.get(self.collectionNames.chunks_collection_name)
        restrictions = await self._filter(scope)

        async def read(batch: Sequence[UUID]) -> list:
            by_ids = Filter.by_id().contains_any(list(batch))
            result = await chunks.query.fetch_objects(
                filters=by_ids if restrictions is None else Filter.all_of([by_ids, restrictions]), limit=len(batch),
                return_properties=[], return_references=[QueryReference(link_on="document",
                                                                        return_properties=list(properties))])
            return result.objects

        batches = await asyncio.gather(*(read(ids[i:i + READ_BATCH]) for i in range(0, len(ids), READ_BATCH)))
        found: dict[UUID, tuple[UUID, dict[str, Any]]] = {}
        for objects in batches:
            for obj in objects:
                refs = (obj.references or {}).get("document")
                if refs and refs.objects:
                    document = refs.objects[0]
                    found[UUID(str(obj.uuid))] = (
                        UUID(str(document.uuid)), {prop: document.properties.get(prop) for prop in properties})
        return [(i, *found[i]) for i in ids if i in found]

    async def _ranked(self, query: ChunkQuery, **returned):
        chunks = self.client.collections.get(self.collectionNames.chunks_collection_name)
        common = dict(limit=query.limit, filters=await self._filter(query), **returned)
        if query.mode == SearchType.text:
            return await chunks.query.bm25(query=query.text, query_properties=self.query_properties, **common)
        if query.mode == SearchType.vector:
            vector, target = _vector(query)
            return await chunks.query.near_vector(near_vector=vector, target_vector=target, **common)
        if query.mode == SearchType.hybrid:
            vector, target = _vector(query)
            return await chunks.query.hybrid(query=query.text, alpha=query.alpha, vector=vector,
                                             target_vector=target, fusion_type=self.fusion,
                                             query_properties=self.query_properties, **common)
        raise ValueError(f"Unknown search type: {query.mode}")

    async def document_filter_stats(self) -> tuple[int | None, int | None, list[str] | None]:
        """(min yearIssued, max yearIssued, languages) over the public documents (#279); None where unknown."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        min_year = max_year = None
        res_year = await documents.aggregate.over_all(
            filters=public_documents(),
            return_metrics=[Metrics("yearIssued").integer(minimum=True, maximum=True)]
        )
        if "yearIssued" in res_year.properties:
            if res_year.properties["yearIssued"].minimum is not None:
                min_year = int(res_year.properties["yearIssued"].minimum)
            if res_year.properties["yearIssued"].maximum is not None:
                max_year = int(res_year.properties["yearIssued"].maximum)

        res_lang = await documents.aggregate.over_all(
            filters=public_documents(),
            return_metrics=[Metrics("language").text(top_occurrences_value=True, limit=1000)]
        )
        languages = []
        if "language" in res_lang.properties and res_lang.properties["language"].top_occurrences:
            languages = [top.value for top in res_lang.properties["language"].top_occurrences if top.value]
        return min_year, max_year, languages or None

    async def _filter(self, query: ChunkQuery):
        filters = [] if _within_readable_collection(query) else [_readable(query.readable_collection_id)]
        if query.collection_id is not None:
            filters.append(Filter.by_ref(link_on=self.collectionNames.user_collection_link_name)
                           .by_id().equal(query.collection_id))
        if query.document_id is not None:
            filters.append(Filter.by_ref(link_on="document").by_id().equal(query.document_id))
        if query.document_collection_id is not None:
            filters.append(Filter.by_ref(link_on="document").by_ref(link_on="collection")
                           .by_id().equal(query.document_collection_id))
        filters.extend(_condition(c) for c in query.conditions)
        if query.document_conditions or query.chunk_conditions:
            filters.extend(await self._criteria_filters(query))
        if not filters:
            return None
        return Filter.all_of(filters) if len(filters) > 1 else filters[0]

    async def _criteria_filters(self, query: ChunkQuery) -> list:
        document_types, document_tokenizations, chunk_types, chunk_tokenizations = await self._declared()
        copied = [c for c in query.document_conditions if c.prop in CHUNK_COPIES]
        referenced = [c for c in query.document_conditions if c.prop not in CHUNK_COPIES]
        return [
            *criteria.parts(referenced, document_types, document_tokenizations, records="Documents",
                            target=lambda prop: Filter.by_ref(link_on="document").by_property(prop)),
            *criteria.parts(copied, chunk_types, records="Documents"),
            *criteria.parts(query.chunk_conditions, chunk_types, chunk_tokenizations, records="Chunks"),
        ]


def _within_readable_collection(query: ChunkQuery) -> bool:
    """The query is limited to the documents of its readable collection, so every chunk is eligible."""
    return query.readable_collection_id is not None and query.document_collection_id == query.readable_collection_id


def _readable(collection_id: UUID | None):
    """The document access rule on chunks (#279): the chunk's document is public or, given an
    authorized collection, belongs to it. Applied inside every query, before ranking and limits.
    Public is read from the chunk's own copy ``documentPublic`` (#793), which fails closed: a
    chunk without the value never matches. Filtering through the ``document`` reference instead
    cost 1.2-2.6 s per query on the production corpus (#789)."""
    public = Filter.by_property(DOCUMENT_PUBLIC_FLAG).equal(True)
    if collection_id is None:
        return public
    return Filter.any_of([public, Filter.by_ref(link_on="document").by_ref(link_on="collection")
                         .by_id().equal(collection_id)])


def _hit(obj) -> SearchResultChunk | None:
    """A chunk object with its document reference as a search hit; None without a document."""
    doc_objs = obj.references.get("document").objects if obj.references and obj.references.get("document") else []
    if not doc_objs:
        return None
    first_doc = doc_objs[0]
    return SearchResultChunk(
        id=obj.uuid,
        **chunk_properties(obj.properties),
        document_object=Document(id=first_doc.uuid, **first_doc.properties),
        document=first_doc.uuid,
        metadata=classifications(obj.properties),
    )


def classifications(properties: Mapping[str, Any]) -> dict[str, list[str]]:
    """The populated classification properties (``TASK_CLASSES``) of a chunk, in that order.

    Stored as ``text[]``; a single value (older data, e.g. a string) becomes a one-element
    list of its text. Empty and repeated values are dropped, other properties are never
    included.
    """
    result = {}
    for name in TASK_CLASSES:
        stored = properties.get(name)
        if stored is None:
            continue
        values = stored if isinstance(stored, (list, tuple)) else [stored]
        values = list(dict.fromkeys(str(v) for v in values if v is not None and v != ""))
        if values:
            result[name] = values
    return result


def _vector(query: ChunkQuery) -> tuple[list[float], str]:
    if query.vector is None or not query.target_vector:
        raise ValueError(f"{query.mode.value} search needs a query vector and its target vector")
    return query.vector, query.target_vector


def _condition(condition: FieldCondition):
    if condition.field in DOCUMENT_FIELDS:
        target = Filter.by_ref(link_on="document").by_property(condition.field)
    else:
        target = Filter.by_property(condition.field)
    if condition.op == Op.equal:
        return target.equal(condition.value)
    if condition.op == Op.greater_or_equal:
        return target.greater_or_equal(condition.value)
    if condition.op == Op.less_or_equal:
        return target.less_or_equal(condition.value)
    if condition.op == Op.contains_any:
        return target.contains_any(list(condition.value))
    raise ValueError(f"Unsupported filter operation: {condition.op}")

