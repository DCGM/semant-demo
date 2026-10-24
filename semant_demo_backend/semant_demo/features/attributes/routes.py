"""HTTP routes of collection attributes (#331); the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, Response, status

from semant_demo.features.attributes import service
from semant_demo.features.attributes.schemas import (
    Attribute, AttributeAssignRequest, AttributeAssignResult, AttributeChange, PatchAttribute, PatchAttributeValue,
    PostAttribute, PostAttributeValue,
)
from semant_demo.features.attributes.service import AttributeStore
from semant_demo.routes.dependencies import get_attribute_store
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

exp_router = APIRouter()

# Unknown or inaccessible collections, attributes, values and annotations are answered with
# 404 (also ids of another collection), a name or label already taken with 400, a definition
# that annotations still use cannot be deleted (409 with the number affected), and an
# assignment store without the attribute properties answers 503.


@exp_router.get("/api/user_collections/{collection_id}/attributes", response_model=list[Attribute])
async def list_attributes(collection_id: str, store: AttributeStore = Depends(get_attribute_store),
                          current_user: User = Depends(current_active_user)) -> list[Attribute]:
    """The collection's attributes with their values (also retired ones), by name."""
    return await service.list_attributes(store, current_user, collection_id)


@exp_router.post("/api/user_collections/{collection_id}/attributes", response_model=Attribute,
                 status_code=status.HTTP_201_CREATED)
async def create_attribute(collection_id: str, attribute: PostAttribute,
                           store: AttributeStore = Depends(get_attribute_store),
                           current_user: User = Depends(current_active_user)) -> Attribute:
    """Defines an attribute (with initial values) of the collection. Owner and shared users."""
    return await service.create_attribute(store, current_user, collection_id, attribute)


@exp_router.patch("/api/user_collections/{collection_id}/attributes/{attribute_id}", response_model=Attribute)
async def update_attribute(collection_id: str, attribute_id: str, patch: PatchAttribute,
                           store: AttributeStore = Depends(get_attribute_store),
                           current_user: User = Depends(current_active_user)) -> Attribute:
    """Renames, describes, retires or restricts to tags an attribute. Annotations are not rewritten."""
    return await service.update_attribute(store, current_user, collection_id, attribute_id, patch)


@exp_router.delete("/api/user_collections/{collection_id}/attributes/{attribute_id}",
                   status_code=status.HTTP_204_NO_CONTENT)
async def delete_attribute(collection_id: str, attribute_id: str,
                           store: AttributeStore = Depends(get_attribute_store),
                           current_user: User = Depends(current_active_user)) -> Response:
    """Deletes an attribute no annotation has a value of; otherwise 409 with the number affected."""
    await service.delete_attribute(store, current_user, collection_id, attribute_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@exp_router.post("/api/user_collections/{collection_id}/attributes/{attribute_id}/values",
                 response_model=Attribute, status_code=status.HTTP_201_CREATED)
async def add_attribute_value(collection_id: str, attribute_id: str, value: PostAttributeValue,
                              store: AttributeStore = Depends(get_attribute_store),
                              current_user: User = Depends(current_active_user)) -> Attribute:
    """Adds a value; returns the attribute."""
    return await service.add_value(store, current_user, collection_id, attribute_id, value)


@exp_router.patch("/api/user_collections/{collection_id}/attributes/{attribute_id}/values/{value_id}",
                  response_model=Attribute)
async def update_attribute_value(collection_id: str, attribute_id: str, value_id: str, patch: PatchAttributeValue,
                                 store: AttributeStore = Depends(get_attribute_store),
                                 current_user: User = Depends(current_active_user)) -> Attribute:
    """Renames, describes or retires a value; its assignments stay."""
    return await service.update_value(store, current_user, collection_id, attribute_id, value_id, patch)


@exp_router.delete("/api/user_collections/{collection_id}/attributes/{attribute_id}/values/{value_id}",
                   response_model=Attribute)
async def delete_attribute_value(collection_id: str, attribute_id: str, value_id: str,
                                 store: AttributeStore = Depends(get_attribute_store),
                                 current_user: User = Depends(current_active_user)) -> Attribute:
    """Deletes a value no annotation has; otherwise 409 with the number affected. Returns the attribute."""
    return await service.delete_value(store, current_user, collection_id, attribute_id, value_id)


@exp_router.post("/api/user_collections/{collection_id}/annotations/attributes/assign",
                 response_model=AttributeAssignResult)
async def assign_attribute_values(collection_id: str, body: AttributeAssignRequest,
                                  store: AttributeStore = Depends(get_attribute_store),
                                  current_user: User = Depends(current_active_user)) -> AttributeAssignResult:
    """
    Adds, removes or replaces the values of one attribute on up to 200 approved annotations,
    each expected at its ``attributeVersion``. Best effort and per item: ``succeeded`` lists the
    changed annotations (or those already as asked), ``failed`` the ones not changed or
    uncertain, with ``edit_conflict`` for an annotation whose attributes were written since;
    ``versions`` and ``values`` give the current state. Nothing is rolled back.
    """
    return await service.assign_attributes(store, current_user, collection_id, body)


@exp_router.get("/api/user_collections/{collection_id}/annotations/{annotation_id}/attribute-changes",
                response_model=list[AttributeChange])
async def list_attribute_changes(collection_id: str, annotation_id: str,
                                 store: AttributeStore = Depends(get_attribute_store),
                                 current_user: User = Depends(current_active_user)) -> list[AttributeChange]:
    """Who changed the annotation's attribute values when (oldest first), manual or AI-assisted."""
    return await service.read_attribute_changes(store, current_user, collection_id, annotation_id)
