from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
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

import logging
from time import time
import weaviate
import weaviate.collections.classes.internal
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding, get_hyde_document_embedding
from weaviate.classes.query import QueryReference
from semant_demo.config import config

import logging

from semant_demo.weaviate_utils.helpers import WeaviateHelpers

class TextChunk():
    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.helpers = WeaviateHelpers(client, collectionNames)
        self.chunk_collection = self.client.collections.get(collectionNames.chunks_collection_name)
        self.span_collection = self.client.collections.get(collectionNames.span_collection_name)

    #######
    # API #
    #######
    async def read(self):
        filters = Filter()
        return await self.helpers.fetch_chunks(filters=filters)

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

    async def tag(self, chunk_id: str, span: schemas.TagSpan):
        if not self.span_collection:
            raise RuntimeError("Span collection not available")

        await self.span_collection.data.insert(
            properties={
                "start": span.start,
                "end": span.end,
                "type": span.type.value if span.type is not None else None,
            },
            references={
                "tag": span.tagId,
                "text_chunk": chunk_id
            }
        )

    async def untag(self, span_id: str):
        if not self.span_collection:
            raise RuntimeError("Span collection is not available")

        try:
            await self.span_collection.data.delete_by_id(uuid=span_id)
            return True
        except Exception as e:
            logging.error(f"Error deleting span with id {span_id}: {e}")
            return False

    async def approve_tag(self, data: schemas.ApproveTagReq) -> bool:
        # TODO change Span.type
        # try:
        #     span_filters = (
        #         Filter.by_ref("text_chunk").by_id().equal(data.chunkID) &
        #         Filter.by_ref("tag").by_id().equal(data.tagID)
        #     )
        #     matching_spans = await self.span_collection.query.fetch_objects(filters=span_filters)

        #     for span in matching_spans.objects:
        #         await self.span_collection.data.update(
        #             uuid=span.uuid,
        #             properties={"type": schemas.SpanType.pos.value}
        #         )
        #     logging.info(f"Updated {len(matching_spans.objects)} spans to 'pos'")
        # except Exception as span_e:
        #     logging.error(f"Error updating spans during approve: {span_e}")
        # TODO/
        """
        Output:
            bool value if operation successfull
        """
        try:
            logging.info(f"Chunk ID: {data.chunkID}, Tag ID: {data.tagID}")
            # get chunk
            return_references=[
                    QueryReference(
                        link_on="automaticTag"
                    ),
                    QueryReference(
                        link_on="positiveTag"
                    ),
                    QueryReference(
                        link_on="negativeTag"
                    )]
            print("HERE 1")
            print(data.chunkID)
            obj = await self.helpers.fetch_object_by_id(data.chunkID, self.helpers.collectionNames.chunks_collection_name, return_references)
            refs = obj.references or {}
            print("Here 2")
            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            pos_ids = ref_uuids(refs.get("positiveTag"))
            tag_id = str(data.tagID)
            print("Here 3")
            # create the reference for approved tag
            # positive tags
            print(obj.uuid)
            updatedTags = sorted(set(pos_ids + [tag_id]))
            for targetId in updatedTags:
                await self.helpers.create_reference(src_id=str(obj.uuid), 
                                        src_collection_name=self.helpers.collectionNames.chunks_collection_name, 
                                        property_name="positiveTag",
                                        target_collection_id=targetId)
            print("Here 4")
            # remove the reference from the negative tags
            await self.helpers.remove_reference(src_id=str(obj.uuid), 
                                        src_collection_name=self.helpers.collectionNames.chunks_collection_name, 
                                        property_name="negativeTag",
                                        target_collection_id=targetId)
            print("Here 5")
            # remove the reference from the automatic tags
            await self.helpers.remove_reference(src_id=str(obj.uuid), 
                                        src_collection_name=self.helpers.collectionNames.chunks_collection_name, 
                                        property_name="automaticTag",
                                        target_collection_id=targetId)
            return True
        except Exception as e:
            logging.error(f"Not changed approval state. Error: {e}")
            return False

    async def disapprove_tag(self, data: schemas.ApproveTagReq) -> bool:
        # TODO change Span.type
         # try:
        #     span_filters = (
        #         Filter.by_ref("text_chunk").by_id().equal(data.chunkID) &
        #         Filter.by_ref("tag").by_id().equal(data.tagID)
        #     )
        #     matching_spans = await self.span_collection.query.fetch_objects(filters=span_filters)

        #     for span in matching_spans.objects:
        #         await self.span_collection.data.update(
        #             uuid=span.uuid,
        #             properties={"type": schemas.SpanType.neg.value}
        #         )
        #     logging.info(f"Updated {len(matching_spans.objects)} spans to 'neg'")
        # except Exception as span_e:
        #     logging.error(f"Error updating spans during disapprove: {span_e}")
        # TODO/
        """
        Output:
            bool value if operation successfull
        """
        try:
            logging.info(f"Chunk ID: {data.chunkID}, Tag ID: {data.tagID}")
            # get chunk
            return_references=[
                    QueryReference(
                        link_on="automaticTag"
                    ),
                    QueryReference(
                        link_on="positiveTag"
                    ),
                    QueryReference(
                        link_on="negativeTag"
                    )]
            obj = await self.helpers.fetch_object_by_id(data.chunkID, self.helpers.collectionNames.chunks_collection_name, return_references)
            refs = obj.references or {}

            # helper to extract UUID strings from reference block
            def ref_uuids(ref_block):
                if not ref_block:
                    return []
                return [str(r.uuid) for r in ref_block.objects]

            neg_ids = ref_uuids(refs.get("negativeTag"))
            tag_id = str(data.tagID)

            # create the reference for disapproved tag
            # negative tags
            updatedTags = sorted(set(neg_ids + [tag_id]))
            for targetId in updatedTags:
                await self.helpers.create_reference(src_id=str(obj.uuid), 
                                        src_collection_name=self.helpers.collectionNames.chunks_collection_name, 
                                        property_name="negativeTag",
                                        target_collection_id=targetId)
            # remove the reference from the positive tags
            await self.helpers.remove_reference(src_id=str(obj.uuid), 
                                        src_collection_name=self.helpers.collectionNames.chunks_collection_name, 
                                        property_name="positiveTag",
                                        target_collection_id=targetId)
            
            # remove the reference from the automatic tags
            await self.helpers.remove_reference(src_id=str(obj.uuid), 
                                        src_collection_name=self.helpers.collectionNames.chunks_collection_name, 
                                        property_name="automaticTag",
                                        target_collection_id=targetId)
            return True
        except Exception as e:
            logging.error(f"Not changed approval state. Error: {e}")
            return False

    def get_tags():
        pass

    async def get_chunks_by_tags(self, getChunksReq: schemas.GetTaggedChunksReq) -> schemas.GetTaggedChunksResponse:
        """
        Get tag objects from them extract collection names, in these collections
        search for chunks that refer to any of the selected tags and return chunk
        texts and all tags from selected tags that are referenced from the chunk
        """
        try:
            # get all chunks with at least one tag from chosenTagUUIDs list
            # get tags
            
            chunk_lst_with_tags = []
            filters = Filter.by_id().contains_any([str(uuid) for uuid in getChunksReq.tag_uuids])
            results = await self.helpers.fetch_tags(filters=filters)
            # get different collection names
            collection_names = {obj.properties["collection_name"] for obj in results}
            userCollectionName = next(iter(collection_names))
            logging.info(f"Tag uuids in get_tagged_chunks: {getChunksReq.tag_uuids} {collection_names} {userCollectionName}")
            # go over chunks, retrieve text chunks and corresponding tags
            # filter to get chunks in selected user collection
            filters =(
                Filter.by_ref(link_on="userCollection").by_property("name").equal(userCollectionName)
            )
            try:
                chunk_results = await self.helpers.fetch_chunks(filters=filters)
                reference_src = getChunksReq.tag_type.value + "Tag"  # ["automaticTag", "positiveTag", "negativeTag"]
                logging.info(f"Source selected: {reference_src}")
                for chunk_obj in chunk_results:
                        referencedTags = chunk_obj.references.get(reference_src) if chunk_obj.references else None
                        chunk_id = str(chunk_obj.uuid)
                        chunk_text = chunk_obj.properties.get('text', '')
                        corresponding_tags = []
                        if referencedTags is not None:
                            logging.info(f"Referenced tags: {referencedTags}")
                        # extract tag
                        if referencedTags and getattr(referencedTags, "objects", None):
                            for tag_obj in referencedTags.objects:
                                if tag_obj.uuid in getChunksReq.tag_uuids:
                                    corresponding_tags.append(str(tag_obj.uuid))
                        # check if there is at least one selected tag

                        if corresponding_tags:
                            # extract approval counts
                            for tagID in corresponding_tags:
                                chunk_lst_with_tags.append(
                                    {'tag_uuid': tagID, 'text_chunk': chunk_text, "chunk_id": chunk_id,
                                    "chunk_collection_name": userCollectionName, "tag_type": getChunksReq.tag_type.value})
            except Exception as e:
                logging.error(f"Tags in Chunks error: {e}")
                
            return {"chunks_with_tags": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"No tags assigned yet. {e}")
            return {'chunks_with_tags': []}

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


    