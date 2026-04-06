from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from semant_demo.routes.dependencies import get_weaviate_client
from semant_demo.schemas import Tag, TagCreateRequest
from semant_demo.weaviate_client import WeaviateClient

router = APIRouter()

@router.get("/api/v1/collections/{collection_id}/tags", response_model=list[Tag])
async def get_collection_tags(
    collection_id: UUID,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> list[Tag]:
    return await wv_client.get_all_tags(collection_id=collection_id)


@router.post("/api/v1/collections/{collection_id}/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_collection_tag(
    collection_id: UUID,
    payload: TagCreateRequest,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> Tag:
    try:
        return await wv_client.create_tag(collection_id=collection_id, tag=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
