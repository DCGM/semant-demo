import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response

from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

#import dependencies
from semant_demo.features.collections import access
from semant_demo.routes.dependencies import get_search
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.schema.tags import PatchTag, Tag, PostTag
from semant_demo.weaviate_exceptions import WeaviateOperationError

logging.basicConfig(level=logging.INFO)

exp_router = APIRouter()

# Tags belong to one collection. Reading needs collection read access; creating,
# editing and deleting tag definitions is allowed to the owner and shared users.

@exp_router.post("/api/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(collection_id: str, tag: PostTag,
                     searcher: WeaviateAbstraction = Depends(get_search),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Creates a tag in weaviate db, or not if the same tag already exists
    """
    grant = await access.require_tag_definition_edit(searcher, current_user, collection_id)
    try:
        return await searcher.tag.create(collection_id=grant.collection_id, tag=tag)
    except WeaviateOperationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@exp_router.get("/api/tags/{tag_uuid}", response_model=Tag)
async def get_tag(tag_uuid: str, searcher: WeaviateAbstraction = Depends(get_search),
                  current_user: User = Depends(current_active_user)) -> Tag:
    """
    Retrieve tag by its id
    """
    await access.require_collection_read(searcher, current_user, await access.collection_of_tags(searcher, [tag_uuid]))
    response = await searcher.tag.read(access.parse_id(tag_uuid, "Tag"))
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tag with id {tag_uuid} not found")
    return response

@exp_router.delete("/api/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_uuid: str,
                      searcher: WeaviateAbstraction = Depends(get_search),
                      current_user: User = Depends(current_active_user)) -> None:
    """
    Deletes tag
    """
    collection_id = await access.collection_of_tags(searcher, [tag_uuid])
    await access.require_tag_definition_edit(searcher, current_user, collection_id)
    await searcher.tag.delete(str(access.parse_id(tag_uuid, "Tag")))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.patch("/api/tags/{tag_uuid}", response_model=Tag)
async def update_tag(tag_uuid: str, tag_update: PatchTag,
                      searcher: WeaviateAbstraction = Depends(get_search),
                      current_user: User = Depends(current_active_user)) -> Tag:
    """
    Updates a tag
    """
    collection_id = await access.collection_of_tags(searcher, [tag_uuid])
    await access.require_tag_definition_edit(searcher, current_user, collection_id)
    try:
        response = await searcher.tag.update(access.parse_id(tag_uuid, "Tag"), tag_update)
        return response
    except WeaviateOperationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
