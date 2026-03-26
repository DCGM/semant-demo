# Richard Juřica's version of API for handling user collections

from fastapi import APIRouter, Depends, Response, status
from uuid import UUID
from semant_demo.schemas import CollectionResponse, PostCollectionRequest, PatchCollectionRequest
from semant_demo.routes.dependencies import get_weaviate_client
from semant_demo.weaviate_client import WeaviateClient

router = APIRouter()

@router.get("/api/v1/collections")
async def get_collections(user_id: str, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> list[CollectionResponse]:
    response = await wv_client.get_all_collections(user_id)
    return response

@router.post("/api/v1/collections")
async def create_collection(collectionReq: PostCollectionRequest, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> CollectionResponse:
    collection_id = await wv_client.create_collection(collectionReq)
    response = await wv_client.get_collection_by_id(collection_id)
    return response

@router.patch("/api/v1/collections/{collection_id}")
async def update_collection(collection_id: str, collectionReq: PatchCollectionRequest, wv_client: WeaviateClient = Depends(get_weaviate_client)) -> CollectionResponse:
    await wv_client.update_collection(collection_id, collectionReq)
    response = await wv_client.get_collection_by_id(collection_id)
    return response