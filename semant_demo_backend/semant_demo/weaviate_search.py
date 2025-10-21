import logging
from time import time

import weaviate
import weaviate.collections.classes.internal
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding
from weaviate.classes.query import QueryReference



class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient):
        self.client = client
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")

    @classmethod
    async def create(cls, config:Config) -> "WeaviateSearch":
        # Instantiate async client with custom params
        async_client = weaviate.use_async_with_custom(
            http_host=config.WEAVIATE_HOST, http_port=config.WEAVIATE_REST_PORT, http_secure=False,
            grpc_host=config.WEAVIATE_HOST, grpc_port=config.WEAVIATE_GRPC_PORT, grpc_secure=False,
        )
        # Connect and verify readiness
        await async_client.connect()  # :contentReference[oaicite:0]{index=0}
        if not await async_client.is_ready():  # :contentReference[oaicite:1]{index=1}
            logging.error("Weaviate is not ready.")
            await async_client.close()
            exit(-1)

        return cls(async_client)

    async def close(self):
        await self.client.close()  # :contentReference[oaicite:2]{index=2}

    async def search(self, search_request: schemas.SearchRequest) -> schemas.SearchResponse:
        # Build filters
        filters = []
        if search_request.min_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").greater_than(search_request.min_year)
            )
        if search_request.max_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").less_than(search_request.max_year)
            )
        if search_request.language:
            filters.append(Filter.by_property("language").equal(search_request.language))

        # Combine with AND logic
        combined_filter = None
        if filters:
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter &= f


        document_properties_to_return = [
                "library", "title", "subTitle", "partNumber", "partName",
                "yearIssued", "dateIssued", "authors", "publisher", "description",
                "url", "public", "documentType", "keywords", "genre", "placeTerm",
                "section", "region", "id_code"
        ]

        t1 = time()
        if search_request.type == schemas.SearchType.hybrid:
            q_vector = await get_query_embedding(search_request.query)

            # Execute hybrid search
            result = await self.chunk_col.query.hybrid(
                query=search_request.query,
                alpha=1,
                vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=document_properties_to_return)
            )
        elif search_request.type == schemas.SearchType.text:
            # Execute text search
            result = await self.chunk_col.query.bm25(
                query=search_request.query,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=document_properties_to_return)
            )
        elif search_request.type == schemas.SearchType.vector:
            q_vector = await get_query_embedding(search_request.query)
            result = await self.chunk_col.query.near_vector(
                near_vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=document_properties_to_return)
            )
        else:
            raise ValueError(f"Unknown search type: {search_request.type}")

        search_time = time() - t1

        # Parse results
        results: list[schemas.TextChunkWithDocument] = []
        log_entry = (
            f"Top {len(result.objects)} results for “{search_request.query}”. "
            f"Retrieved in {search_time:.2f} seconds:"
        )
        logging.info(log_entry)
        for obj in result.objects:
            chunk_data = obj.properties
            doc_objs = obj.references.get("document").objects
            if not doc_objs:
                continue
            first_doc = doc_objs[0]
            if "library" not in first_doc.properties or not first_doc.properties["library"]:
                first_doc.properties["library"] = "mzk"

            document_obj = schemas.Document(
                id=first_doc.uuid,
                **first_doc.properties,
            )
            chunk = schemas.TextChunkWithDocument(
                id=obj.uuid,
                **chunk_data,
                document_object=document_obj,
                document=first_doc.uuid
            )
            chunk.text = chunk.text.replace("-\n", "").replace("\n", " ")
            results.append(chunk)

        response = schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry]
        )

        logging.info(f'Response created in {time() - t1:.2f} seconds')
        return response
