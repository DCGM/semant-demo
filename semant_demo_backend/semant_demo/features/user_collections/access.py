"""Collection access checks (ADR 0007).

Each check loads the requested resource directly by id and raises before any protected
read, write or provider call. Rights:

| Check | Owner | Shared user | Anyone else |
| --- | --- | --- | --- |
| ``require_collection_read`` | yes | yes | not found |
| ``require_annotation_edit`` (spans, AI suggestions/review) | yes | yes | not found |
| ``require_tag_definition_edit`` (create/edit/delete tags) | yes | yes | not found |
| ``require_attribute_definition_edit`` (create/edit/delete attributes and values, #331) | yes | yes | not found |
| ``require_membership_edit`` (add/remove documents/chunks) | yes | forbidden | not found |
| ``require_collection_owner`` (metadata, delete, sharing) | yes | forbidden | not found |
| ``require_admin`` (change a collection's owner) | no | no | admins only |

Users who cannot read a collection get "not found", so ids of other users' collections
are not confirmed. There is no admin bypass: admins have the explicit admin-only routes
(changing a collection's owner) and otherwise the same rights as anyone else. Tags
resolve to their single owning collection; a tag referencing no collection or several
collections is treated as inaccessible rather than guessed. Spans live in the annotation
tenant of their collection (#327): span requests name the collection, which is checked
first, and the spans are then looked up only in its tenant, so a span id is never a
credential and an id of another collection is "not found". Collection+document requests
also need the document to be linked to that collection.

Adding a document or chunk to a collection (``require_document_addable``, #279) also needs the
document to be readable by the user already: public, or linked to another collection the
user can read. Otherwise any signed-in user could unlock a restricted document by adding
its id to a collection of their own.

Each function takes the repository it reads (collections, tags, spans), so callers do
not need the transitional ``WeaviateAbstraction`` facade.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol
from uuid import UUID

from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import NotFoundError
from semant_demo.features.annotations.schemas import TagSpan


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


async def require_attribute_definition_edit(collections: UserCollectionRepository, user: Principal | None,
                                            collection_id: str | UUID) -> CollectionGrant:
    # Like tag definitions (#201, ADR 0011): attributes are the collection's shared vocabulary.
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


async def require_document_addable(collections: UserCollectionRepository, user: Principal | None,
                                   document_id: UUID) -> None:
    """The user may add the document to a collection (#279): it is public (``public`` true) or
    linked to a collection the user can read. "Not found" otherwise, as for a document that
    does not exist, so restricted ids are not confirmed."""
    rights = await collections.read_document_rights(document_id)
    if rights is None:
        raise ResourceNotFound("Document not found")
    public, linked = rights
    if public is True:
        return
    for collection_id in sorted(linked):
        try:
            await require_collection_read(collections, user, collection_id)
            return
        except ResourceNotFound:
            continue
    raise ResourceNotFound("Document not found")


async def require_chunk_addable(collections: UserCollectionRepository, user: Principal | None,
                                chunk_id: UUID) -> None:
    """``require_document_addable`` for the chunk's document; "not found" for an unknown chunk.
    A chunk without a document has no source rights to check (and is never eligible in
    search, which requires its document to be readable)."""
    exists, document_id = await collections.read_chunk_document(chunk_id)
    if not exists:
        raise ResourceNotFound("Chunk not found")
    if document_id is not None:
        await require_document_addable(collections, user, document_id)


async def require_chunks_in_collection(collections: UserCollectionRepository, chunk_ids: Iterable[str | UUID],
                                       collection_id: UUID, document_id: str | UUID | None = None) -> list[UUID]:
    ids = list(dict.fromkeys(parse_id(c, "Chunk") for c in chunk_ids))
    doc = parse_id(document_id, "Document") if document_id is not None else None
    found = await collections.chunk_ids_in_collection(ids, collection_id, doc)
    if len(found) != len(ids):
        raise ResourceNotFound("Chunk not found in this collection")
    return ids


async def require_spans_in_collection(spans: SpanRepository, span_ids: Iterable[str | UUID],
                                      collection_id: UUID) -> dict[UUID, TagSpan]:
    """The spans in request order, read from the tenant of ``collection_id`` (already
    authorized by the caller); "not found" unless every id is a span of that collection."""
    ids = list(dict.fromkeys(parse_id(s, "Span") for s in span_ids))
    if not ids:
        raise ResourceNotFound("Span not found")
    found = await spans.read_many(collection_id, ids)
    if any(i not in found for i in ids):
        raise ResourceNotFound("Span not found")
    return {i: found[i] for i in ids}
