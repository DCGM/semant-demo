"""Saved research selections (#824, parent #335): named live filters of a collection's
annotation workspace, kept on the server.

Access reuses the collection's rights (ADR 0007); no other access list exists and a link to a
saved selection grants nothing. Every reader of the collection (owner and shared users) lists,
opens and creates saved selections; renaming, replacing the query and deleting are for the
selection's creator and the collection owner. Losing access to the collection loses access to
its saved selections at once, since every request checks the collection first; a creator who
lost access keeps no rights over the selections they created, which stay with the collection.

A live filter stores the annotation query (``AnnotationFilters``, #663) and how the workspace
lists it; it is evaluated again whenever it is opened, so its result follows later annotation
changes. Its tags, attributes and documents are not checked against the collection here: a
query naming deleted ones matches as the annotation query does (no annotation of a deleted tag),
and the workspace warns about such references.
"""
from dataclasses import dataclass
from uuid import UUID

from semant_demo.adapters.sql.saved_selections import SavedSelectionRepository, StoredSelection
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.saved_selections.schemas import (
    MAX_SAVED_SELECTIONS, PatchSavedSelection, PostSavedSelection, SavedSelection, SavedSelectionKind,
)
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import AccessDenied, CollectionGrant, Principal

Id = str | UUID

NOT_EDITABLE = "Only the creator of a saved selection and the collection owner can change or delete it"


@dataclass
class SavedSelectionStore:
    collections: UserCollectionRepository
    selections: SavedSelectionRepository


def _may_edit(grant: CollectionGrant, user: Principal, selection: StoredSelection) -> bool:
    return grant.is_owner or selection.created_by == user.id


def _public(grant: CollectionGrant, user: Principal, selection: StoredSelection) -> SavedSelection:
    return SavedSelection(id=selection.id, collection_id=selection.collection_id, kind=selection.kind,
                          name=selection.name, query=selection.query, unreadable=selection.query is None,
                          created_by=selection.created_by, created_at=selection.created_at,
                          updated_by=selection.updated_by, updated_at=selection.updated_at,
                          can_edit=_may_edit(grant, user, selection))


async def _editable(store: SavedSelectionStore, user: Principal | None, collection_id: Id,
                    selection_id: Id) -> tuple[CollectionGrant, StoredSelection]:
    grant = await access.require_collection_read(store.collections, user, collection_id)
    selection = await store.selections.read(grant.collection_id, access.parse_id(selection_id, "Saved selection"))
    if selection is None:
        raise NotFoundError("Saved selection not found")
    if not _may_edit(grant, user, selection):
        raise AccessDenied(NOT_EDITABLE)
    return grant, selection


async def list_saved_selections(store: SavedSelectionStore, user: Principal | None,
                                collection_id: Id) -> list[SavedSelection]:
    """The collection's saved selections, by name."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    return [_public(grant, user, s) for s in await store.selections.read_all(grant.collection_id)]


async def create_saved_selection(store: SavedSelectionStore, user: Principal | None, collection_id: Id,
                                 body: PostSavedSelection) -> SavedSelection:
    """Saves a live filter under a name unique in the collection (400 when taken or when the
    collection already has ``MAX_SAVED_SELECTIONS``). The limit is soft: it is counted before the
    insert, so concurrent creates can pass it by a few."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    if await store.selections.count(grant.collection_id) >= MAX_SAVED_SELECTIONS:
        raise InvalidRequestError(f"A collection has at most {MAX_SAVED_SELECTIONS} saved selections; delete one first")
    created = await store.selections.create(grant.collection_id, SavedSelectionKind.live, body.name, body.query,
                                            user.id)
    return _public(grant, user, created)


async def update_saved_selection(store: SavedSelectionStore, user: Principal | None, collection_id: Id,
                                 selection_id: Id, patch: PatchSavedSelection) -> SavedSelection:
    """Renames it and/or replaces its query. Its creator and the collection owner only (403)."""
    grant, selection = await _editable(store, user, collection_id, selection_id)
    updated = await store.selections.update(grant.collection_id, selection.id, user.id, name=patch.name,
                                            query=patch.query)
    if updated is None:
        raise NotFoundError("Saved selection not found")
    return _public(grant, user, updated)


async def delete_saved_selection(store: SavedSelectionStore, user: Principal | None, collection_id: Id,
                                 selection_id: Id) -> None:
    """Deletes it; no annotation changes. Its creator and the collection owner only (403)."""
    grant, selection = await _editable(store, user, collection_id, selection_id)
    if not await store.selections.delete(grant.collection_id, selection.id):
        raise NotFoundError("Saved selection not found")
