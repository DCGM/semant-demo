"""Corpus documents and their chunks."""
import logging
from collections.abc import Sequence
from uuid import UUID

from pydantic import ValidationError

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import BM25Operator, Filter, QueryReference, Sort

from semant_demo.adapters.weaviate import criteria
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.features.documents.criteria import Condition
from semant_demo.features.documents.schemas import (
    DocumentChunk, Document, DocumentBrowse, DocumentDetail, DocumentViewChunk, LayoutStart)

logger = logging.getLogger(__name__)

YEAR = "yearIssued"
"""The ``Documents`` property of the publication year, the order of ``browse_by_year``."""
_LOWEST_YEAR = -(2 ** 63)
"""Every stored year is at least this (``int`` is 64-bit in Weaviate): ``>=`` it means "has a year"."""

METADATA_PROPERTIES = {"title": 2, "subtitle": 1, "author": 1, "publisher": 1}
"""The bibliographic ``Documents`` properties a text query matches as metadata (#607), with their
BM25 weights: a word in the title counts double. Only those the store declares as searchable
text are queried (stores differ, #312)."""

LAYOUT_START = "layoutStart"
"""The ``Chunks`` object property of a chunk's start on the page scans (#541)."""


def chunk_properties(props: dict) -> dict:
    """A chunk's stored properties for a chunk projection: ``layoutStart`` is parsed, and an
    anchor that does not parse is left out (logged), so one bad value never fails a read."""
    value = props.get(LAYOUT_START)
    if value is None:
        return props
    try:
        anchor = LayoutStart.model_validate(value)
    except ValidationError:
        logger.warning("Ignoring an invalid stored chunk layoutStart")
        anchor = None
    return {**props, LAYOUT_START: anchor}


def _document_id(obj) -> UUID | None:
    docs = (obj.references or {}).get("document")
    return docs.objects[0].uuid if docs and docs.objects else None


def _to_text_chunk(obj, document_id: UUID) -> DocumentChunk:
    return DocumentChunk(**{**chunk_properties(obj.properties), "id": obj.uuid, "document": document_id})


POSITION_PROPERTIES = {"startChar": "start_char", "startWord": "start_word", "wordOpenAtStart": "word_open_at_start"}
"""``Chunks`` properties of a chunk's absolute position in its document (#463), by field of
``AnnotationChunk`` / ``ChunkPosition``."""


def _to_chunk_text(obj, document_id: UUID | None = None) -> AnnotationChunk:
    props = obj.properties
    return AnnotationChunk(id=obj.uuid, document_id=document_id or _document_id(obj), order=props["order"],
                           text=props.get("text") or "",
                           **{field: props.get(name) for name, field in POSITION_PROPERTIES.items()})


async def missing_position_properties(client: WeaviateAsyncClient, names: CollectionNames) -> list[str]:
    """The chunk position properties (#463) the ``Chunks`` collection does not declare."""
    config = await client.collections.get(names.chunks_collection_name).config.get()
    declared = {p.name for p in config.properties}
    return [name for name in POSITION_PROPERTIES if name not in declared]


class DocumentRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self._metadata_properties: list[str] | None = None
        self.positions = False
        """``Chunks`` declares the position properties (#463): chunk text reads return them
        (set at startup; a property that is not declared cannot be read)."""

    def _chunks(self):
        return self.client.collections.get(self.collectionNames.chunks_collection_name)

    def _text_properties(self) -> list[str]:
        return ["order", "text", *(POSITION_PROPERTIES if self.positions else ())]

    async def read(self, document_id: UUID) -> Document | None:
        """The document with this id, or None if it does not exist."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        response = await documents.query.fetch_object_by_id(document_id)
        if response is None:
            return None
        return Document(id=response.uuid, **response.properties)

    async def read_chunks(self, document_id: UUID, collection_id: UUID) -> DocumentDetail | None:
        """
        The document and all its chunks, each marked with membership in the collection.
        None if the document does not exist.
        """
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        document_response = await documents.query.fetch_object_by_id(document_id)
        if document_response is None:
            return None

        document = Document(id=document_response.uuid, **document_response.properties)

        link = self.collectionNames.user_collection_link_name
        chunk_objects = await fetch_all(
            self.client.collections.get(self.collectionNames.chunks_collection_name),
            filters=Filter.by_ref("document").by_id().equal(document_id),
            return_references=[QueryReference(link_on=link)],
        )
        chunks = []
        for chunk_obj in chunk_objects:
            refs = chunk_obj.references.get(link) if chunk_obj.references else None
            chunks.append(DocumentViewChunk(
                id=chunk_obj.uuid,
                **chunk_properties(chunk_obj.properties),
                document=document_response.uuid,
                in_user_collection=collection_id in {ref.uuid for ref in (refs.objects if refs else [])},
            ))
        return DocumentDetail(document=document, chunks=chunks)

    async def exists(self, document_id: UUID) -> bool:
        """Whether the document exists (reads no properties)."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        return await documents.query.fetch_object_by_id(document_id, return_properties=[]) is not None

    async def read_chunks_covering_page(self, document_id: UUID, page: int, limit: int) -> list[DocumentChunk]:
        """Up to ``limit`` chunks of the document whose ``from_page``..``to_page`` includes
        ``page``, in ``order``."""
        response = await self._chunks().query.fetch_objects(
            filters=Filter.by_ref("document").by_id().equal(document_id)
            & Filter.by_property("from_page").less_or_equal(page)
            & Filter.by_property("to_page").greater_or_equal(page),
            sort=Sort.by_property("order", ascending=True),
            limit=limit,
        )
        return [_to_text_chunk(o, document_id) for o in response.objects]

    async def read_chunk_text(self, chunk_id: UUID) -> AnnotationChunk | None:
        """The chunk's document, order, text and position, or None if it does not exist."""
        obj = await self._chunks().query.fetch_object_by_id(
            chunk_id, return_properties=self._text_properties(),
            return_references=[QueryReference(link_on="document", return_properties=[])])
        return _to_chunk_text(obj) if obj is not None else None

    async def _read_orders(self, document_id: UUID, first: int, last: int, **query) -> list:
        """The document's chunk objects with ``first <= order <= last``, sorted by order;
        several chunks with one order are all returned.

        No server-side sort (which loads every chunk of the document, #376), and the orders
        are listed rather than bounded: without a range index Weaviate evaluates ``>=`` and
        ``<=`` over every chunk on either side of the bound, so the cost would grow with
        the length of the document; equality lookups of the few orders do not.
        """
        if last < first:
            return []
        response = await self._chunks().query.fetch_objects(
            filters=Filter.all_of([Filter.by_ref("document").by_id().equal(document_id),
                                   Filter.by_property("order").contains_any(list(range(first, last + 1)))]),
            # A margin over the range, so that duplicate orders are seen rather than cut off.
            limit=2 * (last - first + 1),
            **query)
        return sorted(response.objects, key=lambda o: o.properties["order"])

    async def read_chunk_texts_in_range(self, document_id: UUID, first: int, last: int) -> list[AnnotationChunk]:
        """The document's chunks with ``first <= order <= last`` (order, text, position), in
        order; several chunks with one order are all returned."""
        objects = await self._read_orders(document_id, first, last, return_properties=self._text_properties())
        return [_to_chunk_text(o, document_id) for o in objects]

    async def read_many(self, document_ids: list[UUID]) -> dict[UUID, Document]:
        """The existing documents among ``document_ids``."""
        if not document_ids:
            return {}
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        response = await documents.query.fetch_objects(
            filters=Filter.by_id().contains_any(list(document_ids)), limit=len(document_ids))
        return {UUID(str(o.uuid)): Document(id=o.uuid, **o.properties) for o in response.objects}

    async def read_chunk(self, chunk_id: UUID) -> DocumentChunk | None:
        """The chunk with its stored properties, or None if it (or its document link) does not exist."""
        obj = await self._chunks().query.fetch_object_by_id(
            chunk_id, return_references=[QueryReference(link_on="document", return_properties=[])])
        document_id = _document_id(obj) if obj is not None else None
        return _to_text_chunk(obj, document_id) if document_id is not None else None

    async def read_adjacent_chunks(self, document_id: UUID, order: int, direction: str, limit: int) -> list[DocumentChunk]:
        """
        Up to ``limit`` chunks of the document directly before (``direction="before"``) or
        after (``"after"``) the chunk with ``order``, nearest first, returned in document order.

        Reads the ``limit`` orders next to ``order`` (#376). Since a document's orders are
        consecutive (ADR 0009), fewer chunks than ``limit`` indicates a boundary for
        valid documents. Gaps and duplicates violate the model; no recovery is attempted
        and results for such documents are not guaranteed.
        """
        before = direction == "before"
        first, last = (order - limit, order - 1) if before else (order + 1, order + limit)
        chunks = [_to_text_chunk(o, document_id) for o in await self._read_orders(document_id, first, last)]
        # Duplicate orders may return more than ``limit``: keep the nearest.
        return chunks[max(len(chunks) - limit, 0):] if before else chunks[:limit]

    async def count_chunks(self, document_id: UUID) -> int:
        """The number of chunks of the document (0 for an unknown document)."""
        chunks = self.client.collections.get(self.collectionNames.chunks_collection_name)
        response = await chunks.aggregate.over_all(
            filters=Filter.by_ref("document").by_id().equal(document_id),
            total_count=True,
        )
        return response.total_count or 0

    async def browse(
        self,
        collection_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = None,
        sort_desc: bool = False,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        document_type: str | None = None,
        conditions: Sequence[Condition] = (),
    ) -> DocumentBrowse:
        """One page of documents, optionally only those of a collection and matching filters:
        the substring filters (``title``, ...) and the search criteria ``conditions`` (rendered
        as Analytics renders them, so both match the same documents). Raises
        ``criteria.UnavailableFilter`` for a condition on a property the store does not declare."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        filters = await self._browse_filter(collection_id, conditions, title=title, author=author,
                                            publisher=publisher, documentType=document_type)
        sort = Sort.by_property(sort_by, ascending=not sort_desc) if sort_by else None

        count_response = await documents.aggregate.over_all(filters=filters, total_count=True)
        response = await documents.query.fetch_objects(
            filters=filters, limit=limit + 1, offset=offset, sort=sort)

        objects = response.objects
        has_more = len(objects) > limit
        return DocumentBrowse(
            items=[Document(id=obj.uuid, **obj.properties) for obj in objects[:limit]],
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
            total_count=count_response.total_count or 0,
        )

    async def browse_by_year(self, collection_id: UUID | None = None, limit: int = 50, offset: int = 0,
                             conditions: Sequence[Condition] = ()) -> DocumentBrowse:
        """One page of the documents of ``browse`` (without its substring filters) in a stable
        order: publication year, oldest first, then id; the documents without a year follow all
        dated ones, by id.

        Weaviate sorts a missing value first in ascending order and last in descending order,
        and filtering by a missing value needs ``indexNullState``, which the stores do not
        enable (measured on 1.40). So the dated documents are counted, read in ascending order
        with a filter that only a year satisfies, and the undated ones are read past the dated
        ones of the descending order (``YEAR``, then id ascending). Two counts and at most two
        reads per page; ``offset + limit`` stays within ``QUERY_MAXIMUM_RESULTS`` for the
        caller to ensure. A document whose year changes between those reads may be missed or
        repeated on that page, never shown as undated."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        filters = await self._browse_filter(collection_id, conditions)
        dated = Filter.by_property(YEAR).greater_or_equal(_LOWEST_YEAR)
        dated_filters = dated if filters is None else Filter.all_of([filters, dated])
        total = (await documents.aggregate.over_all(filters=filters, total_count=True)).total_count or 0
        dated_total = 0
        if total:
            dated_total = (await documents.aggregate.over_all(filters=dated_filters, total_count=True)).total_count or 0

        objects = []
        if offset < dated_total:
            response = await documents.query.fetch_objects(
                filters=dated_filters, limit=min(limit, dated_total - offset), offset=offset,
                sort=Sort.by_property(YEAR, ascending=True).by_property("_id", ascending=True))
            objects.extend(response.objects)
        undated_offset = max(offset, dated_total)
        undated_limit = offset + limit - undated_offset
        if undated_limit > 0 and undated_offset < total:
            response = await documents.query.fetch_objects(
                filters=filters, limit=undated_limit, offset=undated_offset,
                sort=Sort.by_property(YEAR, ascending=False).by_property("_id", ascending=True))
            objects.extend(o for o in response.objects if o.properties.get(YEAR) is None)

        has_more = offset + limit < total
        return DocumentBrowse(
            items=[Document(id=obj.uuid, **obj.properties) for obj in objects],
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
            total_count=total,
        )

    async def count(self, collection_id: UUID | None = None, conditions: Sequence[Condition] = ()) -> int:
        """The number of documents of ``browse`` (without its substring filters): of the collection,
        if given, and matching ``conditions``. Raises ``criteria.UnavailableFilter``."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        filters = await self._browse_filter(collection_id, conditions)
        return (await documents.aggregate.over_all(filters=filters, total_count=True)).total_count or 0

    async def metadata_ranked_ids(self, text: str, limit: int, collection_id: UUID | None = None,
                                  conditions: Sequence[Condition] = ()) -> list[UUID]:
        """Ids of the top ``limit`` documents of ``count`` whose bibliographic metadata
        (``METADATA_PROPERTIES``) holds every word of ``text``, by BM25 relevance (#607); no
        properties are read. Every word is required (BM25 ``and``): a single common word of a
        longer query does not make a title a match. Empty when the store has none of the
        properties."""
        properties = await self._searchable_metadata()
        if not properties:
            return []
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        response = await documents.query.bm25(
            query=text, query_properties=properties, operator=BM25Operator.and_(), limit=limit,
            filters=await self._browse_filter(collection_id, conditions), return_properties=[])
        return [obj.uuid for obj in response.objects]

    async def read_eligible(self, document_ids: Sequence[UUID], collection_id: UUID | None = None,
                            conditions: Sequence[Condition] = ()) -> dict[UUID, Document]:
        """The documents among ``document_ids`` that ``count`` counts (of the collection, matching
        ``conditions``); the others, also those that do not exist, are left out."""
        if not document_ids:
            return {}
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        by_ids = Filter.by_id().contains_any(list(document_ids))
        scope = await self._browse_filter(collection_id, conditions)
        response = await documents.query.fetch_objects(
            filters=by_ids if scope is None else Filter.all_of([by_ids, scope]), limit=len(document_ids))
        return {UUID(str(o.uuid)): Document(id=o.uuid, **o.properties) for o in response.objects}

    async def _searchable_metadata(self) -> list[str]:
        """``METADATA_PROPERTIES`` the store declares as searchable text, with their weights; read
        once, then cached (a schema change needs a restart)."""
        if self._metadata_properties is None:
            config = await self.client.collections.get(
                await resolve_collection(self.client, self.collectionNames.document_collection_name)
            ).config.get()
            searchable = {p.name for p in config.properties
                          if p.data_type.value in ("text", "text[]") and p.index_searchable is not False}
            self._metadata_properties = [name if weight == 1 else f"{name}^{weight}"
                                         for name, weight in METADATA_PROPERTIES.items() if name in searchable]
        return self._metadata_properties

    async def _browse_filter(self, collection_id: UUID | None, conditions: Sequence[Condition] = (),
                             **substrings: str | None):
        """The filter of a browse: the collection, the substring filters (stored property ->
        text) and the search criteria ``conditions``; None without any."""
        name = self.collectionNames.document_collection_name
        parts = []
        if collection_id is not None:
            parts.append(Filter.by_ref("collection").by_id().equal(collection_id))
        for prop, value in substrings.items():
            if value:
                parts.append(Filter.by_property(prop).like(f"*{value}*"))
        if conditions:
            types, tokenizations = await criteria.declared(self.client, name)
            parts.extend(criteria.parts(conditions, types, tokenizations))
        return Filter.all_of(parts) if len(parts) > 1 else (parts[0] if parts else None)
