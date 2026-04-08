
from datetime import datetime, timezone

from semant_demo.weaviate_search import WeaviateSearch
from semant_demo.schema.tags import Tag, PostTag, PatchTag
from semant_demo.schema.collections import Collection, PostCollection, PatchCollection
from semant_demo.schema.documents import Document, DocumentBrowse
from semant_demo.schema.collection_stats import CollectionStats
from uuid import UUID

from weaviate.classes.query import Filter, Sort, QueryReference
import logging


class WeaviateClient(WeaviateSearch):
    async def get_all_collections(self, user_id: str) -> list[Collection]:
        """
        Retrieves all collections for given user
        """
        usercollection_collection = self.client.collections.get(
            "UserCollection")

        filters = (
            Filter.by_property("user_id").equal(user_id)
        )
        response = await usercollection_collection.query.fetch_objects(
            filters=filters
        )
        collections = []
        for obj in response.objects:
            props = obj.properties
            collections.append(Collection(
                id=obj.uuid,
                name=props.get("name"),
                userId=props.get("user_id"),
                description=props.get("description"),
                createdAt=props.get("created_at"),
                updatedAt=props.get("updated_at"),
                color=props.get("color")
            ))
        return collections

    async def get_collection_by_id(self, collection_id: UUID) -> Collection | None:
        """
        Retrieves collection by its id, returns None if collection with given id does not exist
        """

        usercollection_collection = self.client.collections.get(
            "UserCollection")
        response = await usercollection_collection.query.fetch_object_by_id(collection_id)
        if response is None:
            return None
        props = response.properties
        return Collection(
            id=response.uuid,
            name=props.get("name"),
            userId=props.get("user_id"),
            description=props.get("description"),
            createdAt=props.get("created_at"),
            updatedAt=props.get("updated_at"),
            color=props.get("color")
        )

    async def get_collection_stats(self, collection_id: UUID) -> CollectionStats | None:
        """
        Computes aggregate statistics for one collection.
        """

        collection = await self.get_collection_by_id(collection_id)
        if collection is None:
            return None

        # Compute documents count
        documents_collection = self.client.collections.get("Documents")
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

        chunks_collection = self.client.collections.get("Chunks")
        chunks_count_response = await chunks_collection.aggregate.over_all(
            total_count=True,
            filters=chunks_filters
        )
        chunks_count = chunks_count_response.total_count or 0

        # Compute tags count
        tags_collection = self.client.collections.get("Tag")
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
        # Span belongs to selected collection if linked chunk OR linked tag belongs to that collection.

        spans_collection = self.client.collections.get("Span_test")

        spans_filters = (
            Filter.by_ref("text_chunk").by_ref(
                "userCollection").by_id().equal(collection_id)
            |
            Filter.by_ref("tag").by_ref(
                "userCollection").by_id().equal(collection_id)
        )

        annotations_count_response = await spans_collection.aggregate.over_all(
            total_count=True,
            filters=spans_filters,
        )
        annotations_count = annotations_count_response.total_count or 0

        return CollectionStats(
            collectionId=collection_id,
            documentsCount=documents_count,
            chunksCount=chunks_count,
            tagsCount=tags_count,
            annotationsCount=annotations_count,
        )

    async def create_collection(self, collection: PostCollection) -> UUID:
        """
        Creates new collection and returns its id
        """
        usercollection_collection = self.client.collections.get(
            "UserCollection")
        now = datetime.now(timezone.utc)

        uuid = await usercollection_collection.data.insert(
            properties={
                "name": collection.name,
                "user_id": collection.userId,
                "description": collection.description,
                "color": collection.color,
                "created_at": now,
                "updated_at": now
            }
        )
        return uuid

    async def update_collection(self, collection_id: UUID, collection: PatchCollection):
        """"
        Updates collection with given id, raises exception if collection with given id does not exist
        """
        usercollection_collection = self.client.collections.get(
            "UserCollection")
        now = datetime.now(timezone.utc)

        # PATCH semantics: update only fields that were actually sent by the client.
        properties = collection.model_dump(exclude_unset=True)
        properties["updated_at"] = now

        await usercollection_collection.data.update(
            uuid=collection_id,
            properties=properties
        )

    async def delete_collection(self, collection_id: UUID) -> None:
        """
        Deletes collection with given id.
        Before deleting the collection object itself, remove references to it
        from chunks, documents, and tags.
        """
        documents_collection = self.client.collections.get("Documents")
        chunks_collection = self.client.collections.get("Chunks")
        tags_collection = self.client.collections.get("Tag")
        usercollection_collection = self.client.collections.get(
            "UserCollection")

        page_size = 100

        async def remove_collection_refs(objects_collection, filters, from_property: str) -> None:
            while True:
                response = await objects_collection.query.fetch_objects(
                    filters=filters,
                    limit=page_size,
                )

                if not response.objects:
                    break

                for obj in response.objects:
                    await objects_collection.data.reference_delete(
                        from_uuid=obj.uuid,
                        from_property=from_property,
                        to=collection_id,
                    )

                if len(response.objects) < page_size:
                    break

        await remove_collection_refs(
            chunks_collection,
            Filter.by_ref("userCollection").by_id().equal(collection_id),
            "userCollection",
        )
        await remove_collection_refs(
            documents_collection,
            Filter.by_ref("collection").by_id().equal(collection_id),
            "collection",
        )
        await remove_collection_refs(
            tags_collection,
            Filter.by_ref("userCollection").by_id().equal(collection_id),
            "userCollection",
        )

        await usercollection_collection.data.delete_by_id(collection_id)

    async def get_document_by_id(self, document_id: str) -> Document | None:
        """
        Retrieves document by its id, returns None if document with given id does not exist
        """
        document_collection = self.client.collections.get("Documents")
        response = await document_collection.query.fetch_object_by_id(document_id)
        if response is None:
            return None
        props = response.properties
        return Document(
            id=response.uuid,
            **props
        )

    async def get_all_documents(self, collection_id: UUID | None = None) -> list[Document]:
        """
        Retrieves all documents - optionally can be filtered by collection id
        """
        document_collection = self.client.collections.get("Documents")
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

    async def browse_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = None,
        sort_desc: bool = False,
        collection_id: UUID | None = None,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        document_type: str | None = None
    ) -> DocumentBrowse:
        """
        Retrieves documents in pages with optional filters for browsing large datasets.
        """
        document_collection = self.client.collections.get("Documents")
        filters = None

        def append_filter(current_filter, new_filter):
            return new_filter if current_filter is None else current_filter & new_filter

        if collection_id is not None:
            filters = append_filter(
                filters,
                Filter.by_ref("collection").by_id().equal(collection_id)
            )

        if title:
            filters = append_filter(
                filters, Filter.by_property("title").like(f"*{title}*"))
        if author:
            filters = append_filter(
                filters, Filter.by_property("author").like(f"*{author}*"))
        if publisher:
            filters = append_filter(filters, Filter.by_property(
                "publisher").like(f"*{publisher}*"))
        if document_type:
            filters = append_filter(filters, Filter.by_property(
                "documentType").like(f"*{document_type}*"))

        sort = None
        if sort_by:
            sort = Sort.by_property(sort_by, ascending=not sort_desc)

        count_response = await document_collection.aggregate.over_all(
            filters=filters,
            total_count=True,
        )
        total_count = count_response.total_count or 0

        response = await document_collection.query.fetch_objects(
            filters=filters,
            limit=limit + 1,
            offset=offset,
            sort=sort,
        )

        objects = response.objects
        has_more = len(objects) > limit
        if has_more:
            objects = objects[:limit]

        items = [
            Document(
                id=obj.uuid,
                **obj.properties
            )
            for obj in objects
        ]

        return DocumentBrowse(
            items=items,
            hasMore=has_more,
            nextOffset=(offset + limit) if has_more else None,
            totalCount=total_count,
        )

    async def get_all_tags(self, collection_id: UUID | None = None) -> list[Tag]:
        """
        Retrieves all tags - optionally filtered by collection id.
        """
        tag_collection = self.client.collections.get("Tag")
        filters = None
        if collection_id is not None:
            filters = Filter.by_ref("userCollection").by_id().equal(collection_id)

        response = await tag_collection.query.fetch_objects(
            filters=filters,
            limit=1000,
            return_references=[QueryReference(link_on="userCollection", return_properties=["name"])],
        )

        tags: list[Tag] = []
        for obj in response.objects:
            props = obj.properties or {}

            tag_examples = [str(item) for item in props.get("tag_examples", [])]

            tags.append(
                Tag(
                    name=str(props.get("tag_name") or ""),
                    shorthand=str(props.get("tag_shorthand") or ""),
                    color=str(props.get("tag_color") or ""),
                    pictogram=str(props.get("tag_pictogram") or ""),
                    definition=str(props.get("tag_definition") or ""),
                    examples=tag_examples,
                    id=obj.uuid,
                )
            )

        return tags

    async def get_tag_by_id(self, collection_id: UUID, tag_uuid: UUID) -> Tag | None:
        """
        Retrieves one tag by id, scoped to a collection.
        Returns None if not found or if the tag is not linked to the collection.
        """
        tag_collection = self.client.collections.get("Tag")
        response = await tag_collection.query.fetch_object_by_id(
            tag_uuid,
            return_references=[QueryReference(link_on="userCollection")],
        )

        if response is None:
            return None

        refs = response.references or {}
        collection_refs = refs.get("userCollection")
        if not collection_refs or not any(ref.uuid == collection_id for ref in collection_refs.objects):
            return None

        props = response.properties or {}
        return Tag(
            name=str(props.get("tag_name") or ""),
            shorthand=str(props.get("tag_shorthand") or ""),
            color=str(props.get("tag_color") or ""),
            pictogram=str(props.get("tag_pictogram") or ""),
            definition=str(props.get("tag_definition") or ""),
            examples=[str(item) for item in props.get("tag_examples", [])],
            id=response.uuid,
        )

    async def create_tag(self, collection_id: UUID, tag: PostTag) -> Tag:
        """
        Creates a new tag under given collection and links the tag to that collection.
        If an exact same tag already exists in the same collection, returns existing one.
        """
        collection = await self.get_collection_by_id(collection_id)
        if collection is None:
            raise ValueError("Collection not found")

        tag_collection = self.client.collections.get("Tag")

        filters = Filter.by_ref("userCollection").by_id().equal(collection_id)
        existing = await tag_collection.query.fetch_objects(
            filters=filters,
            limit=1000,
            return_references=[QueryReference(link_on="userCollection", return_properties=["name"])],
        )

        normalized_examples = [example for example in tag.examples if example.strip()]
        normalized_examples_set = set(normalized_examples)
        tag_name = tag.name.strip()
        tag_shorthand = tag.shorthand.strip()
        tag_color = tag.color.strip()
        tag_pictogram = tag.pictogram.strip()
        tag_definition = tag.definition.strip()

        for obj in existing.objects:
            props = obj.properties or {}
            existing_examples = [str(item) for item in (props.get("tag_examples") or [])]
            if (
                str(props.get("tag_name") or "").strip() == tag_name
                and str(props.get("tag_shorthand") or "").strip() == tag_shorthand
                and str(props.get("tag_color") or "").strip() == tag_color
                and str(props.get("tag_pictogram") or "").strip() == tag_pictogram
                and str(props.get("tag_definition") or "").strip() == tag_definition
                and set(existing_examples) == normalized_examples_set
            ):
                return Tag(
                    name=str(props.get("tag_name") or ""),
                    shorthand=str(props.get("tag_shorthand") or ""),
                    color=str(props.get("tag_color") or ""),
                    pictogram=str(props.get("tag_pictogram") or ""),
                    definition=str(props.get("tag_definition") or ""),
                    examples=[str(item) for item in existing_examples],
                    id=obj.uuid,
                )

        new_tag_uuid = await tag_collection.data.insert(
            properties={
                "tag_name": tag.name,
                "tag_shorthand": tag.shorthand,
                "tag_color": tag.color,
                "tag_pictogram": tag.pictogram,
                "tag_definition": tag.definition,
                "tag_examples": normalized_examples,
            }
        )

        await tag_collection.data.reference_add(
            from_uuid=new_tag_uuid,
            from_property="userCollection",
            to=collection_id,
        )

        return Tag(
            name=tag.name,
            shorthand=tag.shorthand,
            color=tag.color,
            pictogram=tag.pictogram,
            definition=tag.definition,
            examples=normalized_examples,
            id=new_tag_uuid,
        )

    async def delete_tag(self, collection_id: UUID, tag_uuid: UUID) -> None:
        """
        Deletes a tag after removing every reference to it from Span and Chunk collections.
        """
        tag_collection = self.client.collections.get("Tag")
        span_collection = self.client.collections.get("Span_test")
        chunk_collection = self.client.collections.get("Chunks")

        tag_response = await tag_collection.query.fetch_object_by_id(
            tag_uuid,
            return_references=[QueryReference(link_on="userCollection")],
        )
        if tag_response is None:
            raise ValueError("Tag not found")

        tag_refs = tag_response.references or {}
        collection_refs = tag_refs.get("userCollection")
        if not collection_refs or not any(ref.uuid == collection_id for ref in collection_refs.objects):
            raise ValueError("Tag not found")

        page_size = 100

        span_filter = Filter.by_ref("tag").by_id().equal(tag_uuid)
        while True:
            span_response = await span_collection.query.fetch_objects(
                filters=span_filter,
                limit=page_size,
                return_references=[QueryReference(link_on="tag")],
            )

            if not span_response.objects:
                break

            for span_obj in span_response.objects:
                await span_collection.data.reference_delete(
                    from_uuid=span_obj.uuid,
                    from_property="tag",
                    to=tag_uuid,
                )

            if len(span_response.objects) < page_size:
                break

        chunk_filter = (
            Filter.by_ref("automaticTag").by_id().equal(tag_uuid)
            | Filter.by_ref("positiveTag").by_id().equal(tag_uuid)
            | Filter.by_ref("negativeTag").by_id().equal(tag_uuid)
        )
        chunk_reference_names = ("automaticTag", "positiveTag", "negativeTag")

        while True:
            chunk_response = await chunk_collection.query.fetch_objects(
                filters=chunk_filter,
                limit=page_size,
                return_references=[
                    QueryReference(link_on=ref_name)
                    for ref_name in chunk_reference_names
                ],
            )

            if not chunk_response.objects:
                break

            for chunk_obj in chunk_response.objects:
                refs = chunk_obj.references or {}
                for ref_name in chunk_reference_names:
                    current_refs = refs.get(ref_name)
                    if current_refs and any(ref.uuid == tag_uuid for ref in current_refs.objects):
                        await chunk_collection.data.reference_delete(
                            from_uuid=chunk_obj.uuid,
                            from_property=ref_name,
                            to=tag_uuid,
                        )

            if len(chunk_response.objects) < page_size:
                break

        await tag_collection.data.delete_by_id(tag_uuid)

    async def update_tag(self, collection_id: UUID, tag_uuid: UUID, updated_tag: PatchTag) -> None:
        """
        Updates an existing tag in a collection.
        """
        tag_collection = self.client.collections.get("Tag")

        tag_response = await tag_collection.query.fetch_object_by_id(
            tag_uuid,
            return_references=[QueryReference(link_on="userCollection")],
        )
        if tag_response is None:
            raise ValueError("Tag not found")

        tag_refs = tag_response.references or {}
        collection_refs = tag_refs.get("userCollection")
        if not collection_refs or not any(ref.uuid == collection_id for ref in collection_refs.objects):
            raise ValueError("Tag not found")


        patch_data = updated_tag.model_dump(exclude_unset=True, exclude_none=True)
        if not patch_data:
            raise ValueError("No fields provided for update")

        properties_to_update: dict[str, str | list[str]] = {}

        if "name" in patch_data:
            properties_to_update["tag_name"] = str(patch_data["name"])
        if "shorthand" in patch_data:
            properties_to_update["tag_shorthand"] = str(patch_data["shorthand"])
        if "color" in patch_data:
            properties_to_update["tag_color"] = str(patch_data["color"])
        if "pictogram" in patch_data:
            properties_to_update["tag_pictogram"] = str(patch_data["pictogram"])
        if "definition" in patch_data:
            properties_to_update["tag_definition"] = str(patch_data["definition"])
        if "examples" in patch_data:
            properties_to_update["tag_examples"] = [
                str(example) for example in patch_data["examples"] if str(example).strip()
            ]

        await tag_collection.data.update(
            uuid=tag_uuid,
            properties=properties_to_update,
        )

    async def add_document_to_collection(self, document_id: UUID, collection_id: UUID) -> bool:
        """
        Adds a document to a collection and also links all its chunks to that collection.
        """
        document_collection = self.client.collections.get("Documents")
        chunks_collection = self.client.collections.get("Chunks")
        try:
            matched_chunks = 0
            already_linked_chunks = 0
            added_chunks = 0

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
                    matched_chunks += 1
                    current_refs = chunk.references.get(
                        "userCollection") if chunk.references else None
                    current_collection_ids = [ref.uuid for ref in (
                        current_refs.objects if current_refs else [])]

                    if collection_id in current_collection_ids:
                        already_linked_chunks += 1
                        continue

                    await chunks_collection.data.reference_add(
                        from_uuid=chunk.uuid,
                        from_property="userCollection",
                        to=collection_id,
                    )
                    added_chunks += 1

                if len(chunks_response.objects) < page_size:
                    break

                offset += page_size

            await document_collection.data.reference_add(
                from_uuid=document_id,
                from_property="collection",
                to=collection_id,
            )

            logging.info(
                "add_document_to_collection summary for document %s and collection %s: matched_chunks=%d, already_linked=%d, added=%d",
                document_id,
                collection_id,
                matched_chunks,
                already_linked_chunks,
                added_chunks,
            )

            return True
        except Exception as e:
            logging.error(
                f"Failed to add document {document_id} to collection {collection_id}: {e}")
            return False

    async def remove_document_from_collection(self, document_id: UUID, collection_id: UUID) -> bool:
        """
        Removes a document from a collection by deleting the reference between them.
        """
        document_collection = self.client.collections.get("Documents")
        chunks_collection = self.client.collections.get("Chunks")
        try:
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

            return True
        except Exception as e:
            logging.error(
                f"Failed to remove document {document_id} from collection {collection_id}: {e}")
            return False
