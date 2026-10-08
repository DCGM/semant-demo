"""Corpus documents and their chunks."""
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference, Sort

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.schema.chunks import ChunkText
from semant_demo.schema.documents import Document, DocumentBrowse, DocumentDetail, DocumentDetailTextChunkWithUserCollectionInfo


def _to_chunk_text(obj) -> ChunkText:
    docs = (obj.references or {}).get("document")
    return ChunkText(id=obj.uuid, document_id=docs.objects[0].uuid if docs and docs.objects else None,
                     order=obj.properties["order"], text=obj.properties.get("text") or "")


class DocumentRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames

    def _chunks(self):
        return self.client.collections.get(self.collectionNames.chunks_collection_name)

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

        doc_props = document_response.properties
        if "library" not in doc_props or not doc_props["library"]:
            doc_props["library"] = "mzk"
        document = Document(id=document_response.uuid, **doc_props)

        link = self.collectionNames.user_collection_link_name
        chunk_objects = await fetch_all(
            self.client.collections.get(self.collectionNames.chunks_collection_name),
            filters=Filter.by_ref("document").by_id().equal(document_id),
            return_references=[QueryReference(link_on=link)],
        )
        chunks = []
        for chunk_obj in chunk_objects:
            refs = chunk_obj.references.get(link) if chunk_obj.references else None
            chunks.append(DocumentDetailTextChunkWithUserCollectionInfo(
                id=chunk_obj.uuid,
                **chunk_obj.properties,
                document=document_response.uuid,
                in_user_collection=collection_id in {ref.uuid for ref in (refs.objects if refs else [])},
            ))
        return DocumentDetail(document=document, chunks=chunks)

    async def read_chunk_text(self, chunk_id: UUID) -> ChunkText | None:
        """The chunk's document, order and text, or None if it does not exist."""
        obj = await self._chunks().query.fetch_object_by_id(
            chunk_id, return_properties=["order", "text"],
            return_references=[QueryReference(link_on="document", return_properties=[])])
        return _to_chunk_text(obj) if obj is not None else None

    async def read_following_chunk_texts(self, document_id: UUID, after_order: int, limit: int) -> list[ChunkText]:
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
