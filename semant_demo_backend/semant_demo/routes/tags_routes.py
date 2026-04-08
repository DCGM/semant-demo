from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from semant_demo.routes.dependencies import get_weaviate_client
from semant_demo.schema.tags import Tag, PostTag, PatchTag
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
    payload: PostTag,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> Tag:
    try:
        return await wv_client.create_tag(collection_id=collection_id, tag=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/api/v1/collections/{collection_id}/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection_tag(
    collection_id: UUID,
    tag_uuid: UUID,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> Response:
    try:
        await wv_client.delete_tag(collection_id=collection_id, tag_uuid=tag_uuid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

@router.patch("/api/v1/collections/{collection_id}/tags/{tag_uuid}", response_model=Tag)
async def update_collection_tag(
    collection_id: UUID,
    tag_uuid: UUID,
    payload: PatchTag,
    wv_client: WeaviateClient = Depends(get_weaviate_client),
) -> Tag:
    try:
        await wv_client.update_tag(collection_id=collection_id, tag_uuid=tag_uuid, updated_tag=payload)
        updated = await wv_client.get_tag_by_id(collection_id=collection_id, tag_uuid=tag_uuid)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc