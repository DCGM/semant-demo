import logging

from weaviate.classes.query import Filter

from semant_demo.weaviate_search import WeaviateSearch
from semant_demo import schemas

async def fetch_chunks_by_collection(collectionId: str, searcher: WeaviateSearch) ->schemas.GetCollectionChunksResponse:
        """
        Get all chunks belonging to collection with collectionId
        get collection object, in that collection search for chunks that refer to the
        collection and return chunk texts
        """
        try:
            chunk_lst_with_tags = []
            # prepare filter for collection ID
            filters = Filter.by_ref("userCollection").by_id().equal(collectionId)
            # iterate over all chunks find the reference to the user collection
            chunks = await searcher._fetch_chunks(filters=filters)
            chunk_lst_with_tags.extend([
                    {
                        'text_chunk': chunk_obj.properties.get('text', ''),
                        'chunk_id': str(chunk_obj.uuid),
                        'chunk_collection_name': collectionId
                    }
                    for chunk_obj in chunks
            ])
            return {"chunks_of_collection": chunk_lst_with_tags}
        except Exception as e:
            logging.error(f"Error: {e}")
            return {'chunks_of_collection': []}
