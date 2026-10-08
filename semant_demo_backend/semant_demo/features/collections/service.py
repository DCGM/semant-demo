"""Collection use cases: metadata, sharing, membership and collection-scoped reads.

Every function checks access itself (``access.py``, ADR 0007) before any other read or
write, so callers outside HTTP get the same rules. ``user`` is the authenticated user or
``None``. Storage goes through the injected repositories; users are looked up in SQL
through ``UserLookup``. Unknown collections, documents, chunks and users raise
``NotFoundError``; ids may be strings or UUIDs, malformed ids are "not found".

Other features may call these functions instead of using the collection repository.
"""
from uuid import UUID

from semant_demo.adapters.sql.users import UserLookup
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.collections import access
from semant_demo.features.collections.access import Principal
from semant_demo.features.collections.schemas import (
    Collection, CollectionStats, PatchCollection, PostCollection,
)
from semant_demo.schema.chunks import Chunk
from semant_demo.schema.documents import Document, DocumentStats
from semant_demo.schema.outcomes import WriteResult
from semant_demo.features.annotations.schemas import Tag
from semant_demo.users.schemas import UserSearchResult

Id = str | UUID


def _logged_in(user: Principal | None) -> Principal:
    if user is None:
        raise access.AuthenticationRequired("Log in to access collections")
    return user


############
# Metadata #
############

async def create_collection(collections: UserCollectionRepository, user: Principal | None,
                            collection: PostCollection) -> Collection:
    """Creates a collection owned by the user."""
    owner = _logged_in(user)
    return await collections.create(collection, owner_id=owner.id, owner_name=getattr(owner, "name", None))


async def list_collections(collections: UserCollectionRepository, user: Principal | None) -> list[Collection]:
    """Collections the user owns or that are shared with them."""
    return await collections.read_all(_logged_in(user).id)


async def get_collection(collections: UserCollectionRepository, user: Principal | None,
                         collection_id: Id) -> Collection:
    grant = await access.require_collection_read(collections, user, collection_id)
    collection = await collections.read(grant.collection_id)
    if collection is None:
        raise NotFoundError("Collection not found")
    collection.is_shared_with_me = not grant.is_owner
    return collection


async def update_collection(collections: UserCollectionRepository, user: Principal | None,
                            collection_id: Id, patch: PatchCollection) -> Collection:
    """Sets the sent name/description/color. Owner only."""
    grant = await access.require_collection_owner(collections, user, collection_id)
    return await collections.update(grant.collection_id, patch)


async def change_owner(collections: UserCollectionRepository, users: UserLookup, user: Principal | None,
                       collection_id: Id, new_owner_id: UUID) -> Collection:
    """Reassigns the collection to another existing user. Admin only."""
    access.require_admin(user)
    new_owner = await users.get_user(new_owner_id)
    if new_owner is None:
        raise NotFoundError(f"User with id {new_owner_id} not found")
    return await collections.set_owner(access.parse_id(collection_id, "Collection"), new_owner.id, new_owner.name)


async def delete_collection(collections: UserCollectionRepository, user: Principal | None,
                            collection_id: Id) -> None:
    """
    Deletes the collection with its tags and annotations. Owner only. A failed step raises
    ``IncompleteWriteError`` naming it and the completed steps; deleting again continues.
    """
    grant = await access.require_collection_owner(collections, user, collection_id)
    await collections.delete(grant.collection_id)


###########
# Sharing #
###########

async def share_collection(collections: UserCollectionRepository, users: UserLookup, user: Principal | None,
                           collection_id: Id, user_id: UUID) -> Collection:
    """Shares the collection with another existing user. Owner only."""
    grant = await access.require_collection_owner(collections, user, collection_id)
    if user_id == user.id:
        raise InvalidRequestError("Cannot share a collection with its owner")
    if await users.get_user(user_id) is None:
        raise NotFoundError(f"User with id {user_id} not found")
    return await collections.share(grant.collection_id, user_id)


async def unshare_collection(collections: UserCollectionRepository, user: Principal | None,
                             collection_id: Id, user_id: UUID) -> Collection:
    """Revokes a share (no change if the user had none). Owner only."""
    grant = await access.require_collection_owner(collections, user, collection_id)
    return await collections.unshare(grant.collection_id, user_id)


async def list_members(collections: UserCollectionRepository, users: UserLookup, user: Principal | None,
                       collection_id: Id) -> list[UserSearchResult]:
    """The users the collection is shared with (unknown user ids are left out). Owner and shared users."""
    grant = await access.require_collection_read(collections, user, collection_id)
    return await users.get_users(await collections.read_shared_user_ids(grant.collection_id))


#########
# Reads #
#########

async def get_collection_stats(collections: UserCollectionRepository, user: Principal | None,
                               collection_id: Id) -> CollectionStats:
    grant = await access.require_collection_read(collections, user, collection_id)
    stats = await collections.read_collection_stats(grant.collection_id)
    if stats is None:
        raise NotFoundError("Collection not found")
    return stats


async def list_documents(collections: UserCollectionRepository, user: Principal | None,
                         collection_id: Id) -> list[Document]:
    grant = await access.require_collection_read(collections, user, collection_id)
    return await collections.read_all_documents(grant.collection_id)


async def list_tags(collections: UserCollectionRepository, tags: TagRepository, user: Principal | None,
                    collection_id: Id) -> list[Tag]:
    grant = await access.require_collection_read(collections, user, collection_id)
    return await tags.read_by_collection(grant.collection_id)


async def get_document_stats(collections: UserCollectionRepository, user: Principal | None,
                             collection_id: Id, document_id: Id) -> DocumentStats:
    """Statistics of a document that is linked to the collection."""
    grant = await access.require_collection_read(collections, user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    return await collections.read_document_stats(grant.collection_id, document)


async def get_document_chunks(collections: UserCollectionRepository, user: Principal | None,
                              collection_id: Id, document_id: Id) -> list[Chunk]:
    """The document's chunks that belong to the collection, in order."""
    grant = await access.require_collection_read(collections, user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    return await collections.read_all_chunks_by_document(document, grant.collection_id)


async def get_neighbour_chunk(collections: UserCollectionRepository, user: Principal | None,
                              collection_id: Id, document_id: Id, direction: str,
                              boundary_order: int) -> Chunk | None:
    """The chunk before (``prev``) or after (``next``) ``boundary_order``, marked with membership."""
    grant = await access.require_collection_read(collections, user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    return await collections.get_neighbour_chunk(document_id=document, collection_id=grant.collection_id,
                                                 direction=direction, boundary_order=boundary_order)


async def get_chunks_in_range(collections: UserCollectionRepository, user: Principal | None,
                              collection_id: Id, document_id: Id,
                              order_gt: int | None, order_lt: int | None) -> list[Chunk]:
    """All chunks of the document strictly between the given orders, marked with membership."""
    grant = await access.require_collection_read(collections, user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    return await collections.get_chunks_in_range(document_id=document, collection_id=grant.collection_id,
                                                 order_gt=order_gt, order_lt=order_lt)


##############
# Membership #
##############
# Owner only: sharing grants annotation rights, never membership changes (ADR 0007).
# Adding needs no prior membership of the document; best-effort outcomes come from the
# repository (ADR 0002).

async def add_chunk(collections: UserCollectionRepository, user: Principal | None,
                    collection_id: Id, chunk_id: Id) -> WriteResult:
    """Links the chunk and its document to the collection; ``partial`` if the document link failed."""
    grant = await access.require_membership_edit(collections, user, collection_id)
    return await collections.add_chunk(access.parse_id(chunk_id, "Chunk"), grant.collection_id)


async def remove_chunk(collections: UserCollectionRepository, user: Principal | None,
                       collection_id: Id, chunk_id: Id) -> None:
    """Unlinks the chunk; a chunk that is not in the collection is a no-op."""
    grant = await access.require_membership_edit(collections, user, collection_id)
    await collections.remove_chunk(chunk_id=access.parse_id(chunk_id, "Chunk"), collection_id=grant.collection_id)


async def add_document(collections: UserCollectionRepository, user: Principal | None,
                       collection_id: Id, document_id: Id) -> WriteResult:
    """Links the document and all its chunks to the collection."""
    grant = await access.require_membership_edit(collections, user, collection_id)
    return await collections.add_document(document_id=access.parse_id(document_id, "Document"),
                                          collection_id=grant.collection_id)


async def remove_document(collections: UserCollectionRepository, user: Principal | None,
                          collection_id: Id, document_id: Id) -> WriteResult:
    """Unlinks the document's chunks, then the document (kept linked if a chunk unlink failed)."""
    grant = await access.require_membership_edit(collections, user, collection_id)
    return await collections.remove_document(document_id=access.parse_id(document_id, "Document"),
                                             collection_id=grant.collection_id)
