from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

import logging
from time import time
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from semant_demo.gemma_embedding import get_query_embedding, get_hyde_document_embedding
from weaviate.classes.query import QueryReference

import logging
from typing import Any

from semant_demo.weaviate_utils.helpers import WeaviateHelpers

class TextChunk():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.helpers = WeaviateHelpers(client, collectionNames)
        self.chunk_collection = self.client.collections.get(collectionNames.chunks_collection_name)
        self.span_collection = self.client.collections.get(collectionNames.span_collection_name)
        self.user_collection = self.client.collections.get(collectionNames.user_collection_name)

    #######
    # API #
    #######
    async def read(self):
        filters = Filter()
        return await self.helpers.fetch_chunks(filters=filters)

    async def search(
        self,
        search_request: schemas.SearchRequest,
        filters: list[Any] | None = None
    ) -> schemas.SearchResponse:
        # Build filters
        query_filters = []
        if search_request.user_collection_id:
            query_filters.append(
                Filter.by_ref(link_on=self.helpers.collectionNames.user_collection_link_name)
                .by_id()
                .equal(search_request.user_collection_id)
            )

        if filters is None:
            # legacy fallback
            # TODO: Remove when all usages are updated
            if search_request.min_year:
                query_filters.append(Filter.by_ref(link_on="document").by_property("yearIssued").greater_or_equal(search_request.min_year))
            if search_request.max_year:
                query_filters.append(Filter.by_ref(link_on="document").by_property("yearIssued").less_or_equal(search_request.max_year))
            if search_request.language:
                query_filters.append(Filter.by_property("language").equal(search_request.language))
        else:
            query_filters.extend(filters)

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
            query_filters.append(combined_tag_filters)
            
        # Combine with AND logic
        combined_filter = None
        if query_filters:
            combined_filter = query_filters[0]
            for f in query_filters[1:]:
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
            result = await self.chunk_collection.query.hybrid(
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
            result = await self.chunk_collection.query.bm25(
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

            result = await self.chunk_collection.query.near_vector(
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

    def get_tags():
        pass

    async def filterChunksByTags(self, requestedData: schemas.FilterChunksByTagsRequest):
        """
        Filters chunks by tags - for search results filtration after initial search
        get tag objects, chunk objects,
        then filter the chunks that has positive tags and automatic tags referces to any of
        the selected tags and return the data
        """
        try:
            # get all chunks from the list and filter them by the tag
            filters = [Filter.by_id().contains_any([str(uuid) for uuid in requestedData.chunkIds])]
            if requestedData.positive:
                filters.append(Filter.by_ref("automaticTag").by_id().contains_any(requestedData.tagIds))
            if requestedData.automatic:
                filters.append(Filter.by_ref("positiveTag").by_id().contains_any(requestedData.tagIds))
            combinedFilters = filters[0]
            for f in filters[1:]:
                combinedFilters |= f

            chunk_results = await self.helpers.fetch_chunks(filters=combinedFilters)

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            resultLst = []
            for chunk in chunk_results:
                refs = chunk.references or {}

                auto_ids = ref_uuids(refs.get("automaticTag"))
                pos_ids = ref_uuids(refs.get("positiveTag"))

                requested_ids = requestedData.tagIds

                auto_ids = list(set(auto_ids) & set(requested_ids))
                pos_ids = list(set(pos_ids) & set(requested_ids))
                resultLst.append({'chunk_id': str(chunk.uuid), 'positive_tags_ids': pos_ids, 'automatic_tags_ids': auto_ids})
            logging.info(f'"chunkTags": {resultLst} ')
            return { "chunkTags": resultLst }
        except Exception as e:
            logging.error(f"Error in chunk filtering: {e}")
            return { "chunkTags": [] }

    ###########
    # Helpers #
    ###########


    