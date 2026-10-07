"""Collection access checks (ADR 0007).

Each check loads the requested resource directly by id and raises before any protected
read, write or provider call. Rights:

| Check | Owner | Shared user | Anyone else |
| --- | --- | --- | --- |
| ``require_collection_read`` | yes | yes | not found |
| ``require_annotation_edit`` (spans, AI suggestions/review) | yes | yes | not found |
| ``require_tag_definition_edit`` (create/edit/delete tags) | yes | yes | not found |
| ``require_membership_edit`` (add/remove documents/chunks) | yes | forbidden | not found |
| ``require_collection_owner`` (metadata, delete, sharing) | yes | forbidden | not found |

Users who cannot read a collection get "not found", so ids of other users' collections
are not confirmed. There is no admin bypass: admins have the explicit admin-only routes
(changing a collection's owner) and otherwise the same rights as anyone else. Tags and
spans resolve to their single owning collection; a tag referencing no collection or
several collections is treated as inaccessible rather than guessed. Collection+document
requests also need the document to be linked to that collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol
from uuid import UUID

from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction


class Principal(Protocol):
    id: UUID


class AuthenticationRequired(Exception):
    """The operation needs a logged-in user."""


class ResourceNotFound(Exception):
    """The resource does not exist or the user may not know that it exists."""


class AccessDenied(Exception):
    """The user can read the collection but lacks the right for this operation."""


@dataclass(frozen=True)
class CollectionGrant:
    collection_id: UUID
    is_owner: bool


def parse_id(value: str | UUID, kind: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        raise ResourceNotFound(f"{kind} not found") from None


async def _grant(store: WeaviateAbstraction, user: Principal | None, collection_id: str | UUID) -> CollectionGrant:
    if user is None:
        raise AuthenticationRequired("Log in to access collections")
    cid = parse_id(collection_id, "Collection")
    record = await store.userCollection.read_access_record(cid)
    if record is None:
        raise ResourceNotFound("Collection not found")
    owner_id, shared_with = record
    if owner_id == user.id:
        return CollectionGrant(cid, is_owner=True)
    if user.id in shared_with:
        return CollectionGrant(cid, is_owner=False)
    raise ResourceNotFound("Collection not found")


async def require_collection_read(store, user, collection_id) -> CollectionGrant:
    return await _grant(store, user, collection_id)


async def require_annotation_edit(store, user, collection_id) -> CollectionGrant:
    return await _grant(store, user, collection_id)


async def require_tag_definition_edit(store, user, collection_id) -> CollectionGrant:
    # Decided 2026-10-07 (#201): shared users may create, edit and delete tag definitions.
    return await _grant(store, user, collection_id)


async def require_membership_edit(store, user, collection_id) -> CollectionGrant:
    grant = await _grant(store, user, collection_id)
    if not grant.is_owner:
        raise AccessDenied("Only the collection owner can add or remove documents and chunks")
    return grant


async def require_collection_owner(store, user, collection_id) -> CollectionGrant:
    grant = await _grant(store, user, collection_id)
    if not grant.is_owner:
        raise AccessDenied("Only the collection owner can do this")
    return grant


async def collection_of_tags(store: WeaviateAbstraction, tag_ids: Iterable[str | UUID]) -> UUID:
    """The one collection all given tags belong to; not found otherwise."""
    ids = list(dict.fromkeys(parse_id(t, "Tag") for t in tag_ids))
    if not ids:
        raise ResourceNotFound("Tag not found")
    owners = await store.tag.read_collection_ids(ids)
    collections = set()
    for tid in ids:
        refs = owners.get(tid)
        if refs is None or len(refs) != 1:
            raise ResourceNotFound("Tag not found")
        collections.add(refs[0])
    if len(collections) != 1:
        raise ResourceNotFound("Tags belong to different collections")
    return collections.pop()


async def require_tags_in_collection(store: WeaviateAbstraction, tag_ids: Iterable[str | UUID],
                                     collection_id: UUID) -> list[UUID]:
    ids = list(dict.fromkeys(parse_id(t, "Tag") for t in tag_ids))
    if ids and await collection_of_tags(store, ids) != collection_id:
        raise ResourceNotFound("Tag not found")
    return ids


async def require_document_in_collection(store: WeaviateAbstraction, document_id: str | UUID,
                                         collection_id: UUID) -> UUID:
    """The document must be linked to the collection; otherwise not found.

    Collection access alone does not make another collection's document part of a
    collection-scoped request.
    """
    doc = parse_id(document_id, "Document")
    if not await store.userCollection.document_in_collection(doc, collection_id):
        raise ResourceNotFound("Document not found in this collection")
    return doc


async def require_chunks_in_collection(store: WeaviateAbstraction, chunk_ids: Iterable[str | UUID],
                                       collection_id: UUID, document_id: str | UUID | None = None) -> list[UUID]:
    ids = list(dict.fromkeys(parse_id(c, "Chunk") for c in chunk_ids))
    doc = parse_id(document_id, "Document") if document_id is not None else None
    found = await store.userCollection.chunk_ids_in_collection(ids, collection_id, doc)
    if len(found) != len(ids):
        raise ResourceNotFound("Chunk not found in this collection")
    return ids


async def collection_of_spans(store: WeaviateAbstraction, span_ids: Iterable[str | UUID]) -> UUID:
    """The one collection all given spans belong to (via their tag); not found otherwise."""
    ids = list(dict.fromkeys(parse_id(s, "Span") for s in span_ids))
    if not ids:
        raise ResourceNotFound("Span not found")
    refs = await store.span.read_refs(ids)
    tag_ids = set()
    for sid in ids:
        span_refs = refs.get(sid)
        if span_refs is None or len(span_refs[0]) != 1:
            raise ResourceNotFound("Span not found")
        tag_ids.add(span_refs[0][0])
    return await collection_of_tags(store, tag_ids)
