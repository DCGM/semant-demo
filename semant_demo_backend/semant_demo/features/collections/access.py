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
| ``require_admin`` (change a collection's owner) | no | no | admins only |
| ``require_readable_tags`` (search tag filters) | yes | yes | not found |

Users who cannot read a collection get "not found", so ids of other users' collections
are not confirmed. There is no admin bypass: admins have the explicit admin-only routes
(changing a collection's owner) and otherwise the same rights as anyone else. Tags and
spans resolve to their single owning collection; a tag referencing no collection or
several collections is treated as inaccessible rather than guessed. Collection+document
requests also need the document to be linked to that collection.

Each function takes the repository it reads (collections, tags, spans), so callers do
not need the transitional ``WeaviateAbstraction`` facade.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol
from uuid import UUID

from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import NotFoundError
from semant_demo.weaviate_utils.span import Span


class Principal(Protocol):
    id: UUID


class AuthenticationRequired(Exception):
    """The operation needs a logged-in user."""


class ResourceNotFound(NotFoundError):
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


async def _grant(collections: UserCollectionRepository, user: Principal | None, collection_id: str | UUID) -> CollectionGrant:
    if user is None:
        raise AuthenticationRequired("Log in to access collections")
    cid = parse_id(collection_id, "Collection")
    record = await collections.read_access_record(cid)
    if record is None:
        raise ResourceNotFound("Collection not found")
    owner_id, shared_with = record
    if owner_id == user.id:
        return CollectionGrant(cid, is_owner=True)
    if user.id in shared_with:
        return CollectionGrant(cid, is_owner=False)
    raise ResourceNotFound("Collection not found")


async def require_collection_read(collections: UserCollectionRepository, user: Principal | None,
                                  collection_id: str | UUID) -> CollectionGrant:
    return await _grant(collections, user, collection_id)


async def require_annotation_edit(collections: UserCollectionRepository, user: Principal | None,
                                  collection_id: str | UUID) -> CollectionGrant:
    return await _grant(collections, user, collection_id)


async def require_tag_definition_edit(collections: UserCollectionRepository, user: Principal | None,
                                      collection_id: str | UUID) -> CollectionGrant:
    # Decided 2026-10-07 (#201): shared users may create, edit and delete tag definitions.
    return await _grant(collections, user, collection_id)


async def require_membership_edit(collections: UserCollectionRepository, user: Principal | None,
                                  collection_id: str | UUID) -> CollectionGrant:
    grant = await _grant(collections, user, collection_id)
    if not grant.is_owner:
        raise AccessDenied("Only the collection owner can add or remove documents and chunks")
    return grant


async def require_collection_owner(collections: UserCollectionRepository, user: Principal | None,
                                   collection_id: str | UUID) -> CollectionGrant:
    grant = await _grant(collections, user, collection_id)
    if not grant.is_owner:
        raise AccessDenied("Only the collection owner can do this")
    return grant


def require_admin(user: Principal | None) -> None:
    """Explicit admin-only actions (changing a collection's owner); not a bypass of the checks above."""
    if user is None:
        raise AuthenticationRequired("Log in to access collections")
    if not getattr(user, "is_superuser", False):
        raise AccessDenied("Only administrators can do this")


async def collection_of_tags(tags: TagRepository, tag_ids: Iterable[str | UUID]) -> UUID:
    """The one collection all given tags belong to; not found otherwise."""
    ids = list(dict.fromkeys(parse_id(t, "Tag") for t in tag_ids))
    if not ids:
        raise ResourceNotFound("Tag not found")
    owners = await tags.read_collection_ids(ids)
    collections = set()
    for tid in ids:
        refs = owners.get(tid)
        if refs is None or len(refs) != 1:
            raise ResourceNotFound("Tag not found")
        collections.add(refs[0])
    if len(collections) != 1:
        raise ResourceNotFound("Tags belong to different collections")
    return collections.pop()


async def require_tags_in_collection(tags: TagRepository, tag_ids: Iterable[str | UUID],
                                     collection_id: UUID) -> list[UUID]:
    ids = list(dict.fromkeys(parse_id(t, "Tag") for t in tag_ids))
    if ids and await collection_of_tags(tags, ids) != collection_id:
        raise ResourceNotFound("Tag not found")
    return ids


async def require_readable_tags(collections: UserCollectionRepository, tags: TagRepository, user: Principal | None,
                                tag_ids: Iterable[str | UUID], collection_id: UUID | None = None) -> list[UUID]:
    """Every tag must belong to one collection the user can read (to ``collection_id``, if given).

    Unknown, malformed, other users' and (with ``collection_id``) other collections' tags
    all raise the same "Tag not found", so the answer does not reveal whether a private
    tag exists. Anonymous users cannot use tags. No tags: nothing to check.
    """
    ids = list(dict.fromkeys(parse_id(t, "Tag") for t in tag_ids))
    if not ids:
        return []
    if user is None:
        raise AuthenticationRequired("Log in to filter by tags")
    owners = await tags.read_collection_ids(ids)
    tag_collections = set()
    for tid in ids:
        refs = owners.get(tid)
        if refs is None or len(refs) != 1 or (collection_id is not None and refs[0] != collection_id):
            raise ResourceNotFound("Tag not found")
        tag_collections.add(refs[0])
    for cid in tag_collections:
        try:
            await _grant(collections, user, cid)
        except ResourceNotFound:
            raise ResourceNotFound("Tag not found") from None
    return ids


async def require_document_in_collection(collections: UserCollectionRepository, document_id: str | UUID,
                                         collection_id: UUID) -> UUID:
    """The document must be linked to the collection; otherwise not found.

    Collection access alone does not make another collection's document part of a
    collection-scoped request.
    """
    doc = parse_id(document_id, "Document")
    if not await collections.document_in_collection(doc, collection_id):
        raise ResourceNotFound("Document not found in this collection")
    return doc


async def require_chunks_in_collection(collections: UserCollectionRepository, chunk_ids: Iterable[str | UUID],
                                       collection_id: UUID, document_id: str | UUID | None = None) -> list[UUID]:
    ids = list(dict.fromkeys(parse_id(c, "Chunk") for c in chunk_ids))
    doc = parse_id(document_id, "Document") if document_id is not None else None
    found = await collections.chunk_ids_in_collection(ids, collection_id, doc)
    if len(found) != len(ids):
        raise ResourceNotFound("Chunk not found in this collection")
    return ids


async def collection_of_spans(spans: Span, tags: TagRepository, span_ids: Iterable[str | UUID]) -> UUID:
    """The one collection all given spans belong to (via their tag); not found otherwise."""
    ids = list(dict.fromkeys(parse_id(s, "Span") for s in span_ids))
    if not ids:
        raise ResourceNotFound("Span not found")
    refs = await spans.read_refs(ids)
    tag_ids = set()
    for sid in ids:
        span_refs = refs.get(sid)
        if span_refs is None or len(span_refs[0]) != 1:
            raise ResourceNotFound("Span not found")
        tag_ids.add(span_refs[0][0])
    return await collection_of_tags(tags, tag_ids)
