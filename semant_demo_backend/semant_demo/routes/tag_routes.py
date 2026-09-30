import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

import logging

#import dependencies
from semant_demo.routes.dependencies import get_search
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.schema.tags import PatchTag, Tag, PostTag
from semant_demo.weaviate_exceptions import WeaviateOperationError

logging.basicConfig(level=logging.INFO)

exp_router = APIRouter()

@exp_router.post("/api/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(collection_id: str, tag: PostTag, 
                     searcher: WeaviateAbstraction = Depends(get_search),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Creates a tag in weaviate db, or not if the same tag already exists
    """
    try:
        return await searcher.tag.create(collection_id=collection_id, tag=tag)
    except WeaviateOperationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@exp_router.get("/api/tags/{tag_uuid}", response_model=Tag)
async def get_tag(tag_uuid: str, searcher: WeaviateAbstraction = Depends(get_search)) -> Tag:
    """
    Retrieve tag by its id
    """
    response = await searcher.tag.read(tag_uuid)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tag with id {tag_uuid} not found")
    return response

@exp_router.delete("/api/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_uuid: str,
                      searcher: WeaviateAbstraction = Depends(get_search)) -> None:
    """
    Deletes tag
    """
    await searcher.tag.delete(tag_uuid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.patch("/api/tags/{tag_uuid}", response_model=Tag)
async def update_tag(tag_uuid: str, tag_update: PatchTag,
                      searcher: WeaviateAbstraction = Depends(get_search)) -> Tag:
    """
    Updates a tag
    """
    try:
        response = await searcher.tag.update(tag_uuid, tag_update)
        return response
    except WeaviateOperationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
