import logging
from time import time
import weaviate
import weaviate.collections.classes.internal
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryNested

from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding, get_hyde_document_embedding
from weaviate.classes.query import QueryReference
from .config import config

import logging

from weaviate.collections.classes.grpc import QueryReference

class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient):
        self.client = client
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")

        try:
            self.tagspan_col = self.client.collections.get("TagSpan_test")
        except Exception:
            self.tagspan_col = None

    # TagSpans
    async def set_chunk_spans_embedded(self, chunk_id: str, spans: list[schemas.TagSpan]):
        """
        Add new TagSpan to Chunks_test's 'tagSpansArr'.
        """
        payloads = []
        for s in spans:
            payloads.append({
                "tagId": s.tagId,
                "start": s.start,
                "end": s.end,
            })

        await self.chunk_col.data.update(
            uuid=chunk_id,
            properties={"tagSpansArr": payloads}
        )

    async def set_chunk_spans_separate(self, chunk_id: str, spans: list[schemas.TagSpan]):
        """
        Add new TagSpan to TagSpan2_test table with Chunk ID (not as reference)
        """
        if not self.tagspan_col:
            raise RuntimeError("TagSpan2_test collection not available")

        # clear existing for this chunk
        await self.tagspan_col.data.delete_many(where=Filter.by_property("chunkId").equal(chunk_id))

        for s in spans:
            await self.tagspan_col.data.insert(
                properties={
                    "tagId": s.tagId,
                    "start": s.start,
                    "end": s.end,
                    "chunkId": chunk_id
                }
            )

    async def get_chunk_spans_separate(self, chunk_id: str) -> list[schemas.TagSpan]:
        """
        Get TagSpans from TagSpans2_test table by chunk id.
        """
        if not self.tagspan_col:
            raise RuntimeError("TagSpan2_test collection not available")

        response = await self.tagspan_col.query.fetch_objects(
            filters=Filter.by_property("chunkId").equal(chunk_id),
            return_properties=["tagId", "start", "end"]
        )

        # add TagSpan ID
        return [
            schemas.TagSpan(
                id=str(obj.uuid),
                tagId=obj.properties.get("tagId"),
                start=obj.properties.get("start"),
                end=obj.properties.get("end")
            )
            for obj in response.objects
        ]

    async def get_chunk_spans_embedded(self, chunk_id: str) -> list[schemas.TagSpan]:
        """
        Get TagSpans from Chunks_test's 'tagSpansArr'
        """
        obj = await self.chunk_col.query.fetch_object_by_id(
            uuid=chunk_id,
            return_properties=[
                QueryNested(
                    name="tagSpansArr",
                    properties=["tagId", "start", "end"]
                )
            ]
        )

        if not obj or "tagSpansArr" not in obj.properties or obj.properties["tagSpansArr"] is None:
            return []

        raw_spans = obj.properties["tagSpansArr"]

        return [
            schemas.TagSpan(
                tagId=s.get("tagId"),
                start=s.get("start"),
                end=s.get("end")
            )
            for s in raw_spans
        ]

    async def update_tag_span_embedded(self, chunk_id: str, index: int, update_data: dict):
        """
        Update TagSpan's informations like start, end, ...
        """
        # load TagSpan
        obj = await self.chunk_col.query.fetch_object_by_id(
            uuid=chunk_id,
            return_properties=[
                QueryNested(name="tagSpansArr", properties=[
                            "tagId", "start", "end", "confidence", "note"])
            ]
        )

        if not obj or "tagSpansArr" not in obj.properties:
            raise ValueError("Chunk or TagSpans not found")

        spans = obj.properties["tagSpansArr"]

        if index < 0 or index >= len(spans):
            raise IndexError("Index out of boundries")

        # update necessary fields
        for key, value in update_data.items():
            if value is not None:
                spans[index][key] = value

        # update in db
        await self.chunk_col.data.update(
            uuid=chunk_id,
            properties={"tagSpansArr": spans}
        )

    async def update_tag_span_separate(self, span_id: str, update_data: dict):
        """
        Update TagSpan's informations like start, end, ...
        """
        if not self.tagspan_col:
            raise RuntimeError("Kolekce TagSpan2_test není dostupná")

        await self.tagspan_col.data.update(
            uuid=span_id,
            properties=update_data
        )
    # /TagSpans

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
                Filter.by_ref(link_on="document").by_property("yearIssued").greater_or_equal(search_request.min_year)
            )
        if search_request.max_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").less_or_equal(search_request.max_year)
            )
        if search_request.language:
            filters.append(Filter.by_property("language").equal(search_request.language))

        tagFilters = []
        if search_request.tag_uuids:
            logging.info(search_request.tag_uuids)
            if search_request.automatic:
                tagFilters.append(Filter.by_ref("automaticTag").by_id().contains_any(search_request.tag_uuids))
            if search_request.positive:
                tagFilters.append(Filter.by_ref("positiveTag").by_id().contains_any(search_request.tag_uuids))

        combined_tag_filters = None
        if tagFilters:
            combined_tag_filters = tagFilters[0]
            for f in tagFilters[1:]:
                combined_tag_filters = combined_tag_filters | f

        if combined_tag_filters:
            filters.append(combined_tag_filters)
            
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
            if search_request.is_hyde == False:
                q_vector = await get_query_embedding(search_request.query)
            else:
                q_vector = await get_hyde_document_embedding(search_request.query)

            # Execute hybrid search
            result = await self.chunk_col.query.hybrid(
                query=search_request.query,
                alpha=search_request.hybrid_search_alpha,
                vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=document_properties_to_return),
                    # TODO: Do not fetch tags if not needed. (xtomas36)
                    QueryReference(
                        link_on="automaticTag",                 # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
            )
        elif search_request.type == schemas.SearchType.text:
            # Execute text search
            result = await self.chunk_col.query.bm25(
                query=search_request.query,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=document_properties_to_return),
                         QueryReference(
                        link_on="automaticTag",                 # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
            )
        elif search_request.type == schemas.SearchType.vector:
            if search_request.is_hyde == False:
                q_vector = await get_query_embedding(search_request.query)
            else:
                q_vector = await get_hyde_document_embedding(search_request.query)

            result = await self.chunk_col.query.near_vector(
                near_vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=[QueryReference(link_on="document", return_properties=document_properties_to_return),
                    QueryReference(
                        link_on="automaticTag",                 # the reference property
                        return_properties=["uuid", "tag_name"]  # properties from the referenced tags
                    ),
                    QueryReference(
                        link_on="positiveTag",
                        return_properties=["uuid", "tag_name"]
                    ),
                ]
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

        # helper to extract UUID strings from reference block
        def ref_uuids(ref_block):
            if not ref_block:
                return []
            return [str(r.uuid) for r in ref_block.objects]
        tags_result = []

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

            # add tag info for this chunk
            refs = obj.references or {}

            auto_ids = ref_uuids(refs.get("automaticTag"))
            pos_ids = ref_uuids(refs.get("positiveTag"))

            requested_ids = search_request.tag_uuids

            auto_ids = list(set(auto_ids) & set(requested_ids))
            pos_ids = list(set(pos_ids) & set(requested_ids))
            tags_result.append({'chunk_id': str(chunk.id), 'positive_tags_ids': pos_ids, 'automatic_tags_ids': auto_ids})

        response = schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry],
            tags_result=tags_result,
        )
        logging.info(f'Response created in {time() - t1:.2f} seconds')
        return response
    