import logging
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from weaviate.classes.query import Filter, QueryReference, Sort

from semant_demo.weaviate_exceptions import NotFoundError

from semant_demo.schema.collections import Collection, CollectionStats, PatchCollection, PostCollection
from semant_demo.schema.documents import DocumentStats
from semant_demo.schema.documents import Document
from semant_demo.schema.tags import Tag
from semant_demo.schema.chunks import Chunk
from semant_demo.schema.spans import SpanType

from semant_demo.weaviate_utils.base_repository import WeaviateBaseRepository
from semant_demo.users.models import User


class UserCollectionRepository(WeaviateBaseRepository):
    """Repository for the Weaviate user-collection collection."""

    #########
    # CRUD  #
    #########

    async def create(self, collection: PostCollection, user: User) -> Collection:
        """
        Creates a new user collection owned by the given user.

        Args:
            collection: collection data to create.
            user: the owner.

        Returns:
            The created collection.
        """
        logging.info(f"Adding user collection\nUser: {user.id}\nCollection name: {collection.name}")

        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)

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

    async def read(self, collection_id: UUID) -> Collection | None:
        """
        Retrieves a collection by its id.

        Args:
            collection_id: UUID of the collection.

        Returns:
            The collection, or None if no collection with this id exists.
        """
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
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
        Retrieves all collections owned by the given user.

        Args:
            user: the owner to filter by.

        Returns:
            All matching collections.
        """
        filters = Filter.by_property("user_id").equal(user.id)
        collection = self.client.collections.get(self.collectionNames.user_collection_name)

        collections_response = []
        async for obj in self._paginate_objects(collection, filters=filters):
            props = obj.properties
            collections_response.append(Collection(
                id=obj.uuid,
                name=props.get("name"),
                owner=props.get("owner"),
                description=props.get("description"),
                created_at=props.get("created_at"),
                updated_at=props.get("updated_at"),
                color=props.get("color")
            ))
        return collections_response

    async def update(self, collection_id: str, collection: PatchCollection) -> Collection:
        """
        Applies a partial update to an existing collection.

        Args:
            collection_id: UUID of the collection to update.
            collection: fields to change; unset fields are left untouched.

        Returns:
            The updated collection.

        Raises:
            NotFoundError: no collection with this id exists.
        """
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
        collection_in_db = await self.read(collection_id)
        if collection_in_db is None:
            raise NotFoundError(f"Collection with id {collection_id} not found")

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
            raise NotFoundError(f"Collection with id {collection_id} not found after update")

        return updated_collection

    async def delete(self, collection_id: str) -> None:
        """
        Deletes a collection after removing every reference to it from
        documents, chunks and its own tags.

        Args:
            collection_id: UUID of the collection to delete.

        Raises:
            NotFoundError: no collection with this id exists.
        """
        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)

        collection_response = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if collection_response is None:
            raise NotFoundError(f"Collection with id {collection_id} not found")

        await self.helpers.delete_user_collection_cascade(collection_id)

    #######################
    # Additional queries  #
    #######################

    async def change_owner(self, collection_id: str, user_id: UUID, session: AsyncSession) -> Collection:
        """
        Reassigns ownership of a collection to a different user.

        Args:
            collection_id: UUID of the collection.
            user_id: UUID of the new owner (looked up in the SQL user store).
            session: SQL session used to look up the new owner.

        Returns:
            The updated collection.

        Raises:
            NotFoundError: the user or the collection does not exist.
        """
        result = await session.execute(select(User).where(User.id == user_id))
        new_owner = result.scalar_one_or_none()
        if new_owner is None:
            raise NotFoundError(f"User with id {user_id} not found")

        usercollection_collection = self.client.collections.get(self.collectionNames.user_collection_name)
        collection_in_db = await self.read(collection_id)
        if collection_in_db is None:
            raise NotFoundError(f"Collection with id {collection_id} not found")

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
            raise NotFoundError(f"Collection with id {collection_id} not found after update")

        return updated_collection

    async def read_collection_stats(self, collection_id: UUID) -> CollectionStats | None:
        """
        Computes aggregate statistics (documents/chunks/tags/annotations counts) for one collection.

        Returns:
            The stats, or None if the collection does not exist.
        """
        collection = await self.read(collection_id)
        if collection is None:
            return None

        documents_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        documents_count_response = await documents_collection.aggregate.over_all(
            total_count=True,
            filters=Filter.by_ref("collection").by_id().equal(collection_id),
        )
        documents_count = documents_count_response.total_count or 0

        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        chunks_count_response = await chunks_collection.aggregate.over_all(
            total_count=True,
            filters=Filter.by_ref("userCollection").by_id().equal(collection_id),
        )
        chunks_count = chunks_count_response.total_count or 0

        tags_collection = self.client.collections.get(self.collectionNames.tag_collection_name)
        tags_count_response = await tags_collection.aggregate.over_all(
            total_count=True,
            filters=Filter.by_ref("userCollection").by_id().equal(collection_id),
        )
        tags_count = tags_count_response.total_count or 0

        # One annotation = one span object. A span belongs to the collection if
        # it references a chunk that belongs to the collection and a tag that
        # belongs to the collection.
        spans_collection = self.client.collections.get(self.collectionNames.span_collection_name)
        spans_filters = (
            Filter.by_ref("text_chunk").by_ref(self.collectionNames.user_collection_name).by_id().equal(collection_id)
            & Filter.by_ref("tag").by_ref(self.collectionNames.user_collection_name).by_id().equal(collection_id)
            & Filter.by_property("type").equal(SpanType.pos)
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

    async def read_all_tags(self, collection_id: UUID) -> list[Tag]:
        """Retrieves all tags that belong to the given collection."""
        tag_collection = self.client.collections.get(self.collectionNames.tag_collection_name)
        filters = Filter.by_ref("userCollection").by_id().equal(collection_id)

        tags = []
        async for obj in self._paginate_objects(tag_collection, filters=filters):
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
        return tags

    async def read_all_chunks(self, collectionId: str):
        return await self.helpers.fetch_chunks_by_collection(collectionId)

    async def read_all_chunks_by_document(self, document_id: str, collection_id: str) -> list[Chunk]:
        """Retrieves all chunks of a document that also belong to the given collection, ordered."""
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        filters = (
            Filter.by_ref("document").by_id().equal(document_id)
            & Filter.by_ref("userCollection").by_id().equal(collection_id)
        )

        chunks = []
        async for obj in self._paginate_objects(
            chunks_collection,
            filters=filters,
            sort=Sort.by_property("order", ascending=True),
            return_references=[QueryReference(link_on="document")],
        ):
            # The filter above already guarantees membership, no need to
            # inspect userCollection references to compute in_collection.
            chunks.append(self._build_chunk(obj, in_collection=True))
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
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)

        order_filters = [Filter.by_property("order").equal(o) for o in order_values]
        combined_order = order_filters[0]
        for f in order_filters[1:]:
            combined_order = combined_order | f

        filters = Filter.by_ref("document").by_id().equal(document_id) & combined_order

        response = await chunks_collection.query.fetch_objects(
            filters=filters,
            sort=Sort.by_property("order", ascending=True),
            return_references=[QueryReference(link_on="userCollection")],
        )

        return [
            self._build_chunk(obj, in_collection=self._is_in_collection(obj, collection_id))
            for obj in response.objects
        ]

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
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)

        range_filter = Filter.by_ref("document").by_id().equal(document_id)
        if order_gt is not None:
            range_filter = range_filter & Filter.by_property("order").greater_than(order_gt)
        if order_lt is not None:
            range_filter = range_filter & Filter.by_property("order").less_than(order_lt)

        result = []
        async for obj in self._paginate_objects(
            chunks_collection,
            filters=range_filter,
            sort=Sort.by_property("order", ascending=True),
            return_references=[QueryReference(link_on="userCollection")],
        ):
            result.append(self._build_chunk(obj, in_collection=self._is_in_collection(obj, collection_id)))
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
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)

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
        return self._build_chunk(obj, in_collection=self._is_in_collection(obj, collection_id))

    async def count_document_chunks(self, document_id: str) -> int:
        """Returns the total number of chunks belonging to the given document."""
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        response = await chunks_collection.aggregate.over_all(
            filters=Filter.by_ref("document").by_id().equal(document_id),
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
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)

        total_response = await chunks_collection.aggregate.over_all(
            filters=Filter.by_ref("document").by_id().equal(document_id),
            total_count=True,
        )
        total_chunks = total_response.total_count or 0

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
        spans_collection = self.client.collections.get(self.collectionNames.span_collection_name)
        spans_filter = (
            Filter.by_ref("text_chunk").by_ref("document").by_id().equal(document_id)
            & Filter.by_ref("text_chunk").by_ref(
                self.collectionNames.user_collection_link_name).by_id().equal(collection_id)
            & Filter.by_ref("tag").by_ref(self.collectionNames.user_collection_name).by_id().equal(collection_id)
            & Filter.by_property("type").equal(SpanType.pos)
        )
        spans_agg_response = await spans_collection.aggregate.over_all(
            filters=spans_filter,
            total_count=True,
        )
        annotations_count = spans_agg_response.total_count or 0

        distinct_tag_ids: set[str] = set()
        if annotations_count > 0:
            async for obj in self._paginate_objects(
                spans_collection,
                filters=spans_filter,
                page_size=500,
                return_references=[QueryReference(link_on="tag")],
            ):
                if obj.references and "tag" in obj.references:
                    for ref in obj.references["tag"].objects:
                        distinct_tag_ids.add(str(ref.uuid))

        return DocumentStats(
            document_id=document_id,
            collection_id=collection_id,
            chunks_in_collection=chunks_in_collection,
            total_chunks=total_chunks,
            annotations_count=annotations_count,
            distinct_tags_count=len(distinct_tag_ids),
        )

    async def read_all_documents(self, collection_id: str) -> list[Document]:
        """Retrieves all documents, optionally filtered by collection id."""
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        filters = None
        if collection_id is not None:
            filters = Filter.by_ref("collection").by_id().equal(collection_id)

        documents = []
        async for obj in self._paginate_objects(document_collection, filters=filters):
            documents.append(Document(id=obj.uuid, **obj.properties))
        return documents

    async def add_chunk(self, chunk_id: str, collection_id: str) -> bool:
        """
        Links a chunk to a collection, and best-effort links the chunk's
        parent document to the collection too (a failure on the document side
        is logged but does not fail the chunk link itself).
        """
        result = await self.helpers.create_reference(
            chunk_id,
            self.collectionNames.chunks_collection_name,
            self.collectionNames.user_collection_link_name,
            collection_id,
        )

        try:
            chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
            chunk_obj = await chunks_collection.query.fetch_object_by_id(
                chunk_id,
                return_references=[QueryReference(link_on="document")]
            )

            if chunk_obj and chunk_obj.references and "document" in chunk_obj.references:
                document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
                for doc_ref in chunk_obj.references["document"].objects:
                    await document_collection.data.reference_add(
                        from_uuid=doc_ref.uuid,
                        from_property="collection",
                        to=collection_id,
                    )
        except Exception as e:
            logging.error(f"Failed to link chunk's document to collection: {e}")

        return result

    async def remove_chunk(self, chunk_id: str, collection_id: str) -> bool:
        """Removes the reference between a chunk and a collection."""
        return await self.helpers.remove_reference(
            chunk_id,
            self.collectionNames.chunks_collection_name,
            self.collectionNames.user_collection_link_name,
            collection_id,
        )

    async def add_document(self, document_id: str, collection_id: str) -> None:
        """Adds a document to a collection and links all its chunks to that collection."""
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)

        chunk_filter = Filter.by_ref("document").by_id().equal(document_id)
        async for chunk in self._paginate_objects(
            chunks_collection,
            filters=chunk_filter,
            return_references=[QueryReference(link_on="userCollection")],
        ):
            current_refs = chunk.references.get("userCollection") if chunk.references else None
            current_collection_ids = [ref.uuid for ref in (current_refs.objects if current_refs else [])]

            if collection_id in current_collection_ids:
                continue

            await chunks_collection.data.reference_add(
                from_uuid=chunk.uuid,
                from_property="userCollection",
                to=collection_id,
            )

        await document_collection.data.reference_add(
            from_uuid=document_id,
            from_property="collection",
            to=collection_id,
        )

    async def remove_document(self, document_id: UUID, collection_id: UUID) -> None:
        """Removes a document from a collection by deleting the reference between them."""
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)

        await document_collection.data.reference_delete(
            from_uuid=document_id,
            from_property="collection",
            to=collection_id,
        )

        # Remove the collection reference from chunks that belong to the document
        # and currently reference the target collection. Not using _paginate_objects
        # here on purpose: each removed reference shrinks the matching result set,
        # so re-querying from offset 0 every time (rather than advancing an offset
        # over what looks like a stable set) is what makes this converge correctly.
        chunk_filter = (
            Filter.by_ref("document").by_id().equal(document_id)
            & Filter.by_ref("userCollection").by_id().equal(collection_id)
        )
        page_size = 100

        while True:
            chunks_response = await chunks_collection.query.fetch_objects(
                filters=chunk_filter,
                limit=page_size,
            )

            if not chunks_response.objects:
                break

            for chunk in chunks_response.objects:
                await chunks_collection.data.reference_delete(
                    from_uuid=chunk.uuid,
                    from_property="userCollection",
                    to=collection_id,
                )

            if len(chunks_response.objects) < page_size:
                break

    ###########
    # Helpers #
    ###########

    def _is_in_collection(self, obj, collection_id: str) -> bool:
        """Whether obj's userCollection references include collection_id (requires return_references=[QueryReference(link_on="userCollection")] on the query)."""
        if obj.references and "userCollection" in obj.references:
            col_ids = [ref.uuid for ref in obj.references["userCollection"].objects]
            return UUID(str(collection_id)) in col_ids
        return False

    def _build_chunk(self, obj, in_collection: bool) -> Chunk:
        """Builds a Chunk from a raw Weaviate chunk object and a precomputed in_collection flag."""
        props = obj.properties
        return Chunk(
            id=obj.uuid,
            text=props['text'],
            order=props['order'],
            title=props['title'],
            end_paragraph=props['end_paragraph'],
            start_page_id=props['start_page_id'],
            from_page=props['from_page'],
            to_page=props['to_page'],
            in_collection=in_collection,
        )
