# Richard Juřica's version of API for handling user collections
import logging
from fastapi import APIRouter, Depends, HTTPException, Response, status
from uuid import UUID
from semant_demo.schemas import (
    GetTagsResponse,
)
from semant_demo.schema.collections import Collection, PostCollection, PatchCollection, CollectionStats
from semant_demo.routes.dependencies import get_weaviate_client
from semant_demo.weaviate_client import WeaviateClient

router = APIRouter()

@router.get("/api/v1/collections")
async def get_collections(user_id: str, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> list[Collection]:
    response = await wv_client.get_all_collections(user_id)
    return response


@router.get("/api/v1/collections/{collection_id}")
async def get_collection_by_id(collection_id: UUID, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> Collection:
    response = await wv_client.get_collection_by_id(collection_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return response


# @router.get("/api/v1/collections/{collection_id}/stats")
# async def get_collection_stats(collection_id: UUID, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> CollectionStats:
#     response = await wv_client.get_collection_stats(collection_id)
#     if response is None:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
#     return response

@router.post("/api/v1/collections", status_code=status.HTTP_201_CREATED)
async def create_collection(collectionReq: PostCollection, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> Collection:
    collection_id = await wv_client.create_collection(collectionReq)
    response = await wv_client.get_collection_by_id(collection_id)
    return response

@router.patch("/api/v1/collections/{collection_id}")
async def update_collection(collection_id: str, collectionReq: PatchCollection, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> Collection:
    await wv_client.update_collection(collection_id, collectionReq)
    response = await wv_client.get_collection_by_id(collection_id)
    return response


@router.delete("/api/v1/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: UUID, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> Response:
    await wv_client.delete_collection(collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/v1/collections/{collection_id}/documents/{document_id}")
async def add_document_to_collection(
    collection_id: UUID,
    document_id: UUID,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> dict:
    success = await wv_client.add_document_to_collection(
        document_id=document_id,
        collection_id=collection_id,
    )
    return {
        "success": success,
        "message": "Document added to collection" if success else "Failed to add document to collection"
    }


@router.delete("/api/v1/collections/{collection_id}/documents/{document_id}")
async def remove_document_from_collection(
    collection_id: UUID,
    document_id: UUID,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> dict:
    success = await wv_client.remove_document_from_collection(
        document_id=document_id,
        collection_id=collection_id,
    )
    return {
        "success": success,
        "message": "Document removed from collection" if success else "Failed to remove document from collection"
    }
