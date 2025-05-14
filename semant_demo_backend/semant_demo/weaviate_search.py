import logging
import weaviate
from weaviate import use_async_with_custom, WeaviateAsyncClient
from weaviate.connect import ConnectionParams
from weaviate.classes.query import Filter
import schemas
from time import time
from config import Config
from gemma_embedding import get_query_embedding


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

        q_vector = await get_query_embedding(search_request.query)

        # Execute hybrid search
        t1 = time()
        result = await self.chunk_col.query.hybrid(
            query=search_request.query,
            alpha=1,
            vector=q_vector,
            limit=search_request.limit,
            filters=combined_filter,
            return_references=["document"],
        )
        search_time = time() - t1

        # Parse results
        results = []
        log_entry = (
            f"Top {len(result.objects)} results for “{search_request.query}”. "
            f"Retrieved in {search_time:.2f} seconds:"
        )
        logging.info(log_entry)
        for obj in result.objects:
            doc_props = obj.references.get("document", [{}])[0].get("properties", {})
            document = schemas.Document(**doc_props)
            chunk = schemas.TextChunkWithDocument(
                id=obj.id,
                text=obj.properties.get("text", "<no text>"),
                start_page_id=obj.properties.get("start_page_id"),
                from_page=obj.properties.get("from_page"),
                to_page=obj.properties.get("to_page"),
                end_paragraph=obj.properties.get("end_paragraph"),
                language=obj.properties.get("language"),
                document=obj.properties.get("document"),
                document_object=document
            )
            results.append(chunk)

        return schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry]
        )