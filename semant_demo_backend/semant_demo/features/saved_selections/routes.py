"""HTTP routes of saved research selections (#824); the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, Response, status

from semant_demo.features.saved_selections import service
from semant_demo.features.saved_selections.schemas import PatchSavedSelection, PostSavedSelection, SavedSelection
from semant_demo.features.saved_selections.service import SavedSelectionStore
from semant_demo.routes.dependencies import get_saved_selection_store
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

exp_router = APIRouter()

# Unknown or inaccessible collections and saved selections (also those of another collection)
# are answered with 404, a name already taken with 400, a change by someone who is neither the
# creator nor the collection owner with 403.

_BASE = "/api/user_collections/{collection_id}/saved-selections"


@exp_router.get(_BASE, response_model=list[SavedSelection])
async def list_saved_selections(collection_id: str, store: SavedSelectionStore = Depends(get_saved_selection_store),
                                current_user: User = Depends(current_active_user)) -> list[SavedSelection]:
    """The collection's saved selections, by name. Owner and shared users."""
    return await service.list_saved_selections(store, current_user, collection_id)


@exp_router.post(_BASE, response_model=SavedSelection, status_code=status.HTTP_201_CREATED)
async def create_saved_selection(collection_id: str, body: PostSavedSelection,
                                 store: SavedSelectionStore = Depends(get_saved_selection_store),
                                 current_user: User = Depends(current_active_user)) -> SavedSelection:
    """Saves a live filter: the annotation query and how it is listed, evaluated again on every open."""
    return await service.create_saved_selection(store, current_user, collection_id, body)


@exp_router.patch(_BASE + "/{selection_id}", response_model=SavedSelection)
async def update_saved_selection(collection_id: str, selection_id: str, patch: PatchSavedSelection,
                                 store: SavedSelectionStore = Depends(get_saved_selection_store),
                                 current_user: User = Depends(current_active_user)) -> SavedSelection:
    """Renames a saved selection and/or replaces its query. Its creator and the collection owner."""
    return await service.update_saved_selection(store, current_user, collection_id, selection_id, patch)


@exp_router.delete(_BASE + "/{selection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_selection(collection_id: str, selection_id: str,
                                 store: SavedSelectionStore = Depends(get_saved_selection_store),
                                 current_user: User = Depends(current_active_user)) -> Response:
    """Deletes a saved selection. Its creator and the collection owner."""
    await service.delete_saved_selection(store, current_user, collection_id, selection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
