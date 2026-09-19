import logging

from fastapi import APIRouter, Depends, HTTPException, status, Response, Query

from semant_demo import schemas
from semant_demo.users.auth import current_active_user, current_active_admin
from semant_demo.users.models import User

from semant_demo.weaviate_exceptions import NotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.schema.collections import Collection, CollectionStats, PostCollection, PatchCollection, PatchCollectionOwner
from semant_demo.schema.documents import DocumentStats
from semant_demo.schema.documents import Document
from semant_demo.schema.tags import Tag

# import dependencies
from semant_demo.routes.dependencies import get_async_session, get_user_collection_repository
from semant_demo.schema.chunks import Chunk
from semant_demo.weaviate_utils.user_collection_repository import UserCollectionRepository

logging.basicConfig(level=logging.INFO)


exp_router = APIRouter()


@exp_router.post("/api/user_collections", response_model=Collection, status_code=status.HTTP_201_CREATED)
async def create_user_collection(collectionReq: PostCollection,
                                 user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
                                 current_user: User = Depends(current_active_user)) -> Collection:
    """
    Creates user collection in weaviate db, or not if the same user collection already exists
    """
    collection = await user_collections.create(collectionReq, user=current_user)
    return collection


@exp_router.get("/api/user_collections", response_model=list[Collection])
async def fetch_collections(user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
                            current_user: User = Depends(current_active_user)) -> list[Collection]:
    """
    Retrieves all collections for given user
    """
    response = await user_collections.read_all(current_user)
    return response


@exp_router.get("/api/user_collections/{collection_id}", response_model=Collection)
async def fetch_collection(collection_id: str,
                           user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> Collection:
    """
    Retrieves collection by its id
    """
    response = await user_collections.read(collection_id)
    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Collection with id {collection_id} not found")
    return response


@exp_router.patch("/api/user_collections/{collection_id}", response_model=Collection)
async def update_collection(collection_id: str, collectionReq: PatchCollection,
                            user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> Collection:
    """
    Updates collection name/description/color
    """
    try:
        response = await user_collections.update(collection_id, collectionReq)
        return response
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@exp_router.patch("/api/collections/{collection_id}/owner", response_model=Collection)
async def update_collection_owner(collection_id: str, req: PatchCollectionOwner,
                                  user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
                                  session: AsyncSession = Depends(get_async_session),
                                  current_user: User = Depends(current_active_admin)) -> Collection:
    """
    Reassigns ownership of a collection to a different user. Admin only.
    """
    try:
        response = await user_collections.change_owner(collection_id, req.user_id, session)
        return response
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@exp_router.post("/api/user_collection/chunks", response_model=schemas.CreateResponse)
async def add_chunk_2_collection(req: schemas.Chunk2CollectionReq,
                                 user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
                                 current_user: User = Depends(current_active_user)) -> schemas.CreateResponse:
    """
    Connects chunk with user collection
    """
    ok = await user_collections.add_chunk(chunk_id=req.chunkId, collection_id=req.collectionId)
    if not ok:
        return {"created": False, "message": "Chunk not added to collection"}
    return {"created": True, "message": "Chunk added to collection"}

@exp_router.post("/api/user_collection/chunks/remove", response_model=schemas.CreateResponse)
async def remove_chunk_from_collection(req: schemas.Chunk2CollectionReq,
                                       user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
                                       current_user: User = Depends(current_active_user)) -> schemas.CreateResponse:
    """
    Removes connection between chunk and user collection.
    """
    ok = await user_collections.remove_chunk(chunk_id=req.chunkId, collection_id=req.collectionId)
    if not ok:
        return {"created": False, "message": "Chunk not removed from collection"}
    return schemas.CreateResponse(created=True, message="Chunk removed from collection")

@exp_router.get("/api/user_collection/chunks", response_model=schemas.GetCollectionChunksResponse)
async def get_collection_chunks(collection_id: str,
                                user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
                                current_user: User = Depends(current_active_user)) -> schemas.GetCollectionChunksResponse:
    """
    Returns chunks which belong to collection given by id
    """
    return await user_collections.read_all_chunks(collection_id)


@exp_router.get("/api/user_collection/{collection_id}/stats", response_model=CollectionStats)
async def get_collection_stats(collection_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> CollectionStats:
    response = await user_collections.read_collection_stats(collection_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return response


@exp_router.delete("/api/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> Response:
    try:
        await user_collections.delete(collection_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.get("/api/user_collection/{collection_id}/documents", response_model=list[Document], response_model_exclude_none=True)
async def get_collection_documents(collection_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> list[Document]:
    """
    Returns documents which belong to collection given by id
    """
    response = await user_collections.read_all_documents(collection_id)
    return response

@exp_router.post("/api/collections/{collection_id}/documents/{document_id}")
async def add_document_to_collection(collection_id: str, document_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> Response:
    """
    Adds document to collection and also links all its chunks to that collection
    """
    await user_collections.add_document(document_id=document_id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.delete("/api/collections/{collection_id}/documents/{document_id}")
async def remove_document_from_collection(
    collection_id: str,
    document_id: str,
    user_collections: UserCollectionRepository = Depends(get_user_collection_repository)
) -> Response:
    await user_collections.remove_document(document_id=document_id, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@exp_router.get("/api/collections/{collection_id}/tags", response_model=list[Tag])
async def get_collection_tags(collection_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> list[Tag]:
    """
    Returns tags which belong to collection given by id
    """
    response = await user_collections.read_all_tags(collection_id)
    return response

@exp_router.get("/api/collections/{collection_id}/documents/{document_id}/stats", response_model=DocumentStats)
async def get_document_stats(collection_id: str, document_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> DocumentStats:
    """
    Returns per-document statistics within the given collection:
    chunks in collection / total, annotation count, distinct tag count.
    """
    return await user_collections.read_document_stats(collection_id, document_id)


@exp_router.get("/api/collections/{collection_id}/documents/{document_id}", response_model=list[Chunk], response_model_exclude_none=True)
async def get_collection_document_chunks(collection_id: str, document_id: str, user_collections: UserCollectionRepository = Depends(get_user_collection_repository)) -> list[Chunk]:
    """
    Returns chunks which belong to document and collection given by id
    """
    response = await user_collections.read_all_chunks_by_document(document_id, collection_id)
    return response


@exp_router.delete("/api/user_collection/chunks", response_model=schemas.CreateResponse)
async def delete_chunk_from_collection(
    req: schemas.Chunk2CollectionReq,
    user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
    current_user: User = Depends(current_active_user),
) -> schemas.CreateResponse:
    """
    Removes a chunk from a user collection.
    """
    ok = await user_collections.remove_chunk(chunk_id=req.chunkId, collection_id=req.collectionId)
    if not ok:
        return {"created": False, "message": "Chunk not removed from collection"}
    return {"created": True, "message": "Chunk removed from collection"}


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
    user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
) -> Chunk | None:
    """
    Returns the chunk immediately before (direction=prev) or after (direction=next)
    the given boundary_order within the document. Marks in_collection accordingly.
    """
    chunk = await user_collections.get_neighbour_chunk(
        document_id=document_id,
        collection_id=collection_id,
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
    user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
) -> list[Chunk]:
    """
    Returns all chunks of a document with order strictly greater than order_gt
    and/or strictly less than order_lt. Used for bulk loading gaps and neighbours.
    """
    return await user_collections.get_chunks_in_range(
        document_id=document_id,
        collection_id=collection_id,
        order_gt=order_gt,
        order_lt=order_lt,
    )


@exp_router.get(
    "/api/documents/{document_id}/chunks/count",
    response_model=int,
)
async def count_document_chunks(
    document_id: str,
    user_collections: UserCollectionRepository = Depends(get_user_collection_repository),
) -> int:
    """Returns the total number of chunks in the given document."""
    return await user_collections.count_document_chunks(document_id=document_id)
