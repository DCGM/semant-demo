import logging

from fastapi import APIRouter, Depends

from semant_demo import schemas
from semant_demo.config import config


import os
import openai
from semant_demo import schemas
import logging
#from semant_demo.weaviate_tag import WeaviateAbstraction

from sqlalchemy.ext.asyncio import AsyncSession


import logging

from semant_demo.schemas import TasksBase

#import dependencies
from semant_demo.routes.dependencies import get_async_session, get_search

logging.basicConfig(level=logging.INFO)

from semant_demo.tagging.tagging_utils import fetch_chunks_by_collection

from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

exp_router = APIRouter()

@exp_router.post("/api/user_collection", response_model=schemas.CreateResponse)
async def create_user_collection(collectionReq: schemas.UserCollectionReqTemplate,
                                 searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.CreateResponse:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    try:
        collection_id = await searcher.userCollection.create(collectionReq)
        if collection_id is None:
            raise Exception("weaviate error")
        return {"created": True,
                "message": f"Collection {collectionReq.collection_name} created with collection id {collection_id}"}
    except Exception as e:
        logging.error(e)
        return {"created": False,
                "message": f"Collection {collectionReq.collection_name} not created becacause of: {e}"}

@exp_router.get("/api/collections", response_model=schemas.GetCollectionsResponse)
async def fetch_collections(userId: str,
                            searcher: WeaviateAbstraction = Depends(get_search)) -> schemas.GetCollectionsResponse:
    """
    Retrieves all collections for given user
    """
    response = await searcher.userCollection.read(userId)
    return response


@exp_router.post("/api/chunk_2_collection", response_model=schemas.CreateResponse)
async def add_chunk_2_collection(req: schemas.Chunk2CollectionReq, 
                                 searcher: WeaviateAbstraction = Depends(get_search),
                                 ) -> schemas.CreateResponse:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    try:
        
        err = await searcher.userCollection.add_chunks(src_id=req.chunkId, 
                                   target_collection_id=req.collectionId)
        if err == False:
            raise Exception(f"weaviate error, reference not created")
        return {"created": True, "message": f"Chunk added to collection"}
    except Exception as e:
        logging.error(e)
        return {"created": False, "message": f"Chunk not added to collection becacause of: {e}"}
    
@exp_router.get("/api/chunks_of_collection", response_model=schemas.GetCollectionChunksResponse)
async def get_collection_chunks(collectionId: str, 
                                searcher: WeaviateAbstraction = Depends(get_search)
                                ) -> schemas.GetCollectionChunksResponse:
    """
    Returns chunks which belong to collection given by id
    """
    try:
        logging.info(f"In get collection chunks {collectionId}")
        response = await searcher.userCollection.read_all_chunks(collectionId)
        return response
    except Exception as e:
        logging.error(f"{e}")
