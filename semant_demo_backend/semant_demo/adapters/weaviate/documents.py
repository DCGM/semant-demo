"""Corpus documents and their chunks."""
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference, Sort

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.features.documents.schemas import DocumentChunk, Document, DocumentBrowse, DocumentDetail, DocumentViewChunk


def _document_id(obj) -> UUID | None:
    docs = (obj.references or {}).get("document")
    return docs.objects[0].uuid if docs and docs.objects else None


def _to_text_chunk(obj, document_id: UUID) -> DocumentChunk:
    return DocumentChunk(**{**obj.properties, "id": obj.uuid, "document": document_id})


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
                **chunk_obj.properties,
                document=document_response.uuid,
                in_user_collection=collection_id in {ref.uuid for ref in (refs.objects if refs else [])},
            ))
        return DocumentDetail(document=document, chunks=chunks)

    async def read_chunk_text(self, chunk_id: UUID) -> AnnotationChunk | None:
        """The chunk's document, order, text and position, or None if it does not exist."""
        obj = await self._chunks().query.fetch_object_by_id(
            chunk_id, return_properties=self._text_properties(),
            return_references=[QueryReference(link_on="document", return_properties=[])])
        return _to_chunk_text(obj) if obj is not None else None

    async def read_chunk_texts_in_range(self, document_id: UUID, first: int, last: int) -> list[AnnotationChunk]:
        """The document's chunks with ``first <= order <= last`` (order, text, position), in
        order; several chunks with one order are all returned.

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
            return_properties=self._text_properties())
        return sorted((_to_chunk_text(o, document_id) for o in response.objects), key=lambda c: c.order)

    async def read_following_chunk_texts(self, document_id: UUID, after_order: int, limit: int) -> list[AnnotationChunk]:
        """Up to ``limit`` chunks of the document with order greater than ``after_order``, in order."""
        response = await self._chunks().query.fetch_objects(
            filters=(Filter.by_ref("document").by_id().equal(document_id)
                     & Filter.by_property("order").greater_than(after_order)),
            sort=Sort.by_property("order", ascending=True),
            limit=limit,
            return_properties=["order", "text"],
            return_references=[QueryReference(link_on="document", return_properties=[])],
        )
        return [_to_chunk_text(o) for o in response.objects]

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
        """
        before = direction == "before"
        position = Filter.by_property("order")
        response = await self._chunks().query.fetch_objects(
            filters=(Filter.by_ref("document").by_id().equal(document_id)
                     & (position.less_than(order) if before else position.greater_than(order))),
            sort=Sort.by_property("order", ascending=not before),
            limit=limit,
        )
        chunks = [_to_text_chunk(o, document_id) for o in response.objects]
        return chunks[::-1] if before else chunks

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
    ) -> DocumentBrowse:
        """One page of documents, optionally only those of a collection and matching filters."""
        documents = self.client.collections.get(self.collectionNames.document_collection_name)
        conditions = []
        if collection_id is not None:
            conditions.append(Filter.by_ref("collection").by_id().equal(collection_id))
        for prop, value in (("title", title), ("author", author), ("publisher", publisher),
                            ("documentType", document_type)):
            if value:
                conditions.append(Filter.by_property(prop).like(f"*{value}*"))
        filters = Filter.all_of(conditions) if conditions else None
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
