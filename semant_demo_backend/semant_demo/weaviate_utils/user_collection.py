import semant_demo.schemas as schemas

import logging
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference, Sort
from weaviate.exceptions import (
    WeaviateConnectionError,
    WeaviateTimeoutError,
    WeaviateQueryError,
    WeaviateInvalidInputError,
    UnexpectedStatusCodeError,
    ResponseCannotBeDecodedError,
    WeaviateClosedClientError,
    InsufficientPermissionsError,
)
from semant_demo.weaviate_exceptions import (
    WeaviateConnectError,
    WeaviateDataValidationError,
    WeaviateLimitError,
    WeaviateServerError,
    WeaviateOperationError
)

from semant_demo.schema.collections import Collection, CollectionStats, PatchCollection, PostCollection
from semant_demo.schema.documents import DocumentStats
from semant_demo.schema.documents import Document
from semant_demo.schema.tags import Tag
from semant_demo.schema.chunks import Chunk
from semant_demo.schema.spans import SpanType

from semant_demo.weaviate_utils.helpers import WeaviateHelpers, step_failure
from semant_demo.schema.outcomes import StepFailure, WriteResult, outcome_of
from semant_demo.users.models import User


class UserCollection():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        self.helpers = WeaviateHelpers(client, collectionNames)

    #######
    # API #
    #######
    async def create(self, collection: PostCollection, user: User) -> Collection:
        """
        Create user collection (contains chunks user choose)
        """
        logging.info(
            f"Adding user collection\nUser: {user.id}\nCollection name: {collection.name}")

        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)

        now = datetime.now(timezone.utc)
        new_collection_uuid = await usercollection_collection.data.insert(
            properties={
                "name": collection.name,
                "owner": user.name,
                "user_id": user.id,
                "description": collection.description,
                "color": collection.color,
                "created_at": now,
                "updated_at": now
            }
        )
        return Collection(
            id=new_collection_uuid,
            name=collection.name,
            owner=user.name,
            description=collection.description,
            created_at=now,
            updated_at=now,
            color=collection.color
        )

    async def read_access_record(self, collection_id: UUID) -> tuple[UUID | None, set[UUID]] | None:
        """
        Owner id and shared-with user ids of a collection, or None if it does not exist.
        Read directly by id; used for authorization.
        """
        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        obj = await usercollection_collection.query.fetch_object_by_id(
            collection_id, return_properties=["user_id", "shared_with"])
        if obj is None:
            return None
        owner = obj.properties.get("user_id")
        return (
            UUID(str(owner)) if owner else None,
            {UUID(str(uid)) for uid in (obj.properties.get("shared_with") or [])},
        )

    async def chunk_ids_in_collection(
        self, chunk_ids: list[UUID], collection_id: UUID, document_id: UUID | None = None,
    ) -> set[UUID]:
        """
        The subset of ``chunk_ids`` that belong to the collection (and to the document,
        when given).
        """
        if not chunk_ids:
            return set()
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)
        filters = (
            Filter.by_id().contains_any(list(chunk_ids))
            & Filter.by_ref(self.collectionNames.user_collection_link_name).by_id().equal(collection_id)
        )
        if document_id is not None:
            filters = filters & Filter.by_ref("document").by_id().equal(document_id)
        response = await chunks_collection.query.fetch_objects(
            filters=filters, limit=len(chunk_ids), return_properties=[])
        return {UUID(str(o.uuid)) for o in response.objects}

    async def read(self, collection_id: UUID) -> Collection | None:
        """
        Retrieves collection by its id, returns None if collection with given id does not exist
        """

        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        response = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if response is None:
            return None
        props = response.properties
        return Collection(
            id=response.uuid,
            name=props.get("name"),
            owner=props.get("owner"),
            description=props.get("description"),
            created_at=props.get("created_at"),
            updated_at=props.get("updated_at"),
            color=props.get("color")
        )

    async def read_all(self, user: User) -> list[Collection]:
        """
        Retrieves all collections for given user
        """
        try:
            # collections the user owns, or that have been shared with them
            filters = (
                Filter.by_property("user_id").equal(user.id)
                | Filter.by_property("shared_with").contains_any([user.id])
            )
            usercollection_collection = self.client.collections.get(
                self.collectionNames.user_collection_name)
            page_size = 1000
            offset = 0
            collections_response = []
            while True:
                results = await usercollection_collection.query.fetch_objects(
                    filters=filters,
                    limit=page_size,
                    offset=offset,
                )
                if not results.objects:
                    break

                for o in results.objects:
                    props = o.properties
                    shared_with = [UUID(str(uid)) for uid in (props.get("shared_with") or [])]
                    collections_response.append(Collection(
                        id=o.uuid,
                        name=props.get("name"),
                        owner=props.get("owner"),
                        description=props.get("description"),
                        created_at=props.get("created_at"),
                        updated_at=props.get("updated_at"),
                        color=props.get("color"),
                        shared_with_count=len(shared_with),
                        is_shared_with_me=user.id in shared_with,
                    ))

                if len(results.objects) < page_size:
                    break
                offset += len(results.objects)

            return collections_response
        except WeaviateConnectionError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateConnectError(str(e))
        except WeaviateInvalidInputError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateDataValidationError(str(e))
        except WeaviateTimeoutError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateLimitError(str(e))
        except WeaviateQueryError as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateOperationError(str(e))
        except (UnexpectedStatusCodeError, ResponseCannotBeDecodedError) as e:
            logging.error(f"Error: {str(e)}")
            raise WeaviateServerError(str(e))
        except Exception as e:
            # catch unexpected errors and wrap them
            logging.error(f"Unexpected error fetching chunks: {str(e)}")
            raise WeaviateServerError(str(e))

    async def read_collection_stats(self, collection_id: UUID) -> CollectionStats | None:
        """
        Computes aggregate statistics for one collection.
        """

        collection = await self.read(collection_id)
        if collection is None:
            return None

        # Compute documents count
        documents_collection = self.client.collections.get(
            self.collectionNames.document_collection_name)
        documents_filters = (
            Filter.by_ref("collection").by_id().equal(collection_id)
        )

        documents_count_response = await documents_collection.aggregate.over_all(
            total_count=True,
            filters=documents_filters
        )
        documents_count = documents_count_response.total_count or 0

        # Compute chunks count
        chunks_filters = (
            Filter.by_ref("userCollection").by_id().equal(collection_id)
        )

        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)
        chunks_count_response = await chunks_collection.aggregate.over_all(
            total_count=True,
            filters=chunks_filters
        )
        chunks_count = chunks_count_response.total_count or 0

        # Compute tags count
        tags_collection = self.client.collections.get(
            self.collectionNames.tag_collection_name)
        tags_filters = (
            Filter.by_ref("userCollection").by_id().equal(collection_id)
        )
        tags_count_response = await tags_collection.aggregate.over_all(
            total_count=True,
            filters=tags_filters
        )
        tags_count = tags_count_response.total_count or 0

        # Compute annotation stats from Span collection.
        # One annotation = one span object.
        # Span belongs to selected collection if it references a chunk that belongs to the collection and also references a tag that belongs to the collection.

        spans_collection = self.client.collections.get(
            self.collectionNames.span_collection_name)

        spans_filters = (
            Filter.by_ref("text_chunk").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
            &
            Filter.by_ref("tag").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
            &
            Filter.by_property("type").equal(SpanType.pos)
        )

        annotations_count_response = await spans_collection.aggregate.over_all(
            total_count=True,
            filters=spans_filters,
        )
        annotations_count = annotations_count_response.total_count or 0

        return CollectionStats(
            collection_id=collection_id,
            documents_count=documents_count,
            chunks_count=chunks_count,
            tags_count=tags_count,
            annotations_count=annotations_count,
        )

    async def update(self, collection_id: str, collection: PatchCollection) -> Collection:
        """"
        Updates collection with given id
        """
        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        collection_in_db = await self.read(collection_id)
        if collection_in_db is None:
            raise WeaviateOperationError(
                f"Collection with id {collection_id} not found")

        now = datetime.now(timezone.utc)

        # PATCH semantics: update only fields that were actually sent by the client.
        properties = collection.model_dump(exclude_unset=True)
        properties["updated_at"] = now

        await usercollection_collection.data.update(
            uuid=collection_id,
            properties=properties
        )

        updated_collection = await self.read(collection_id)
        if updated_collection is None:
            raise WeaviateOperationError(
                "Weaviate error: collection not found after update")

        return updated_collection

    async def change_owner(self, collection_id: str, user_id: UUID, session: AsyncSession) -> Collection:
        """
        Reassigns ownership of a collection to a different user.
        """
        result = await session.execute(select(User).where(User.id == user_id))
        new_owner = result.scalar_one_or_none()
        if new_owner is None:
            raise WeaviateOperationError(f"User with id {user_id} not found")

        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        collection_in_db = await self.read(collection_id)
        if collection_in_db is None:
            raise WeaviateOperationError(
                f"Collection with id {collection_id} not found")

        now = datetime.now(timezone.utc)
        await usercollection_collection.data.update(
            uuid=collection_id,
            properties={
                "owner": new_owner.name,
                "user_id": new_owner.id,
                "updated_at": now
            }
        )

        updated_collection = await self.read(collection_id)
        if updated_collection is None:
            raise WeaviateOperationError(
                "Weaviate error: collection not found after update")

        return updated_collection

    async def delete(self, collection_id: str) -> None:
        """
        Deletes collection with given id.
        """
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)

        collection_response = await usercollection_collection.query.fetch_object_by_id(
            collection_id,
        )
        if collection_response is None:
            raise WeaviateOperationError("Collection not found")
        
        await self.helpers.delete_user_collection_cascade(collection_id)

    async def read_all_tags(self, collection_id: UUID) -> list[Tag]:
        """
        Retrieves all tags which belong to collection given by id
        """
        tag_collection = self.client.collections.get(
            self.collectionNames.tag_collection_name)
        filters = (
            Filter.by_ref("userCollection").by_id().equal(collection_id)
        )
        offset = 0
        page_size = 100
        
        tags = []
        while True:
            response = await tag_collection.query.fetch_objects(
                filters=filters,
                limit=page_size,
                offset=offset,
            )

            if not response.objects:
                break

            for obj in response.objects:
                props = obj.properties
                tags.append(Tag(
                    id=obj.uuid,
                    name=props['tag_name'],
                    shorthand=props['tag_shorthand'],
                    color=props['tag_color'],
                    pictogram=props['tag_pictogram'],
                    definition=props['tag_definition'],
                    examples=props['tag_examples'] or []
                ))

            if len(response.objects) < page_size:
                break

            offset += page_size
        return tags        

    async def read_all_chunks(self, collectionId: str):
        return await self.helpers.fetch_chunks_by_collection(collectionId)
    
    async def read_all_chunks_by_document(self, document_id: str, collection_id: str):
        """
        Retrieves all chunks from a document with given id, that also belong to collection with given id.
        """
        
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)
        filters = (
            Filter.by_ref("document").by_id().equal(document_id)
            & Filter.by_ref("userCollection").by_id().equal(collection_id)
        )
        offset = 0
        page_size = 100
        
        chunks = []
        while True:
            response = await chunks_collection.query.fetch_objects(
                filters=filters,
                limit=page_size,
                offset=offset,
                sort=Sort.by_property("order", ascending=True),
                return_references=[QueryReference(link_on="document")]
            )

            if not response.objects:
                break

            for obj in response.objects:
                props = obj.properties
                chunks.append(Chunk(
                    id=obj.uuid,
                    text=props['text'],
                    order=props['order'],
                    title=props['title'],
                    end_paragraph=props['end_paragraph'],
                    start_page_id=props['start_page_id'],
                    from_page=props['from_page'],
                    to_page=props['to_page'],
                    in_collection=True,
                ))

            if len(response.objects) < page_size:
                break

            offset += page_size
        return chunks

    async def get_document_chunks_with_context(
        self,
        document_id: str,
        collection_id: str,
        order_values: list[int],
    ) -> list[Chunk]:
        """
        Fetches specific chunks from a document by their order values,
        marking whether each chunk is already in the given collection.
        """
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)

        # Build a filter matching the document and the requested order values
        order_filters = [Filter.by_property("order").equal(o) for o in order_values]
        combined_order = order_filters[0]
        for f in order_filters[1:]:
            combined_order = combined_order | f

        doc_filter = Filter.by_ref("document").by_id().equal(document_id)
        filters = doc_filter & combined_order

        response = await chunks_collection.query.fetch_objects(
            filters=filters,
            sort=Sort.by_property("order", ascending=True),
            return_references=[QueryReference(link_on="userCollection")],
        )

        result = []
        for obj in response.objects:
            props = obj.properties
            # Check if this chunk references the current collection
            in_col = False
            if obj.references and "userCollection" in obj.references:
                col_ids = [ref.uuid for ref in obj.references["userCollection"].objects]
                in_col = UUID(collection_id) in col_ids
            result.append(Chunk(
                id=obj.uuid,
                text=props['text'],
                order=props['order'],
                title=props['title'],
                end_paragraph=props['end_paragraph'],
                start_page_id=props['start_page_id'],
                from_page=props['from_page'],
                to_page=props['to_page'],
                in_collection=in_col,
            ))
        return result

    async def get_chunks_in_range(
        self,
        document_id: str,
        collection_id: str,
        order_gt: int | None,
        order_lt: int | None,
    ) -> list[Chunk]:
        """
        Returns all chunks of a document whose order is strictly greater than
        order_gt (if given) and strictly less than order_lt (if given).
        Marks in_collection for each chunk based on collection membership.
        Results are sorted by order ascending.
        """
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)

        doc_filter = Filter.by_ref("document").by_id().equal(document_id)
        range_filter = doc_filter
        if order_gt is not None:
            range_filter = range_filter & Filter.by_property("order").greater_than(order_gt)
        if order_lt is not None:
            range_filter = range_filter & Filter.by_property("order").less_than(order_lt)

        response = await chunks_collection.query.fetch_objects(
            filters=range_filter,
            limit=10000,
            sort=Sort.by_property("order", ascending=True),
            return_references=[QueryReference(link_on="userCollection")],
        )

        result: list[Chunk] = []
        for obj in response.objects:
            props = obj.properties
            in_col = False
            if obj.references and "userCollection" in obj.references:
                col_ids = [ref.uuid for ref in obj.references["userCollection"].objects]
                in_col = UUID(collection_id) in col_ids
            result.append(Chunk(
                id=obj.uuid,
                text=props['text'],
                order=props['order'],
                title=props['title'],
                end_paragraph=props['end_paragraph'],
                start_page_id=props['start_page_id'],
                from_page=props['from_page'],
                to_page=props['to_page'],
                in_collection=in_col,
            ))
        return result

    async def get_neighbour_chunk(
        self,
        document_id: str,
        collection_id: str,
        direction: str,
        boundary_order: int,
    ) -> Chunk | None:
        """
        Returns the single chunk immediately before (direction='prev') or after
        (direction='next') the given boundary_order value within the document.
        Marks in_collection based on whether it belongs to the collection.
        """
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)

        doc_filter = Filter.by_ref("document").by_id().equal(document_id)
        if direction == "prev":
            order_filter = Filter.by_property("order").less_than(boundary_order)
            sort = Sort.by_property("order", ascending=False)
        else:
            order_filter = Filter.by_property("order").greater_than(boundary_order)
            sort = Sort.by_property("order", ascending=True)

        response = await chunks_collection.query.fetch_objects(
            filters=doc_filter & order_filter,
            limit=1,
            sort=sort,
            return_references=[QueryReference(link_on="userCollection")],
        )

        if not response.objects:
            return None

        obj = response.objects[0]
        props = obj.properties
        in_col = False
        if obj.references and "userCollection" in obj.references:
            col_ids = [ref.uuid for ref in obj.references["userCollection"].objects]
            in_col = UUID(collection_id) in col_ids

        return Chunk(
            id=obj.uuid,
            text=props['text'],
            order=props['order'],
            title=props['title'],
            end_paragraph=props['end_paragraph'],
            start_page_id=props['start_page_id'],
            from_page=props['from_page'],
            to_page=props['to_page'],
            in_collection=in_col,
        )

    async def count_document_chunks(self, document_id: str) -> int:
        """Returns the total number of chunks belonging to the given document."""
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)
        doc_filter = Filter.by_ref("document").by_id().equal(document_id)
        response = await chunks_collection.aggregate.over_all(
            filters=doc_filter,
            total_count=True,
        )
        return response.total_count or 0

    async def read_document_stats(self, collection_id: str, document_id: str) -> DocumentStats:
        """
        Computes per-document statistics within a given collection:
        - chunks_in_collection: chunks of this document linked to the collection
        - total_chunks: all chunks of this document
        - annotations_count: spans whose chunk belongs to this document and collection
        - distinct_tags_count: number of distinct tags used in those spans
        """
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)

        # Total chunks in this document
        total_filter = Filter.by_ref("document").by_id().equal(document_id)
        total_response = await chunks_collection.aggregate.over_all(
            filters=total_filter,
            total_count=True,
        )
        total_chunks = total_response.total_count or 0

        # Chunks in this document that are also in the collection
        in_col_filter = (
            Filter.by_ref("document").by_id().equal(document_id)
            & Filter.by_ref(self.collectionNames.user_collection_link_name).by_id().equal(collection_id)
        )
        in_col_response = await chunks_collection.aggregate.over_all(
            filters=in_col_filter,
            total_count=True,
        )
        chunks_in_collection = in_col_response.total_count or 0

        # Annotations (spans) for this document's chunks in this collection.
        # Both the chunk and the tag must belong to the collection.
        spans_collection = self.client.collections.get(
            self.collectionNames.span_collection_name)
        spans_filter = (
            Filter.by_ref("text_chunk").by_ref("document").by_id().equal(document_id)
            & Filter.by_ref("text_chunk").by_ref(
                self.collectionNames.user_collection_link_name).by_id().equal(collection_id)
            & Filter.by_ref("tag").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
            & Filter.by_property("type").equal(SpanType.pos)
        )
        spans_agg_response = await spans_collection.aggregate.over_all(
            filters=spans_filter,
            total_count=True,
        )
        annotations_count = spans_agg_response.total_count or 0

        # Distinct tags used in those spans
        distinct_tag_ids: set[str] = set()
        if annotations_count > 0:
            batch_size = 500
            offset = 0
            while True:
                spans_objects = await spans_collection.query.fetch_objects(
                    filters=spans_filter,
                    limit=batch_size,
                    offset=offset,
                    return_references=[QueryReference(link_on="tag")],
                )
                if not spans_objects.objects:
                    break

                for obj in spans_objects.objects:
                    if obj.references and "tag" in obj.references:
                        for ref in obj.references["tag"].objects:
                            distinct_tag_ids.add(str(ref.uuid))

                fetched_count = len(spans_objects.objects)
                offset += fetched_count
                if fetched_count < batch_size:
                    break

        return DocumentStats(
            document_id=document_id,
            collection_id=collection_id,
            chunks_in_collection=chunks_in_collection,
            total_chunks=total_chunks,
            annotations_count=annotations_count,
            distinct_tags_count=len(distinct_tag_ids),
        )

    async def read_all_documents(self, collection_id: str) -> list[Document]:
        """
        Retrieves all documents - optionally can be filtered by collection id
        """
        document_collection = self.client.collections.get(
            self.collectionNames.document_collection_name)
        filters = None
        if collection_id is not None:
            filters = (
                Filter.by_ref("collection").by_id().equal(collection_id)
            )
        response = await document_collection.query.fetch_objects(
            filters=filters
        )
        documents = []
        for obj in response.objects:
            props = obj.properties
            documents.append(Document(
                id=obj.uuid,
                **props
            ))
        return documents

    async def add_chunk(self, chunk_id: UUID, collection_id: UUID) -> WriteResult:
        """
        Links a chunk to a collection, then links the chunk's document to it.

        Best effort: completed links are kept; a failed document link is reported as a
        partial outcome. Links that already exist count as done. Raises
        ``WeaviateOperationError`` if the chunk does not exist.
        """
        link = self.collectionNames.user_collection_link_name
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        chunk_obj = await chunks_collection.query.fetch_object_by_id(
            chunk_id,
            return_properties=[],
            return_references=[QueryReference(link_on="document"), QueryReference(link_on=link)],
        )
        if chunk_obj is None:
            raise WeaviateOperationError("Chunk not found")
        refs = chunk_obj.references or {}
        document_ids = [UUID(str(d.uuid)) for d in (refs["document"].objects if "document" in refs else [])]
        linked = {UUID(str(c.uuid)) for c in (refs[link].objects if link in refs else [])}

        succeeded: list[str] = []
        failed: list[StepFailure] = []
        try:
            if collection_id not in linked:
                await chunks_collection.data.reference_add(from_uuid=chunk_id, from_property=link, to=collection_id)
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

    async def _link_document(self, document_id: UUID, collection_id: UUID) -> None:
        """Adds the document -> collection reference unless it already exists."""
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        doc = await document_collection.query.fetch_object_by_id(
            document_id, return_properties=[], return_references=[QueryReference(link_on="collection")])
        if doc is None:
            raise WeaviateOperationError("Document not found")
        refs = doc.references or {}
        if collection_id in {UUID(str(c.uuid)) for c in (refs["collection"].objects if "collection" in refs else [])}:
            return
        await document_collection.data.reference_add(from_uuid=document_id, from_property="collection", to=collection_id)

    async def remove_chunk(self, chunk_id: str, collection_id: str) -> bool:
        """
        Removes the reference between a chunk and a collection.
        """
        try:
            chunks_collection = self.client.collections.get(
                self.collectionNames.chunks_collection_name)
            await chunks_collection.data.reference_delete(
                from_uuid=chunk_id,
                from_property="userCollection",
                to=collection_id,
            )
            return True
        except Exception as e:
            logging.error(f"Failed to remove chunk from collection: {e}")
            return False

    async def share(self, collection_id: str, user_id: UUID, current_user: User, session: AsyncSession) -> Collection:
        """
        Shares a collection with another user by adding them to its shared_with list.
        Only the collection's owner may share it. No-op if already shared with that user.
        """
        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        collection_obj = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if collection_obj is None:
            raise WeaviateOperationError(
                f"Collection with id {collection_id} not found")

        props = collection_obj.properties
        if str(props.get("user_id")) != str(current_user.id):
            raise PermissionError("Only the collection owner can share it")

        if user_id == current_user.id:
            raise WeaviateDataValidationError(
                "Cannot share a collection with its owner")

        result = await session.execute(select(User).where(User.id == user_id))
        target_user = result.scalar_one_or_none()
        if target_user is None:
            raise WeaviateOperationError(f"User with id {user_id} not found")

        current_shared_with = {UUID(str(uid)) for uid in (props.get("shared_with") or [])}
        current_shared_with.add(user_id)

        now = datetime.now(timezone.utc)
        await usercollection_collection.data.update(
            uuid=collection_id,
            properties={
                "shared_with": list(current_shared_with),
                "updated_at": now,
            }
        )

        updated_collection = await self.read(collection_id)
        if updated_collection is None:
            raise WeaviateOperationError(
                "Weaviate error: collection not found after update")

        return updated_collection

    async def unshare(self, collection_id: str, user_id: UUID, current_user: User) -> Collection:
        """
        Revokes a collection share, removing the user from its shared_with list.
        Only the collection's owner may unshare it. No-op if not currently shared with that user.
        """
        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        collection_obj = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if collection_obj is None:
            raise WeaviateOperationError(
                f"Collection with id {collection_id} not found")

        props = collection_obj.properties
        if str(props.get("user_id")) != str(current_user.id):
            raise PermissionError("Only the collection owner can unshare it")

        current_shared_with = {UUID(str(uid)) for uid in (props.get("shared_with") or [])}
        current_shared_with.discard(user_id)

        now = datetime.now(timezone.utc)
        await usercollection_collection.data.update(
            uuid=collection_id,
            properties={
                "shared_with": list(current_shared_with),
                "updated_at": now,
            }
        )

        updated_collection = await self.read(collection_id)
        if updated_collection is None:
            raise WeaviateOperationError(
                "Weaviate error: collection not found after update")

        return updated_collection

    async def read_shared_users(self, collection_id: str, session: AsyncSession) -> list[User]:
        """
        Returns the users a collection is currently shared with.
        """
        usercollection_collection = self.client.collections.get(
            self.collectionNames.user_collection_name)
        collection_obj = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if collection_obj is None:
            raise WeaviateOperationError(
                f"Collection with id {collection_id} not found")

        shared_ids = [UUID(str(uid)) for uid in (collection_obj.properties.get("shared_with") or [])]
        if not shared_ids:
            return []

        result = await session.execute(select(User).where(User.id.in_(shared_ids)))
        return result.scalars().all()

    async def _document_chunks(self, document_id: UUID, collection_id: UUID | None = None) -> list:
        """All chunks of a document (optionally only those in the collection), with their collection refs.

        Listed completely before any write, so writes cannot change the pages being read.
        """
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        link = self.collectionNames.user_collection_link_name
        chunk_filter = Filter.by_ref("document").by_id().equal(document_id)
        if collection_id is not None:
            chunk_filter = chunk_filter & Filter.by_ref(link).by_id().equal(collection_id)
        page_size = 100
        chunks: list = []
        while True:
            response = await chunks_collection.query.fetch_objects(
                filters=chunk_filter,
                return_properties=[],
                return_references=[QueryReference(link_on=link)],
                limit=page_size,
                offset=len(chunks),
            )
            chunks.extend(response.objects)
            if len(response.objects) < page_size:
                return chunks

    async def add_document(self, document_id: UUID, collection_id: UUID) -> WriteResult:
        """
        Adds a document to a collection and also links all its chunks to that collection.

        Best effort: each chunk link is attempted and failures are reported; links that
        already exist count as done. The document itself is linked unless every chunk
        link failed. Raises ``WeaviateOperationError`` if the document does not exist.
        """
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        if await document_collection.query.fetch_object_by_id(document_id, return_properties=[]) is None:
            raise WeaviateOperationError("Document not found")
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        link = self.collectionNames.user_collection_link_name

        chunks = await self._document_chunks(document_id)
        succeeded: list[str] = []
        failed: list[StepFailure] = []
        for chunk in chunks:
            refs = chunk.references.get(link) if chunk.references else None
            try:
                if collection_id not in {UUID(str(r.uuid)) for r in (refs.objects if refs else [])}:
                    await chunks_collection.data.reference_add(from_uuid=chunk.uuid, from_property=link, to=collection_id)
                succeeded.append(str(chunk.uuid))
            except Exception as e:
                failed.append(step_failure("link_chunk", chunk.uuid, e))

        if chunks and not succeeded:
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
        collection keeps showing it and the removal can be retried.
        """
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        link = self.collectionNames.user_collection_link_name

        succeeded: list[str] = []
        failed: list[StepFailure] = []
        for chunk in await self._document_chunks(document_id, collection_id):
            try:
                await chunks_collection.data.reference_delete(from_uuid=chunk.uuid, from_property=link, to=collection_id)
                succeeded.append(str(chunk.uuid))
            except Exception as e:
                failed.append(step_failure("unlink_chunk", chunk.uuid, e))

        if failed:
            return WriteResult(outcome=outcome_of(len(succeeded), len(failed), 1), succeeded=succeeded,
                               failed=failed, unattempted=[str(document_id)])
        try:
            await document_collection.data.reference_delete(from_uuid=document_id, from_property="collection", to=collection_id)
            succeeded.append(str(document_id))
        except Exception as e:
            failed.append(step_failure("unlink_document", document_id, e))
        return WriteResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded, failed=failed)

    ###########
    # Helpers #
    ###########
