import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response

from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.features.collections import access
from semant_demo.routes.dependencies import get_collections, get_tags
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.schema.tags import PatchTag, Tag, PostTag

logging.basicConfig(level=logging.INFO)

exp_router = APIRouter()

# Tags belong to one collection. Reading needs collection read access; creating,
# editing and deleting tag definitions is allowed to the owner and shared users.
# A missing tag or collection is answered with 404 (NotFoundError, see create_app).

@exp_router.post("/api/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(collection_id: str, tag: PostTag,
                     tags: TagRepository = Depends(get_tags),
                     collections: UserCollectionRepository = Depends(get_collections),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Creates a tag in weaviate db, or not if the same tag already exists
    """
    grant = await access.require_tag_definition_edit(collections, current_user, collection_id)
    return await tags.create(collection_id=grant.collection_id, tag=tag)

@exp_router.get("/api/tags/{tag_uuid}", response_model=Tag)
async def get_tag(tag_uuid: str,
                  tags: TagRepository = Depends(get_tags),
                  collections: UserCollectionRepository = Depends(get_collections),
                  current_user: User = Depends(current_active_user)) -> Tag:
    """
    Retrieve tag by its id
    """
    await access.require_collection_read(collections, current_user, await access.collection_of_tags(tags, [tag_uuid]))
    response = await tags.read(access.parse_id(tag_uuid, "Tag"))
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tag with id {tag_uuid} not found")
    return response

@exp_router.delete("/api/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_uuid: str,
                     tags: TagRepository = Depends(get_tags),
                     collections: UserCollectionRepository = Depends(get_collections),
                     current_user: User = Depends(current_active_user)) -> None:
    """
    Deletes tag
    """
    collection_id = await access.collection_of_tags(tags, [tag_uuid])
    await access.require_tag_definition_edit(collections, current_user, collection_id)
    await tags.delete(access.parse_id(tag_uuid, "Tag"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.patch("/api/tags/{tag_uuid}", response_model=Tag)
async def update_tag(tag_uuid: str, tag_update: PatchTag,
                     tags: TagRepository = Depends(get_tags),
                     collections: UserCollectionRepository = Depends(get_collections),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Updates a tag. Fields that are omitted or null are kept; at least one field must
    have a value (422 otherwise).
    """
    collection_id = await access.collection_of_tags(tags, [tag_uuid])
    await access.require_tag_definition_edit(collections, current_user, collection_id)
    return await tags.update(access.parse_id(tag_uuid, "Tag"), tag_update)
