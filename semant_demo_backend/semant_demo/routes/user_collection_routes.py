import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status, Response, Query
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo import schemas
from semant_demo.adapters.sql import users
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.core.errors import InvalidRequestError, NotFoundError
from semant_demo.features.collections import access
from semant_demo.routes.dependencies import get_async_session, get_collections, get_documents, get_tags
from semant_demo.schema.chunks import Chunk
from semant_demo.schema.collections import Collection, CollectionStats, PostCollection, PatchCollection, PatchCollectionOwner, ShareCollectionRequest
from semant_demo.schema.documents import Document, DocumentStats
from semant_demo.schema.outcomes import WriteResult
from semant_demo.schema.tags import Tag
from semant_demo.users.auth import current_active_user, current_active_admin
from semant_demo.users.models import User
from semant_demo.users.schemas import UserSearchResult

logging.basicConfig(level=logging.INFO)


exp_router = APIRouter()

# Every collection-scoped route checks access first (features/collections/access.py):
# reads need owner/shared access, membership/metadata/sharing changes need the owner.
# Unknown collections, documents, chunks and users are answered with 404 (NotFoundError,
# see create_app).


@exp_router.post("/api/user_collections", response_model=Collection, status_code=status.HTTP_201_CREATED)
async def create_user_collection(collectionReq: PostCollection,
                                 collections: UserCollectionRepository = Depends(get_collections),
                                 current_user: User = Depends(current_active_user)) -> Collection:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    collection = await collections.create(collectionReq, owner_id=current_user.id, owner_name=current_user.name)
    return collection


@exp_router.get("/api/user_collections", response_model=list[Collection])
async def fetch_collections(collections: UserCollectionRepository = Depends(get_collections),
                            current_user: User = Depends(current_active_user)) -> list[Collection]:
    """
    Retrieves all collections for given user
    """

    response = await collections.read_all(current_user.id)
    return response


@exp_router.get("/api/user_collections/{collection_id}", response_model=Collection)
async def fetch_collection(collection_id: str,
                           collections: UserCollectionRepository = Depends(get_collections),
                           current_user: User = Depends(current_active_user)) -> Collection:
    """
    Retrieves collection by its id
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    response = await collections.read(grant.collection_id)
    if response is None:
        raise NotFoundError("Collection not found")
    response.is_shared_with_me = not grant.is_owner
    return response


@exp_router.patch("/api/user_collections/{collection_id}", response_model=Collection)
async def update_collection(collection_id: str, collectionReq: PatchCollection,
                            collections: UserCollectionRepository = Depends(get_collections),
                            current_user: User = Depends(current_active_user)) -> Collection:
    """
    Updates collection name/description/color. Owner only.
    """
    grant = await access.require_collection_owner(collections, current_user, collection_id)
    return await collections.update(grant.collection_id, collectionReq)

@exp_router.patch("/api/collections/{collection_id}/owner", response_model=Collection)
async def update_collection_owner(collection_id: str, req: PatchCollectionOwner,
                                  collections: UserCollectionRepository = Depends(get_collections),
                                  session: AsyncSession = Depends(get_async_session),
                                  current_user: User = Depends(current_active_admin)) -> Collection:
    """
    Reassigns ownership of a collection to a different user. Admin only.
    """
    new_owner = await users.get_user(session, req.user_id)
    if new_owner is None:
        raise NotFoundError(f"User with id {req.user_id} not found")
    return await collections.set_owner(access.parse_id(collection_id, "Collection"), new_owner.id, new_owner.name)


@exp_router.post("/api/user_collection/{collection_id}/chunks/{chunk_id}", response_model=WriteResult)
async def add_chunk_to_collection(
    collection_id: str,
    chunk_id: str,
    collections: UserCollectionRepository = Depends(get_collections),
    current_user: User = Depends(current_active_user),
) -> WriteResult:
    """
    Connects chunk with user collection, and the chunk's document with the collection.
    Owner only. The result reports each link; ``outcome`` is ``partial`` when the chunk
    was linked but its document could not be.
    """
    grant = await access.require_membership_edit(collections, current_user, collection_id)
    return await collections.add_chunk(access.parse_id(chunk_id, "Chunk"), grant.collection_id)


@exp_router.delete("/api/user_collection/{collection_id}/chunks/{chunk_id}", response_model=schemas.CreateResponse)
async def remove_chunk_from_collection(
    collection_id: str,
    chunk_id: str,
    collections: UserCollectionRepository = Depends(get_collections),
    current_user: User = Depends(current_active_user),
) -> schemas.CreateResponse:
    """
    Removes a chunk from a user collection. Owner only. Removing a chunk that is not in
    the collection succeeds without a change; an unknown chunk is 404.
    """
    grant = await access.require_membership_edit(collections, current_user, collection_id)
    await collections.remove_chunk(chunk_id=access.parse_id(chunk_id, "Chunk"), collection_id=grant.collection_id)
    return {"created": True, "message": "Chunk removed from collection"}


@exp_router.post("/api/collections/{collection_id}/share", response_model=Collection)
async def share_collection(collection_id: str, req: ShareCollectionRequest,
                           collections: UserCollectionRepository = Depends(get_collections),
                           session: AsyncSession = Depends(get_async_session),
                           current_user: User = Depends(current_active_user)) -> Collection:
    """
    Shares a collection with another user. Only the collection's owner may share it.
    """
    grant = await access.require_collection_owner(collections, current_user, collection_id)
    if req.user_id == current_user.id:
        raise InvalidRequestError("Cannot share a collection with its owner")
    if await users.get_user(session, req.user_id) is None:
        raise NotFoundError(f"User with id {req.user_id} not found")
    return await collections.share(grant.collection_id, req.user_id)


@exp_router.delete("/api/collections/{collection_id}/share/{user_id}", response_model=Collection)
async def unshare_collection(collection_id: str, user_id: UUID,
                             collections: UserCollectionRepository = Depends(get_collections),
                             current_user: User = Depends(current_active_user)) -> Collection:
    """
    Revokes a collection share. Only the collection's owner may unshare it.
    """
    grant = await access.require_collection_owner(collections, current_user, collection_id)
    return await collections.unshare(grant.collection_id, user_id)


@exp_router.get("/api/collections/{collection_id}/members", response_model=list[UserSearchResult])
async def get_collection_members(collection_id: str,
                                 collections: UserCollectionRepository = Depends(get_collections),
                                 session: AsyncSession = Depends(get_async_session),
                                 current_user: User = Depends(current_active_user)) -> list[UserSearchResult]:
    """
    Returns the users a collection is currently shared with. Owner and shared users.
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    return await users.get_users(session, await collections.read_shared_user_ids(grant.collection_id))


@exp_router.get("/api/user_collection/{collection_id}/stats", response_model=CollectionStats)
async def get_collection_stats(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                               current_user: User = Depends(current_active_user)) -> CollectionStats:
    grant = await access.require_collection_read(collections, current_user, collection_id)
    response = await collections.read_collection_stats(grant.collection_id)
    if response is None:
        raise NotFoundError("Collection not found")
    return response


@exp_router.delete("/api/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                            current_user: User = Depends(current_active_user)) -> Response:
    """
    Deletes a collection with its tags and annotations. Owner only.
    """
    grant = await access.require_collection_owner(collections, current_user, collection_id)
    await collections.delete(grant.collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.get("/api/user_collection/{collection_id}/documents", response_model=list[Document], response_model_exclude_none=True)
async def get_collection_documents(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                                   current_user: User = Depends(current_active_user)) -> list[Document]:
    """
    Returns documents which belong to collection given by id
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    response = await collections.read_all_documents(grant.collection_id)
    return response

@exp_router.post("/api/collections/{collection_id}/documents/{document_id}", response_model=WriteResult)
async def add_document_to_collection(collection_id: str, document_id: str,
                                     collections: UserCollectionRepository = Depends(get_collections),
                                     current_user: User = Depends(current_active_user)) -> WriteResult:
    """
    Adds document to collection and also links all its chunks to that collection. Owner only.
    The result lists linked chunks/document and failed links; ``outcome`` tells whether
    the document was added completely, partially or not at all.
    """
    grant = await access.require_membership_edit(collections, current_user, collection_id)
    return await collections.add_document(
        document_id=access.parse_id(document_id, "Document"), collection_id=grant.collection_id)

@exp_router.delete("/api/collections/{collection_id}/documents/{document_id}", response_model=WriteResult)
async def remove_document_from_collection(
    collection_id: str,
    document_id: str,
    collections: UserCollectionRepository = Depends(get_collections),
    current_user: User = Depends(current_active_user),
) -> WriteResult:
    """
    Removes a document and its chunks from a collection. Owner only. If some chunks cannot
    be unlinked the document stays in the collection (``outcome`` ``partial``/``failed``).
    Removing a document that is not in the collection changes nothing; an unknown document is 404.
    """
    grant = await access.require_membership_edit(collections, current_user, collection_id)
    return await collections.remove_document(
        document_id=access.parse_id(document_id, "Document"), collection_id=grant.collection_id)

@exp_router.get("/api/collections/{collection_id}/tags", response_model=list[Tag])
async def get_collection_tags(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                              tags: TagRepository = Depends(get_tags),
                              current_user: User = Depends(current_active_user)) -> list[Tag]:
    """
    Returns tags which belong to collection given by id
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    response = await tags.read_by_collection(grant.collection_id)
    return response

@exp_router.get("/api/collections/{collection_id}/documents/{document_id}/stats", response_model=DocumentStats)
async def get_document_stats(collection_id: str, document_id: str, collections: UserCollectionRepository = Depends(get_collections),
                             current_user: User = Depends(current_active_user)) -> DocumentStats:
    """
    Returns per-document statistics within the given collection:
    chunks in collection / total, annotation count, distinct tag count.
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    return await collections.read_document_stats(grant.collection_id, document)


@exp_router.get("/api/collections/{collection_id}/documents/{document_id}", response_model=list[Chunk], response_model_exclude_none=True)
async def get_collection_document_chunks(collection_id: str, document_id: str, collections: UserCollectionRepository = Depends(get_collections),
                                         current_user: User = Depends(current_active_user)) -> list[Chunk]:
    """
    Returns chunks which belong to document and collection given by id
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    response = await collections.read_all_chunks_by_document(document, grant.collection_id)
    return response


@exp_router.get(
    "/api/collections/{collection_id}/documents/{document_id}/neighbour",
    response_model=Chunk | None,
    response_model_exclude_none=False,
)
async def get_neighbour_chunk(
    collection_id: str,
    document_id: str,
    direction: str = Query(..., pattern="^(prev|next)$"),
    boundary_order: int = Query(...),
    collections: UserCollectionRepository = Depends(get_collections),
    current_user: User = Depends(current_active_user),
) -> Chunk | None:
    """
    Returns the chunk immediately before (direction=prev) or after (direction=next)
    the given boundary_order within the document. Marks in_collection accordingly.
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    chunk = await collections.get_neighbour_chunk(
        document_id=document,
        collection_id=grant.collection_id,
        direction=direction,
        boundary_order=boundary_order,
    )
    return chunk


@exp_router.get(
    "/api/collections/{collection_id}/documents/{document_id}/chunks",
    response_model=list[Chunk],
)
async def get_chunks_in_range(
    collection_id: str,
    document_id: str,
    order_gt: int | None = Query(default=None),
    order_lt: int | None = Query(default=None),
    collections: UserCollectionRepository = Depends(get_collections),
    current_user: User = Depends(current_active_user),
) -> list[Chunk]:
    """
    Returns all chunks of a document with order strictly greater than order_gt
    and/or strictly less than order_lt. Used for bulk loading gaps and neighbours.
    """
    grant = await access.require_collection_read(collections, current_user, collection_id)
    document = await access.require_document_in_collection(collections, document_id, grant.collection_id)
    return await collections.get_chunks_in_range(
        document_id=document,
        collection_id=grant.collection_id,
        order_gt=order_gt,
        order_lt=order_lt,
    )


@exp_router.get(
    "/api/documents/{document_id}/chunks/count",
    response_model=int,
)
async def count_document_chunks(
    document_id: str,
    documents: DocumentRepository = Depends(get_documents),
) -> int:
    """Returns the total number of chunks in the given document (public corpus data)."""
    return await documents.count_chunks(access.parse_id(document_id, "Document"))
