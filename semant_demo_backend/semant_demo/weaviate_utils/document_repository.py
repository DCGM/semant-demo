from weaviate.classes.query import Filter, Sort, QueryReference

import semant_demo.schemas as schemas
from semant_demo.weaviate_utils.base_repository import WeaviateBaseRepository
from semant_demo.schema.documents import DocumentBrowse, Document as DocumentSchema


class DocumentRepository(WeaviateBaseRepository):
    """
    Repository for the Weaviate document collection.

    Documents are ingested through a separate pipeline outside this API
    layer, so create/update/delete are not supported here and raise
    NotImplementedError - they only exist to satisfy the base CRUD interface.
    """

    #########
    # CRUD  #
    #########

    async def create(self, *args, **kwargs):
        raise NotImplementedError("Documents are managed by the ingestion pipeline, not this API layer")

    async def read(self, document_id: str) -> DocumentSchema | None:
        """
        Retrieves a document by its id.

        Args:
            document_id: UUID of the document.

        Returns:
            The document, or None if no document with this id exists.

        Raises:
            weaviate.exceptions.WeaviateBaseError: on connection/query/server failures.
        """
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        response = await document_collection.query.fetch_object_by_id(document_id)
        if response is None:
            return None
        return DocumentSchema(id=response.uuid, **response.properties)

    async def read_all(self, *args, **kwargs):
        raise NotImplementedError("Listing all documents is unsupported - use browse() for paginated/filtered listing")

    async def update(self, *args, **kwargs):
        raise NotImplementedError("Documents are managed by the ingestion pipeline, not this API layer")

    async def delete(self, *args, **kwargs):
        raise NotImplementedError("Documents are managed by the ingestion pipeline, not this API layer")

    #######################
    # Additional queries  #
    #######################

    async def read_chunks(self, document_id: str, collection_id: str) -> schemas.DocumentDetail | None:
        """
        Retrieves a document together with all its chunks, marking which chunks
        belong to the given user collection.

        Args:
            document_id: UUID of the document.
            collection_id: UUID of the user collection used to mark chunk membership.

        Returns:
            The document and its chunks, or None if the document does not exist.

        Raises:
            weaviate.exceptions.WeaviateBaseError: on connection/query/server failures.
        """
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        document_response = await document_collection.query.fetch_object_by_id(document_id)
        if document_response is None:
            return None

        doc_props = document_response.properties
        if "library" not in doc_props or not doc_props["library"]:
            doc_props["library"] = "mzk"

        document = schemas.Document(id=document_response.uuid, **doc_props)

        chunks_collection = self.client.collections.get(self.collectionNames.chunks_collection_name)
        chunk_filter = Filter.by_ref("document").by_id().equal(document_id)

        chunks: list[schemas.DocumentDetailTextChunkWithUserCollectionInfo] = []
        async for chunk_obj in self._paginate_objects(
            chunks_collection,
            filters=chunk_filter,
            page_size=100,
            return_references=[QueryReference(link_on="userCollection")],
        ):
            chunk_refs = chunk_obj.references.get("userCollection") if chunk_obj.references else None
            current_collection_ids = [str(ref.uuid) for ref in (chunk_refs.objects if chunk_refs else [])]
            in_user_collection = str(collection_id) in current_collection_ids

            chunks.append(
                schemas.DocumentDetailTextChunkWithUserCollectionInfo(
                    id=chunk_obj.uuid,
                    **chunk_obj.properties,
                    document=document_response.uuid,
                    in_user_collection=in_user_collection,
                )
            )

        return schemas.DocumentDetail(document=document, chunks=chunks)

    async def browse(
        self,
        collection_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str | None = None,
        sort_desc: bool = False,
        title: str | None = None,
        author: str | None = None,
        publisher: str | None = None,
        document_type: str | None = None,
    ) -> DocumentBrowse:
        """
        Retrieves documents page by page with optional filters, for browsing large datasets.

        Args:
            collection_id: only return documents that belong to this user collection.
            limit: page size (max number of documents to return).
            offset: number of documents to skip.
            sort_by: property name to sort by.
            sort_desc: sort descending instead of ascending.
            title: substring filter on the title property.
            author: substring filter on the author property.
            publisher: substring filter on the publisher property.
            document_type: substring filter on the documentType property.

        Returns:
            A page of documents plus pagination metadata.

        Raises:
            weaviate.exceptions.WeaviateBaseError: on connection/query/server failures.
        """
        document_collection = self.client.collections.get(self.collectionNames.document_collection_name)
        filters = None

        def append_filter(current_filter, new_filter):
            return new_filter if current_filter is None else current_filter & new_filter

        if collection_id is not None:
            filters = append_filter(filters, Filter.by_ref("collection").by_id().equal(collection_id))
        if title:
            filters = append_filter(filters, Filter.by_property("title").like(f"*{title}*"))
        if author:
            filters = append_filter(filters, Filter.by_property("author").like(f"*{author}*"))
        if publisher:
            filters = append_filter(filters, Filter.by_property("publisher").like(f"*{publisher}*"))
        if document_type:
            filters = append_filter(filters, Filter.by_property("documentType").like(f"*{document_type}*"))

        sort = None
        if sort_by:
            sort = Sort.by_property(sort_by, ascending=not sort_desc)

        count_response = await document_collection.aggregate.over_all(filters=filters, total_count=True)
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

        items = [DocumentSchema(id=obj.uuid, **obj.properties) for obj in objects]

        return DocumentBrowse(
            items=items,
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
            total_count=total_count,
        )

