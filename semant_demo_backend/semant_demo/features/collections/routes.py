"""HTTP routes of the Collections feature; the rules live in ``service.py``."""
from uuid import UUID

from fastapi import APIRouter, Depends, status, Response, Query

from semant_demo import schemas
from semant_demo.adapters.sql.users import UserLookup
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.features.collections import service
from semant_demo.features.collections.schemas import Collection, CollectionStats, PostCollection, PatchCollection, PatchCollectionOwner, ShareCollectionRequest
from semant_demo.routes.dependencies import get_collections, get_tags, get_user_lookup
from semant_demo.schema.chunks import Chunk
from semant_demo.schema.documents import Document, DocumentStats
from semant_demo.schema.outcomes import WriteResult
from semant_demo.features.annotations.schemas import Tag
from semant_demo.users.auth import current_active_user, current_active_admin
from semant_demo.users.models import User
from semant_demo.users.schemas import UserSearchResult

exp_router = APIRouter()

# The service functions check access (features/collections/access.py): reads need
# owner/shared access, membership/metadata/sharing changes need the owner. Unknown
# collections, documents, chunks and users are answered with 404 (NotFoundError, see
# create_app).


@exp_router.post("/api/user_collections", response_model=Collection, status_code=status.HTTP_201_CREATED)
async def create_user_collection(collectionReq: PostCollection,
                                 collections: UserCollectionRepository = Depends(get_collections),
                                 current_user: User = Depends(current_active_user)) -> Collection:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    return await service.create_collection(collections, current_user, collectionReq)


@exp_router.get("/api/user_collections", response_model=list[Collection])
async def fetch_collections(collections: UserCollectionRepository = Depends(get_collections),
                            current_user: User = Depends(current_active_user)) -> list[Collection]:
    """
    Retrieves all collections for given user
    """
    return await service.list_collections(collections, current_user)


@exp_router.get("/api/user_collections/{collection_id}", response_model=Collection)
async def fetch_collection(collection_id: str,
                           collections: UserCollectionRepository = Depends(get_collections),
                           current_user: User = Depends(current_active_user)) -> Collection:
    """
    Retrieves collection by its id
    """
    return await service.get_collection(collections, current_user, collection_id)


@exp_router.patch("/api/user_collections/{collection_id}", response_model=Collection)
async def update_collection(collection_id: str, collectionReq: PatchCollection,
                            collections: UserCollectionRepository = Depends(get_collections),
                            current_user: User = Depends(current_active_user)) -> Collection:
    """
    Updates collection name/description/color. Owner only.
    """
    return await service.update_collection(collections, current_user, collection_id, collectionReq)

@exp_router.patch("/api/collections/{collection_id}/owner", response_model=Collection)
async def update_collection_owner(collection_id: str, req: PatchCollectionOwner,
                                  collections: UserCollectionRepository = Depends(get_collections),
                                  users: UserLookup = Depends(get_user_lookup),
                                  current_user: User = Depends(current_active_admin)) -> Collection:
    """
    Reassigns ownership of a collection to a different user. Admin only.
    """
    return await service.change_owner(collections, users, current_user, collection_id, req.user_id)


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
    return await service.add_chunk(collections, current_user, collection_id, chunk_id)


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
    await service.remove_chunk(collections, current_user, collection_id, chunk_id)
    return {"created": True, "message": "Chunk removed from collection"}


@exp_router.post("/api/collections/{collection_id}/share", response_model=Collection)
async def share_collection(collection_id: str, req: ShareCollectionRequest,
                           collections: UserCollectionRepository = Depends(get_collections),
                           users: UserLookup = Depends(get_user_lookup),
                           current_user: User = Depends(current_active_user)) -> Collection:
    """
    Shares a collection with another user. Only the collection's owner may share it.
    """
    return await service.share_collection(collections, users, current_user, collection_id, req.user_id)


@exp_router.delete("/api/collections/{collection_id}/share/{user_id}", response_model=Collection)
async def unshare_collection(collection_id: str, user_id: UUID,
                             collections: UserCollectionRepository = Depends(get_collections),
                             current_user: User = Depends(current_active_user)) -> Collection:
    """
    Revokes a collection share. Only the collection's owner may unshare it.
    """
    return await service.unshare_collection(collections, current_user, collection_id, user_id)


@exp_router.get("/api/collections/{collection_id}/members", response_model=list[UserSearchResult])
async def get_collection_members(collection_id: str,
                                 collections: UserCollectionRepository = Depends(get_collections),
                                 users: UserLookup = Depends(get_user_lookup),
                                 current_user: User = Depends(current_active_user)) -> list[UserSearchResult]:
    """
    Returns the users a collection is currently shared with. Owner and shared users.
    """
    return await service.list_members(collections, users, current_user, collection_id)


@exp_router.get("/api/user_collection/{collection_id}/stats", response_model=CollectionStats)
async def get_collection_stats(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                               current_user: User = Depends(current_active_user)) -> CollectionStats:
    return await service.get_collection_stats(collections, current_user, collection_id)


@exp_router.delete("/api/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                            current_user: User = Depends(current_active_user)) -> Response:
    """
    Deletes a collection with its tags and annotations. Owner only. If a step fails, the
    request fails (500) with the completed steps in the body; completed deletions are kept
    and deleting again continues.
    """
    await service.delete_collection(collections, current_user, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.get("/api/user_collection/{collection_id}/documents", response_model=list[Document], response_model_exclude_none=True)
async def get_collection_documents(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                                   current_user: User = Depends(current_active_user)) -> list[Document]:
    """
    Returns documents which belong to collection given by id
    """
    return await service.list_documents(collections, current_user, collection_id)

@exp_router.post("/api/collections/{collection_id}/documents/{document_id}", response_model=WriteResult)
async def add_document_to_collection(collection_id: str, document_id: str,
                                     collections: UserCollectionRepository = Depends(get_collections),
                                     current_user: User = Depends(current_active_user)) -> WriteResult:
    """
    Adds document to collection and also links all its chunks to that collection. Owner only.
    The result lists linked chunks/document and failed links; ``outcome`` tells whether
    the document was added completely, partially or not at all.
    """
    return await service.add_document(collections, current_user, collection_id, document_id)

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
    return await service.remove_document(collections, current_user, collection_id, document_id)

@exp_router.get("/api/collections/{collection_id}/tags", response_model=list[Tag])
async def get_collection_tags(collection_id: str, collections: UserCollectionRepository = Depends(get_collections),
                              tags: TagRepository = Depends(get_tags),
                              current_user: User = Depends(current_active_user)) -> list[Tag]:
    """
    Returns tags which belong to collection given by id
    """
    return await service.list_tags(collections, tags, current_user, collection_id)

@exp_router.get("/api/collections/{collection_id}/documents/{document_id}/stats", response_model=DocumentStats)
async def get_document_stats(collection_id: str, document_id: str, collections: UserCollectionRepository = Depends(get_collections),
                             current_user: User = Depends(current_active_user)) -> DocumentStats:
    """
    Returns per-document statistics within the given collection:
    chunks in collection / total, annotation count, distinct tag count.
    """
    return await service.get_document_stats(collections, current_user, collection_id, document_id)


@exp_router.get("/api/collections/{collection_id}/documents/{document_id}", response_model=list[Chunk], response_model_exclude_none=True)
async def get_collection_document_chunks(collection_id: str, document_id: str, collections: UserCollectionRepository = Depends(get_collections),
                                         current_user: User = Depends(current_active_user)) -> list[Chunk]:
    """
    Returns chunks which belong to document and collection given by id
    """
    return await service.get_document_chunks(collections, current_user, collection_id, document_id)


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
    return await service.get_neighbour_chunk(collections, current_user, collection_id, document_id,
                                             direction, boundary_order)


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
    return await service.get_chunks_in_range(collections, current_user, collection_id, document_id,
                                             order_gt, order_lt)
