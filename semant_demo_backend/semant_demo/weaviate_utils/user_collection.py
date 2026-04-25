import semant_demo.schemas as schemas

import logging
from uuid import UUID
from datetime import datetime, timezone

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

from semant_demo.weaviate_utils.helpers import WeaviateHelpers
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
            # filter collections by user
            filters = (
                Filter.by_property("user_id").equal(user.id)
            )
            results = await self.client.collections.get(self.collectionNames.user_collection_name).query.fetch_objects(
                filters=filters
            )
            logging.info(f"User Id: {user.id}\nRaw results: {results}")
            collections_response = []
            if results.objects is not None:
                if len(results.objects) > 0:
                    collections = results.objects
                    # map collection data to expected response format
                    for o in collections:
                        props = o.properties
                        collections_response.append(Collection(
                            id=o.uuid,
                            name=props.get("name"),
                            owner=props.get("owner"),
                            description=props.get("description"),
                            created_at=props.get("created_at"),
                            updated_at=props.get("updated_at"),
                            color=props.get("color")
                        ))

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
        # Span belongs to selected collection if it references at least one chunk that belongs to the collection.

        spans_collection = self.client.collections.get(
            self.collectionNames.span_collection_name)

        spans_filters = (
            Filter.by_ref("text_chunk").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
            &
            Filter.by_ref("tag").by_ref(
                self.collectionNames.user_collection_name).by_id().equal(collection_id)
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
        )
        spans_agg_response = await spans_collection.aggregate.over_all(
            filters=spans_filter,
            total_count=True,
        )
        annotations_count = spans_agg_response.total_count or 0

        # Distinct tags used in those spans
        distinct_tag_ids: set[str] = set()
        if annotations_count > 0:
            spans_objects = await spans_collection.query.fetch_objects(
                filters=spans_filter,
                limit=10000,
                return_references=[QueryReference(link_on="tag")],
            )
            for obj in spans_objects.objects:
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

    async def add_chunk(self, chunk_id: str, collection_id: str):
        # 1. Add reference from the chunk to the target collection
        result = await self.helpers.create_reference(chunk_id,
                                                     self.collectionNames.chunks_collection_name,
                                                     self.collectionNames.user_collection_link_name,
                                                     collection_id)

        # 2. Find the document the chunk belongs to and link it to the collection
        try:
            chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
            chunk_obj = await chunks_collection.query.fetch_object_by_id(
                chunk_id,
                return_references=[QueryReference(link_on="document")]
            )

            if chunk_obj and chunk_obj.references and "document" in chunk_obj.references:
                doc_refs = chunk_obj.references["document"].objects
                for doc_ref in doc_refs:
                    document_id = doc_ref.uuid
                    
                    document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
                    # Add reference from the document (property "collection") to the given user collection
                    await document_collection.data.reference_add(
                        from_uuid=document_id,
                        from_property="collection",
                        to=collection_id,
                    )
        except Exception as e:
            logging.error(f"Failed to link chunk's document to collection: {e}")

        return result

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

    def share():
        pass

    def unshare():
        pass

    def read_shared_users():
        pass

    async def add_document(self, document_id: str, collection_id: str) -> None:
        """
        Adds a document to a collection and also links all its chunks to that collection.
        """
        document_collection = self.client.collections.get(
            self.collectionNames.document_collection_name)
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)

        # Add collection reference to every chunk that belongs to the document.
        chunk_filter = Filter.by_ref("document").by_id().equal(document_id)
        offset = 0
        page_size = 100

        while True:
            chunks_response = await chunks_collection.query.fetch_objects(
                filters=chunk_filter,
                return_references=[QueryReference(
                    link_on="userCollection")],
                limit=page_size,
                offset=offset,
            )

            if not chunks_response.objects:
                break

            for chunk in chunks_response.objects:
                current_refs = chunk.references.get(
                    "userCollection") if chunk.references else None
                current_collection_ids = [ref.uuid for ref in (
                    current_refs.objects if current_refs else [])]

                if collection_id in current_collection_ids:
                    continue

                await chunks_collection.data.reference_add(
                    from_uuid=chunk.uuid,
                    from_property="userCollection",
                    to=collection_id,
                )

            if len(chunks_response.objects) < page_size:
                break

            offset += page_size

        await document_collection.data.reference_add(
            from_uuid=document_id,
            from_property="collection",
            to=collection_id,
        )

    async def remove_document(self, document_id: UUID, collection_id: UUID) -> None:
        """
        Removes a document from a collection by deleting the reference between them.
        """
        document_collection = self.client.collections.get(
            self.collectionNames.document_collection_name)
        chunks_collection = self.client.collections.get(
            self.collectionNames.chunks_collection_name)

        await document_collection.data.reference_delete(
            from_uuid=document_id,
            from_property="collection",
            to=collection_id,
        )

        # Remove collection reference only from chunks that belong to the document
        # and currently reference the target collection.
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
