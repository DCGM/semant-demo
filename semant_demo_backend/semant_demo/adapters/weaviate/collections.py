"""User collections: metadata, sharing record, and document/chunk membership.

Membership is stored twice: chunk -> collection references (``userCollection``) and
document -> collection references (``collection``). Sharing is the ``shared_with`` list of
user ids on the collection. Users themselves live in SQL; callers look them up there.
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference, Sort

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.adapters.weaviate.writes import delete_collection_cascade, step_failure
from semant_demo.core.errors import NotFoundError
from semant_demo.schema.chunks import Chunk
from semant_demo.schema.collections import Collection, CollectionStats, PatchCollection, PostCollection
from semant_demo.schema.documents import Document, DocumentStats
from semant_demo.schema.outcomes import StepFailure, WriteResult, outcome_of
from semant_demo.schema.spans import SpanType

logger = logging.getLogger(__name__)


def _ref_ids(obj, link: str) -> set[UUID]:
    refs = obj.references.get(link) if obj.references else None
    return {ref.uuid for ref in (refs.objects if refs else [])}


def _shared_with(props) -> list[UUID]:
    return [UUID(str(uid)) for uid in (props.get("shared_with") or [])]


def to_collection(obj) -> Collection:
    props = obj.properties
    return Collection(
        id=obj.uuid,
        name=props.get("name"),
        owner=props.get("owner"),
        description=props.get("description"),
        created_at=props.get("created_at"),
        updated_at=props.get("updated_at"),
        color=props.get("color"),
    )


def to_chunk(obj, in_collection: bool) -> Chunk:
    props = obj.properties
    return Chunk(
        id=obj.uuid,
        text=props["text"],
        order=props["order"],
        title=props["title"],
        end_paragraph=props["end_paragraph"],
        start_page_id=props["start_page_id"],
        from_page=props["from_page"],
        to_page=props["to_page"],
        in_collection=in_collection,
    )


class UserCollectionRepository:
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.link = collectionNames.user_collection_link_name

    def _collections(self):
        return self.client.collections.get(self.collectionNames.user_collection_name)

    def _documents(self):
        return self.client.collections.get(self.collectionNames.document_collection_name)

    def _chunks(self):
        return self.client.collections.get(self.collectionNames.chunks_collection_name)

    def _spans(self):
        return self.client.collections.get(self.collectionNames.span_collection_name)

    async def _require(self, collection_id: UUID, properties: list[str] | None = None):
        obj = await self._collections().query.fetch_object_by_id(collection_id, return_properties=properties)
        if obj is None:
            raise NotFoundError("Collection not found")
        return obj

    async def _read_existing(self, collection_id: UUID) -> Collection:
        collection = await self.read(collection_id)
        if collection is None:
            raise NotFoundError("Collection not found")
        return collection

    ############
    # Metadata #
    ############

    async def create(self, collection: PostCollection, owner_id: UUID, owner_name: str | None) -> Collection:
        now = datetime.now(timezone.utc)
        new_id = await self._collections().data.insert(properties={
            "name": collection.name,
            "owner": owner_name,
            "user_id": owner_id,
            "description": collection.description,
            "color": collection.color,
            "created_at": now,
            "updated_at": now,
        })
        return Collection(id=new_id, name=collection.name, owner=owner_name, description=collection.description,
                          created_at=now, updated_at=now, color=collection.color)

    async def read(self, collection_id: UUID) -> Collection | None:
        """The collection with this id, or None if it does not exist."""
        obj = await self._collections().query.fetch_object_by_id(collection_id)
        return to_collection(obj) if obj is not None else None

    async def read_access_record(self, collection_id: UUID) -> tuple[UUID | None, set[UUID]] | None:
        """
        Owner id and shared-with user ids of a collection, or None if it does not exist.
        Read directly by id; used for authorization.
        """
        obj = await self._collections().query.fetch_object_by_id(
            collection_id, return_properties=["user_id", "shared_with"])
        if obj is None:
            return None
        owner = obj.properties.get("user_id")
        return (UUID(str(owner)) if owner else None, set(_shared_with(obj.properties)))

    async def read_all(self, user_id: UUID) -> list[Collection]:
        """Collections the user owns or that are shared with them."""
        filters = (
            Filter.by_property("user_id").equal(user_id)
            | Filter.by_property("shared_with").contains_any([user_id])
        )
        result = []
        for obj in await fetch_all(self._collections(), filters=filters, page_size=1000):
            shared_with = _shared_with(obj.properties)
            result.append(to_collection(obj).model_copy(update={
                "shared_with_count": len(shared_with),
                "is_shared_with_me": user_id in shared_with,
            }))
        return result

    async def update(self, collection_id: UUID, patch: PatchCollection) -> Collection:
        """Sets the fields that were sent (PATCH). Raises ``NotFoundError`` for an unknown collection."""
        await self._require(collection_id, [])
        properties = patch.model_dump(exclude_unset=True)
        properties["updated_at"] = datetime.now(timezone.utc)
        await self._collections().data.update(uuid=collection_id, properties=properties)
        return await self._read_existing(collection_id)

    async def set_owner(self, collection_id: UUID, owner_id: UUID, owner_name: str | None) -> Collection:
        """Raises ``NotFoundError`` for an unknown collection."""
        await self._require(collection_id, [])
        await self._collections().data.update(uuid=collection_id, properties={
            "owner": owner_name,
            "user_id": owner_id,
            "updated_at": datetime.now(timezone.utc),
        })
        return await self._read_existing(collection_id)

    async def delete(self, collection_id: UUID) -> None:
        """
        Deletes the collection with its tags and their annotations, after removing all
        chunk and document links. Raises ``NotFoundError`` for an unknown collection.
        """
        await self._require(collection_id, [])
        await delete_collection_cascade(self.client, self.collectionNames, collection_id)

    ###########
    # Sharing #
    ###########

    async def read_shared_user_ids(self, collection_id: UUID) -> list[UUID]:
        """Raises ``NotFoundError`` for an unknown collection."""
        return _shared_with((await self._require(collection_id, ["shared_with"])).properties)

    async def _set_shared_with(self, collection_id: UUID, shared_with: set[UUID]) -> Collection:
        await self._collections().data.update(uuid=collection_id, properties={
            "shared_with": list(shared_with),
            "updated_at": datetime.now(timezone.utc),
        })
        return await self._read_existing(collection_id)

    async def share(self, collection_id: UUID, user_id: UUID) -> Collection:
        """Adds the user to the collection's shared-with list (no change if already there)."""
        shared_with = set(await self.read_shared_user_ids(collection_id))
        return await self._set_shared_with(collection_id, shared_with | {user_id})

    async def unshare(self, collection_id: UUID, user_id: UUID) -> Collection:
        """Removes the user from the collection's shared-with list (no change if not there)."""
        shared_with = set(await self.read_shared_user_ids(collection_id))
        return await self._set_shared_with(collection_id, shared_with - {user_id})

    #########
    # Reads #
    #########

    async def read_collection_stats(self, collection_id: UUID) -> CollectionStats | None:
        """Aggregate counts for one collection, or None if it does not exist."""
        if await self._collections().query.fetch_object_by_id(collection_id, return_properties=[]) is None:
            return None
        names = self.collectionNames

        async def count(collection, filters) -> int:
            return (await collection.aggregate.over_all(total_count=True, filters=filters)).total_count or 0

        tags = self.client.collections.get(names.tag_collection_name)
        # One annotation = one approved span whose chunk and tag both belong to the collection.
        spans_filters = (
            Filter.by_ref("text_chunk").by_ref(names.user_collection_name).by_id().equal(collection_id)
            & Filter.by_ref("tag").by_ref(names.user_collection_name).by_id().equal(collection_id)
            & Filter.by_property("type").equal(SpanType.pos)
        )
        return CollectionStats(
            collection_id=collection_id,
            documents_count=await count(self._documents(), Filter.by_ref("collection").by_id().equal(collection_id)),
            chunks_count=await count(self._chunks(), Filter.by_ref(self.link).by_id().equal(collection_id)),
            tags_count=await count(tags, Filter.by_ref("userCollection").by_id().equal(collection_id)),
            annotations_count=await count(self._spans(), spans_filters),
        )

    async def read_all_documents(self, collection_id: UUID) -> list[Document]:
        """All documents linked to the collection."""
        objects = await fetch_all(self._documents(), filters=Filter.by_ref("collection").by_id().equal(collection_id))
        return [Document(id=obj.uuid, **obj.properties) for obj in objects]

    async def document_in_collection(self, document_id: UUID, collection_id: UUID) -> bool:
        """
        Whether the document is linked to the collection (the document -> collection
        reference that the collection's document list uses). One small lookup,
        independent of the document's size.
        """
        response = await self._documents().query.fetch_objects(
            filters=Filter.by_id().equal(document_id) & Filter.by_ref("collection").by_id().equal(collection_id),
            limit=1,
            return_properties=[],
        )
        return bool(response.objects)

    async def chunk_ids_in_collection(
        self, chunk_ids: list[UUID], collection_id: UUID, document_id: UUID | None = None,
    ) -> set[UUID]:
        """The subset of ``chunk_ids`` that belong to the collection (and to the document, when given)."""
        if not chunk_ids:
            return set()
        filters = Filter.by_id().contains_any(list(chunk_ids)) & Filter.by_ref(self.link).by_id().equal(collection_id)
        if document_id is not None:
            filters = filters & Filter.by_ref("document").by_id().equal(document_id)
        response = await self._chunks().query.fetch_objects(filters=filters, limit=len(chunk_ids), return_properties=[])
        return {o.uuid for o in response.objects}

    async def read_all_chunks_by_document(self, document_id: UUID, collection_id: UUID) -> list[Chunk]:
        """The document's chunks that belong to the collection, in order."""
        objects = await fetch_all(
            self._chunks(),
            filters=Filter.by_ref("document").by_id().equal(document_id)
            & Filter.by_ref(self.link).by_id().equal(collection_id),
            sort=Sort.by_property("order", ascending=True),
        )
        return [to_chunk(obj, in_collection=True) for obj in objects]

    async def get_chunks_in_range(self, document_id: UUID, collection_id: UUID,
                                  order_gt: int | None, order_lt: int | None) -> list[Chunk]:
        """
        The document's chunks with order strictly greater than ``order_gt`` and strictly
        less than ``order_lt`` (each bound optional), in order, marked with membership.
        """
        filters = Filter.by_ref("document").by_id().equal(document_id)
        if order_gt is not None:
            filters = filters & Filter.by_property("order").greater_than(order_gt)
        if order_lt is not None:
            filters = filters & Filter.by_property("order").less_than(order_lt)
        objects = await fetch_all(
            self._chunks(),
            filters=filters,
            sort=Sort.by_property("order", ascending=True),
            return_references=[QueryReference(link_on=self.link)],
        )
        return [to_chunk(obj, in_collection=collection_id in _ref_ids(obj, self.link)) for obj in objects]

    async def get_neighbour_chunk(self, document_id: UUID, collection_id: UUID,
                                  direction: str, boundary_order: int) -> Chunk | None:
        """
        The chunk immediately before (``prev``) or after (``next``) ``boundary_order`` in
        the document, marked with membership; None if there is none.
        """
        if direction == "prev":
            order_filter = Filter.by_property("order").less_than(boundary_order)
            sort = Sort.by_property("order", ascending=False)
        else:
            order_filter = Filter.by_property("order").greater_than(boundary_order)
            sort = Sort.by_property("order", ascending=True)
        response = await self._chunks().query.fetch_objects(
            filters=Filter.by_ref("document").by_id().equal(document_id) & order_filter,
            limit=1,
            sort=sort,
            return_references=[QueryReference(link_on=self.link)],
        )
        if not response.objects:
            return None
        obj = response.objects[0]
        return to_chunk(obj, in_collection=collection_id in _ref_ids(obj, self.link))

    async def read_document_stats(self, collection_id: UUID, document_id: UUID) -> DocumentStats:
        """
        Per-document statistics within the collection: chunks in the collection, all
        chunks, approved annotations whose chunk and tag belong to the collection, and the
        number of distinct tags they use.
        """
        names = self.collectionNames

        async def count(collection, filters) -> int:
            return (await collection.aggregate.over_all(filters=filters, total_count=True)).total_count or 0

        document_filter = Filter.by_ref("document").by_id().equal(document_id)
        spans_filter = (
            Filter.by_ref("text_chunk").by_ref("document").by_id().equal(document_id)
            & Filter.by_ref("text_chunk").by_ref(self.link).by_id().equal(collection_id)
            & Filter.by_ref("tag").by_ref(names.user_collection_name).by_id().equal(collection_id)
            & Filter.by_property("type").equal(SpanType.pos)
        )
        annotations_count = await count(self._spans(), spans_filter)
        distinct_tags: set[UUID] = set()
        if annotations_count > 0:
            spans = await fetch_all(self._spans(), filters=spans_filter, page_size=500, return_properties=[],
                                    return_references=[QueryReference(link_on="tag")])
            for span in spans:
                distinct_tags |= _ref_ids(span, "tag")

        return DocumentStats(
            document_id=str(document_id),
            collection_id=str(collection_id),
            chunks_in_collection=await count(self._chunks(), document_filter
                                             & Filter.by_ref(self.link).by_id().equal(collection_id)),
            total_chunks=await count(self._chunks(), document_filter),
            annotations_count=annotations_count,
            distinct_tags_count=len(distinct_tags),
        )

    ##############
    # Membership #
    ##############

    async def add_chunk(self, chunk_id: UUID, collection_id: UUID) -> WriteResult:
        """
        Links a chunk to a collection, then links the chunk's document to it.

        Best effort: completed links are kept; a failed document link is reported as a
        partial outcome. Links that already exist count as done. Raises
        ``NotFoundError`` if the chunk does not exist.
        """
        chunks = self._chunks()
        chunk_obj = await chunks.query.fetch_object_by_id(
            chunk_id,
            return_properties=[],
            return_references=[QueryReference(link_on="document"), QueryReference(link_on=self.link)],
        )
        if chunk_obj is None:
            raise NotFoundError("Chunk not found")
        document_ids = list(_ref_ids(chunk_obj, "document"))

        succeeded: list[str] = []
        failed: list[StepFailure] = []
        try:
            if collection_id not in _ref_ids(chunk_obj, self.link):
                await chunks.data.reference_add(from_uuid=chunk_id, from_property=self.link, to=collection_id)
            succeeded.append(str(chunk_id))
        except Exception as e:
            failed.append(step_failure("link_chunk", chunk_id, e))
            # The document link would claim a membership that the chunk link did not establish.
            return WriteResult(outcome=outcome_of(0, 1, len(document_ids)), failed=failed,
                               unattempted=[str(d) for d in document_ids])

        for document_id in document_ids:
            try:
                await self._link_document(document_id, collection_id)
                succeeded.append(str(document_id))
            except Exception as e:
                failed.append(step_failure("link_document", document_id, e))
        return WriteResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded, failed=failed)

    async def _document_collections(self, document_id: UUID) -> set[UUID]:
        doc = await self._documents().query.fetch_object_by_id(
            document_id, return_properties=[], return_references=[QueryReference(link_on="collection")])
        if doc is None:
            raise NotFoundError("Document not found")
        return _ref_ids(doc, "collection")

    async def _link_document(self, document_id: UUID, collection_id: UUID) -> None:
        """Adds the document -> collection reference unless it already exists."""
        if collection_id not in await self._document_collections(document_id):
            await self._documents().data.reference_add(from_uuid=document_id, from_property="collection",
                                                       to=collection_id)

    async def _unlink_document(self, document_id: UUID, collection_id: UUID) -> None:
        """Removes the document -> collection reference if it exists."""
        if collection_id in await self._document_collections(document_id):
            await self._documents().data.reference_delete(from_uuid=document_id, from_property="collection",
                                                          to=collection_id)

    async def remove_chunk(self, chunk_id: UUID, collection_id: UUID) -> None:
        """
        Removes the chunk -> collection link. Removing a link that does not exist is a
        no-op. The chunk's document stays linked. Raises ``NotFoundError`` if the chunk
        does not exist; storage errors propagate.
        """
        chunks = self._chunks()
        chunk_obj = await chunks.query.fetch_object_by_id(
            chunk_id, return_properties=[], return_references=[QueryReference(link_on=self.link)])
        if chunk_obj is None:
            raise NotFoundError("Chunk not found")
        if collection_id in _ref_ids(chunk_obj, self.link):
            await chunks.data.reference_delete(from_uuid=chunk_id, from_property=self.link, to=collection_id)

    async def _document_chunks(self, document_id: UUID, collection_id: UUID | None = None) -> list:
        """All chunks of a document (optionally only those in the collection), with their collection refs.

        Listed completely before any write, so writes cannot change the pages being read.
        """
        chunk_filter = Filter.by_ref("document").by_id().equal(document_id)
        if collection_id is not None:
            chunk_filter = chunk_filter & Filter.by_ref(self.link).by_id().equal(collection_id)
        return await fetch_all(self._chunks(), filters=chunk_filter, return_properties=[],
                               return_references=[QueryReference(link_on=self.link)])

    async def add_document(self, document_id: UUID, collection_id: UUID) -> WriteResult:
        """
        Adds a document to a collection and also links all its chunks to that collection.

        Best effort: each chunk link is attempted and failures are reported; links that
        already exist count as done. The document itself is linked unless every chunk
        link failed. Raises ``NotFoundError`` if the document does not exist.
        """
        if await self._documents().query.fetch_object_by_id(document_id, return_properties=[]) is None:
            raise NotFoundError("Document not found")
        chunks = self._chunks()

        succeeded: list[str] = []
        failed: list[StepFailure] = []
        document_chunks = await self._document_chunks(document_id)
        for chunk in document_chunks:
            try:
                if collection_id not in _ref_ids(chunk, self.link):
                    await chunks.data.reference_add(from_uuid=chunk.uuid, from_property=self.link, to=collection_id)
                succeeded.append(str(chunk.uuid))
            except Exception as e:
                failed.append(step_failure("link_chunk", chunk.uuid, e))

        if document_chunks and not succeeded:
            return WriteResult(outcome=outcome_of(0, len(failed), 1), failed=failed, unattempted=[str(document_id)])
        try:
            await self._link_document(document_id, collection_id)
            succeeded.append(str(document_id))
        except Exception as e:
            failed.append(step_failure("link_document", document_id, e))
        return WriteResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded, failed=failed)

    async def remove_document(self, document_id: UUID, collection_id: UUID) -> WriteResult:
        """
        Removes a document's chunks from a collection, then the document itself.

        Best effort: each chunk unlink is attempted and failures are reported. The
        document stays linked while any of its chunks could not be unlinked, so the
        collection keeps showing it and the removal can be retried. Removing a document
        that is not in the collection is a no-op. Raises ``NotFoundError`` if the
        document does not exist.
        """
        await self._document_collections(document_id)
        chunks = self._chunks()
        succeeded: list[str] = []
        failed: list[StepFailure] = []
        for chunk in await self._document_chunks(document_id, collection_id):
            try:
                await chunks.data.reference_delete(from_uuid=chunk.uuid, from_property=self.link, to=collection_id)
                succeeded.append(str(chunk.uuid))
            except Exception as e:
                failed.append(step_failure("unlink_chunk", chunk.uuid, e))

        if failed:
            return WriteResult(outcome=outcome_of(len(succeeded), len(failed), 1), succeeded=succeeded,
                               failed=failed, unattempted=[str(document_id)])
        try:
            await self._unlink_document(document_id, collection_id)
            succeeded.append(str(document_id))
        except Exception as e:
            failed.append(step_failure("unlink_document", document_id, e))
        return WriteResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded, failed=failed)
