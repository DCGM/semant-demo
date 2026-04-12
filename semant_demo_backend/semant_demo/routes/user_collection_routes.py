from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response, Query

from semant_demo import schemas
from semant_demo.config import config
from uuid import UUID

import os
import openai
from semant_demo import schemas
import logging
# from semant_demo.weaviate_tag import WeaviateAbstraction

from sqlalchemy.ext.asyncio import AsyncSession


import logging

from semant_demo.schemas import TasksBase
from semant_demo.schema.collections import Collection, CollectionStats, PostCollection, PatchCollection
from semant_demo.schema.documents import Document, DocumentBrowse
from semant_demo.schema.tags import Tag

# import dependencies
from semant_demo.routes.dependencies import get_async_session, get_search

logging.basicConfig(level=logging.INFO)


exp_router = APIRouter()


@exp_router.post("/api/user_collections", response_model=Collection, status_code=status.HTTP_201_CREATED)
async def create_user_collection(collectionReq: PostCollection,
                                 searcher: WeaviateAbstraction = Depends(get_search)) -> Collection:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    collection = await searcher.userCollection.create(collectionReq)
    return collection


@exp_router.get("/api/user_collections", response_model=list[Collection])
async def fetch_collections(userId: UUID,
                            searcher: WeaviateAbstraction = Depends(get_search)) -> list[Collection]:
    """
    Retrieves all collections for given user
    """
    response = await searcher.userCollection.read_all(userId)
    return response


@exp_router.get("/api/user_collections/{collection_id}", response_model=Collection)
async def fetch_collection(collection_id: UUID,
                           searcher: WeaviateAbstraction = Depends(get_search)) -> Collection:
    """
    Retrieves collection by its id
    """
    response = await searcher.userCollection.read(collection_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Collection with id {collection_id} not found")
    return response


@exp_router.patch("/api/user_collections/{collection_id}", response_model=Collection)
async def update_collection(collection_id: UUID, collectionReq: PatchCollection,
                            searcher: WeaviateAbstraction = Depends(get_search)) -> Collection:
    """
    Updates collection name/description/color
    """
    try:
        response = await searcher.userCollection.update(collection_id, collectionReq)
        return response
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@exp_router.post("/api/user_collection/chunks", response_model=schemas.CreateResponse)
async def add_chunk_2_collection(req: schemas.Chunk2CollectionReq,
                                 searcher: WeaviateAbstraction = Depends(
                                     get_search),
                                 ) -> schemas.CreateResponse:
    """
    Connects chunk with user collection
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


@exp_router.get("/api/user_collection/chunks", response_model=schemas.GetCollectionChunksResponse)
async def get_collection_chunks(collection_id: str,
                                searcher: WeaviateAbstraction = Depends(
                                    get_search)
                                ) -> schemas.GetCollectionChunksResponse:
    """
    Returns chunks which belong to collection given by id
    """
    try:
        logging.info(f"In get collection chunks {collection_id}")
        response = await searcher.userCollection.read_all_chunks(collection_id)
        return response
    except Exception as e:
        logging.error(f"{e}")


@exp_router.get("/api/user_collection/{collection_id}/stats", response_model=CollectionStats)
async def get_collection_stats(collection_id: UUID, searcher: WeaviateAbstraction = Depends(get_search)) -> CollectionStats:
    response = await searcher.userCollection.read_collection_stats(collection_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return response


@exp_router.delete("/api/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: UUID, searcher: WeaviateAbstraction = Depends(get_search)) -> Response:
    await searcher.userCollection.delete(collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@exp_router.get("/api/user_collection/{collection_id}/documents", response_model=list[Document], response_model_exclude_none=True)
async def get_collection_documents(collection_id: UUID, searcher: WeaviateAbstraction = Depends(get_search)) -> list[Document]:
    """
    Returns documents which belong to collection given by id
    """
    response = await searcher.userCollection.read_all_documents(collection_id)
    return response

@exp_router.post("/api/collections/{collection_id}/documents/{document_id}")
async def add_document_to_collection(collection_id: UUID, document_id: UUID, searcher: WeaviateAbstraction = Depends(get_search)) -> Response:
    """
    Adds document to collection and also links all its chunks to that collection
    """
    await searcher.userCollection.add_document(document_id=document_id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.delete("/api/collections/{collection_id}/documents/{document_id}")
async def remove_document_from_collection(
    collection_id: UUID,
    document_id: UUID,
    searcher: WeaviateAbstraction = Depends(get_search)
) -> Response:
    await searcher.userCollection.remove_document(document_id=document_id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.get("/api/collections/{collection_id}/tags", response_model=list[Tag])
async def get_collection_tags(collection_id: UUID, searcher: WeaviateAbstraction = Depends(get_search)) -> list[Tag]:
    """
    Returns tags which belong to collection given by id
    """
    response = await searcher.userCollection.read_all_tags(collection_id)
    return response