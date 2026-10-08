"""HTTP routes of the Annotations feature (tags and spans); the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, Query, Response, status

from semant_demo import schemas
from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import (
    BulkUpdateSpansRequest, BulkUpdateSpansResponse, DeleteSpansForTagsRequest, DeleteSpansForTagsResponse,
    PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanBatchRequest, TagSpanWriteResult,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.routes.dependencies import get_annotation_store
from semant_demo.schema.outcomes import WriteResult
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

tag_router = APIRouter()
span_router = APIRouter()

# Unknown or inaccessible collections, tags, spans and chunks are answered with 404,
# invalid span offsets with 400, a multi-step write that stopped part way with 500 and a
# body naming the failed and completed steps (see create_app).


########
# Tags #
########

@tag_router.post("/api/tags", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(collection_id: str, tag: PostTag,
                     store: AnnotationStore = Depends(get_annotation_store),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Creates a tag in the collection, or returns the existing tag with the same fields.
    If the tag cannot be added to its collection it is removed again and the request
    fails (500); creating it again is safe.
    """
    return await service.create_tag(store, current_user, collection_id, tag)


@tag_router.get("/api/tags/{tag_uuid}", response_model=Tag)
async def get_tag(tag_uuid: str,
                  store: AnnotationStore = Depends(get_annotation_store),
                  current_user: User = Depends(current_active_user)) -> Tag:
    """
    Retrieve tag by its id
    """
    return await service.get_tag(store, current_user, tag_uuid)


@tag_router.delete("/api/tags/{tag_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_uuid: str,
                     store: AnnotationStore = Depends(get_annotation_store),
                     current_user: User = Depends(current_active_user)) -> None:
    """
    Deletes the tag with its annotations. If a step fails, the request fails (500) with
    the completed steps in the body; completed deletions are kept and deleting again
    continues.
    """
    await service.delete_tag(store, current_user, tag_uuid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@tag_router.patch("/api/tags/{tag_uuid}", response_model=Tag)
async def update_tag(tag_uuid: str, tag_update: PatchTag,
                     store: AnnotationStore = Depends(get_annotation_store),
                     current_user: User = Depends(current_active_user)) -> Tag:
    """
    Updates a tag. Fields that are omitted or null are kept; at least one field must
    have a value (422 otherwise).
    """
    return await service.update_tag(store, current_user, tag_uuid, tag_update)


#########
# Spans #
#########

@span_router.post("/api/tag_spans", response_model=TagSpanWriteResult)
async def create_tag_span(span: PostSpan,
                          store: AnnotationStore = Depends(get_annotation_store),
                          current_user: User = Depends(current_active_user)) -> TagSpanWriteResult:
    """
    Adds new TagSpan and the matching chunk tag reference. ``outcome`` is ``partial`` when
    the span was saved but the chunk tag could not be updated. Offsets outside the text
    of the chunk's document are rejected (400).
    """
    return await service.create_span(store, current_user, span)


@span_router.get("/api/tag_spans", response_model=list[schemas.TagSpan])
async def read_tag_spans(
    collection_id: str = Query(description="Collection whose annotations to return"),
    chunk_id: str | None = Query(
        default=None, description="Filter spans by chunk ID"),
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> list[schemas.TagSpan]:
    """
    Get stored TagSpans of a collection, optionally for one chunk.
    """
    return await service.list_spans(store, current_user, collection_id, chunk_id)


@span_router.post("/api/tag_spans/batch", response_model=dict[str, list[schemas.TagSpan]])
async def read_tag_spans_batch(
    body: TagSpanBatchRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> dict[str, list[schemas.TagSpan]]:
    """
    Get stored TagSpans of a collection for multiple chunk IDs in a single request.
    """
    return await service.list_spans_by_chunks(store, current_user, body.collection_id, body.chunk_ids)


@span_router.patch("/api/tag_spans/{span_id}", response_model=TagSpanWriteResult)
async def update_tag_span(
    span_id: str,
    body: PatchSpan,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
):
    """
    Update TagSpan's information (start, end, tagId, ...), then re-derive the chunk tag
    references of its (chunk, tag) pair (and the new pair on a tag change), so saving again
    retries a failed chunk tag update. ``outcome`` is ``partial`` when the span was updated
    but the chunk tags could not be.
    """
    return await service.update_span(store, current_user, span_id, body)


@span_router.post(
    "/api/tag_spans/bulk_update",
    response_model=BulkUpdateSpansResponse,
)
async def bulk_update_tag_spans(
    body: BulkUpdateSpansRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> BulkUpdateSpansResponse:
    """
    Apply the same :class:`PatchSpan` to many spans in one round-trip.

    Used by the AI-assist "Approve / Reject all selected" action — collapses
    N PATCH calls into one and lets the server fan them out concurrently.

    All spans must belong to one collection the user may annotate; otherwise nothing
    is updated. Updates are best effort: ``spans`` holds the updated spans and
    ``failed`` the spans that could not be updated (``update_span``) and the chunk tag
    updates that failed (``update_chunk_tags``, item ``chunk_id:tag_id``).
    """
    return await service.bulk_update_spans(store, current_user, body.span_ids, body.update)


@span_router.delete("/api/tag_spans/{span_id}", response_model=WriteResult)
async def delete_tag_span(
    span_id: str,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> WriteResult:
    """
    Delete a TagSpan and the chunk tag reference no other span backs. ``outcome`` is
    ``partial`` when the span was deleted but the chunk tag could not be updated.
    """
    return await service.delete_span(store, current_user, span_id)


@span_router.post(
    "/api/tag_spans/in_document/delete",
    response_model=DeleteSpansForTagsResponse,
)
async def delete_spans_for_tags_in_document(
    body: DeleteSpansForTagsRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> DeleteSpansForTagsResponse:
    """
    Bulk-delete approved (``type == 'pos'``) spans for the given tag ids
    within a single (collection, document) scope. Negatives and unresolved
    auto suggestions are left untouched.

    Best effort: ``succeeded`` lists the deleted spans and ``failed`` those that could
    not be deleted (``delete_span``) and the chunk tag updates that failed
    (``update_chunk_tags``, item ``chunk_id:tag_id``).
    """
    result = await service.delete_approved_spans_in_document(
        store, current_user, body.collection_id, body.document_id, body.tag_ids)
    return DeleteSpansForTagsResponse(**result.model_dump(), deleted=len(result.succeeded))
