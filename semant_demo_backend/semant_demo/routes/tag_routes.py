import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

import logging

# import dependencies
from semant_demo.routes.dependencies import get_search, get_tag_repository
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.schema.tags import PatchTag, Tag, PostTag
from semant_demo.weaviate_exceptions import NotFoundError
from semant_demo.weaviate_utils.tag_repository import TagRepository

logging.basicConfig(level=logging.INFO)

exp_router = APIRouter()


@exp_router.post("/api/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(collection_id: str, tag: PostTag,
                     tag_repository: TagRepository = Depends(
                         get_tag_repository),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Creates a tag in weaviate db, or not if the same tag already exists
    """
    try:
        return await tag_repository.create(collection_id=collection_id, tag=tag)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@exp_router.get("/api/tags", response_model=schemas.GetTagsResponse)
async def get_tags(tag_repository: TagRepository = Depends(get_tag_repository)) -> schemas.GetTagsResponse:
    """
    Retrieve all tags
    """
    response = await tag_repository.read_all()
    return {"tags_lst": response}


@exp_router.get("/api/tags/{tag_uuid}", response_model=Tag)
async def get_tag(tag_uuid: str, tag_repository: TagRepository = Depends(get_tag_repository)) -> Tag:
    """
    Retrieve tag by its id
    """
    response = await tag_repository.read(tag_uuid)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tag with id {tag_uuid} not found")
    return response


@exp_router.delete("/api/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_uuid: str,
                     tag_repository: TagRepository = Depends(get_tag_repository)) -> None:
    """
    Deletes tag
    """
    try:
        await tag_repository.delete(tag_uuid)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@exp_router.patch("/api/tags/{tag_uuid}", response_model=Tag)
async def update_tag(tag_uuid: str, tag_update: PatchTag,
                     tag_repository: TagRepository = Depends(get_tag_repository)) -> Tag:
    """
    Updates a tag
    """
    try:
        response = await tag_repository.update(tag_uuid, tag_update)
        return response
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
