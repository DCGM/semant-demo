import logging
import weaviate
from time import time
from weaviate import use_async_with_custom, WeaviateAsyncClient
from weaviate.classes.query import Filter
from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding
from weaviate.classes.query import QueryReference
import weaviate.collections.classes.internal
from uuid import UUID
from ollama_proxy import OllamaProxy
from config import config
import asyncio

class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient):
        self.client = client
        self.ollama_proxy = OllamaProxy(config.OLLAMA_URLS)
        self.ollama_model = config.OLLAMA_MODEL
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")
        self.title_prompt = "Generate a title in Czech from the following text: \"{text}\" \n " \
                "The title should be relevant for this search query: \"{query}\" \n" \
                "If the the text is not relavant, write \"N/A\" \n"
        self.summary_prompt = "Generate a sort summary in Czech from the following text: \"{text}\" \n " \
                "The summary should be in a list of concise facts extracted from the text which are relevant for this search query: \"{query}\""           

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

    async def _process_with_llm(self, search_results: list[schemas.TextChunkWithDocument], search_request: schemas.SearchRequest) -> list[schemas.TextChunkWithDocument]:

        title_prompt_template = search_request.search_title_prompt if search_request.search_title_prompt else self.title_prompt
        summary_prompt_template = search_request.search_summary_prompt if search_request.search_summary_prompt else self.summary_prompt

        if search_request.search_title_generate:
            title_responses = [self.ollama_proxy.call_ollama(
                self.ollama_model,
                title_prompt_template.format(text=chunk.text, query=search_request.query)
            ) for chunk in search_results]
            title_responses = await asyncio.gather(*title_responses)
            for search_result, generated_title in zip(search_results, title_responses):
                search_result.query_title = generated_title

        if search_request.search_summary_generate:
            summary_responses = [self.ollama_proxy.call_ollama(
                self.ollama_model,
                summary_prompt_template.format(text=chunk.text, query=search_request.query)
            ) for chunk in search_results]
            summary_responses = await asyncio.gather(*summary_responses)
            for search_result, generated_summary in zip(search_results, summary_responses):
                search_result.query_summary = generated_summary

        return search_results
  

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
                return_references=QueryReference(link_on="document", return_properties=None)
            )
        elif search_request.type == schemas.SearchType.text:
            # Execute text search
            result = await self.chunk_col.query.bm25(
                query=search_request.query,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=None)
            )
        elif search_request.type == schemas.SearchType.vector:
            q_vector = await get_query_embedding(search_request.query)
            result = await self.chunk_col.query.near_vector(
                near_vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=None)
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

        # Process with LLM if needed
        if search_request.search_title_generate or search_request.search_summary_generate:
            results = await self._process_with_llm(results, search_request)

        response = schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry]
        )
        logging.info(f'Response created in {time() - t1:.2f} seconds')
        return response