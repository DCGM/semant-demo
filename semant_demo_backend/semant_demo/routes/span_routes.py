import logging

from fastapi import APIRouter, Depends, Query

from semant_demo import schemas
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

import logging

# import dependencies
from semant_demo.features.collections import access
from semant_demo.routes.dependencies import get_search
from semant_demo.schema.outcomes import outcome_of
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.schema.spans import (
    PostSpan,
    PatchSpan,
    DeleteSpansForTagsRequest,
    DeleteSpansForTagsResponse,
    BulkUpdateSpansRequest,
    BulkUpdateSpansResponse,
    TagSpanBatchRequest,
    TagSpanWriteResult,
)
from semant_demo.schema.outcomes import WriteResult
logging.basicConfig(level=logging.INFO)

exp_router = APIRouter()

# Annotations (spans) belong to the collection of their tag. Reading needs collection
# read access; creating, editing and deleting needs annotation-edit access (owner or
# shared user). Spans are only placed on chunks of that collection.
#
# Every span write also updates the chunk-level tag references that tag-filtered search
# uses (``adapters/weaviate/chunk_tags.py``). That second write is best effort: when it
# fails the span write is kept and the response reports it as a partial outcome.


def _span_write_result(span: schemas.TagSpan, failed) -> TagSpanWriteResult:
    return TagSpanWriteResult(**span.model_dump(), outcome=outcome_of(1, len(failed)),
                              succeeded=[str(span.id)], failed=failed)


@exp_router.post("/api/tag_spans", response_model=TagSpanWriteResult)
async def create_tag_span(span: PostSpan, tagger: WeaviateAbstraction = Depends(get_search),
                          current_user: User = Depends(current_active_user)) -> TagSpanWriteResult:
    """
    Adds new TagSpan and the matching chunk tag reference. ``outcome`` is ``partial`` when
    the span was saved but the chunk tag could not be updated.
    """
    collection_id = await access.collection_of_tags(tagger.tag, [span.tagId])
    await access.require_annotation_edit(tagger.userCollection, current_user, collection_id)
    await access.require_chunks_in_collection(tagger.userCollection, [span.chunkId], collection_id)
    return _span_write_result(*await tagger.span.create(span=span))


@exp_router.get("/api/tag_spans", response_model=list[schemas.TagSpan])
async def read_tag_spans(
    collection_id: str = Query(description="Collection whose annotations to return"),
    chunk_id: str | None = Query(
        default=None, description="Filter spans by chunk ID"),
    tagger: WeaviateAbstraction = Depends(get_search),
    current_user: User = Depends(current_active_user),
) -> list[schemas.TagSpan]:
    """
    Get stored TagSpans of a collection, optionally for one chunk.
    """
    grant = await access.require_collection_read(tagger.userCollection, current_user, collection_id)
    return await tagger.span.read_all(chunk_id=chunk_id, collection_id=str(grant.collection_id))


@exp_router.post("/api/tag_spans/batch", response_model=dict[str, list[schemas.TagSpan]])
async def read_tag_spans_batch(
    body: TagSpanBatchRequest,
    tagger: WeaviateAbstraction = Depends(get_search),
    current_user: User = Depends(current_active_user),
) -> dict[str, list[schemas.TagSpan]]:
    """
    Get stored TagSpans of a collection for multiple chunk IDs in a single request.
    """
    grant = await access.require_collection_read(tagger.userCollection, current_user, body.collection_id)
    return await tagger.span.read_batch(chunk_ids=body.chunk_ids, collection_id=str(grant.collection_id))


@exp_router.patch("/api/tag_spans/{span_id}", response_model=TagSpanWriteResult)
async def update_tag_span(
    span_id: str,
    body: PatchSpan,
    tagger: WeaviateAbstraction = Depends(get_search),
    current_user: User = Depends(current_active_user),
):
    """
    Update TagSpan's information (start, end, tagId, ...), then re-derive the chunk tag
    references of its (chunk, tag) pair (and the new pair on a tag change), so saving again
    retries a failed chunk tag update. ``outcome`` is ``partial`` when the span was updated
    but the chunk tags could not be.
    """
    collection_id = await access.collection_of_spans(tagger.span, tagger.tag, [span_id])
    await access.require_annotation_edit(tagger.userCollection, current_user, collection_id)
    if body.tagId is not None:
        await access.require_tags_in_collection(tagger.tag, [body.tagId], collection_id)

    return _span_write_result(*await tagger.span.update(
        span_id=span_id,
        update_fields=body
    ))


@exp_router.post(
    "/api/tag_spans/bulk_update",
    response_model=BulkUpdateSpansResponse,
)
async def bulk_update_tag_spans(
    body: BulkUpdateSpansRequest,
    tagger: WeaviateAbstraction = Depends(get_search),
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
    if not body.span_ids:
        return BulkUpdateSpansResponse(outcome=outcome_of(0, 0), spans=[])
    collection_id = await access.collection_of_spans(tagger.span, tagger.tag, body.span_ids)
    await access.require_annotation_edit(tagger.userCollection, current_user, collection_id)
    if body.update.tagId is not None:
        await access.require_tags_in_collection(tagger.tag, [body.update.tagId], collection_id)

    spans, failed = await tagger.span.bulk_update(
        span_ids=body.span_ids,
        update_fields=body.update,
    )
    return BulkUpdateSpansResponse(
        outcome=outcome_of(len(spans), len(failed)),
        succeeded=[s.id for s in spans],
        failed=failed,
        spans=spans,
    )


@exp_router.delete("/api/tag_spans/{span_id}", response_model=WriteResult)
async def delete_tag_span(
    span_id: str,
    tagger: WeaviateAbstraction = Depends(get_search),
    current_user: User = Depends(current_active_user),
) -> WriteResult:
    """
    Delete a TagSpan and the chunk tag reference no other span backs. ``outcome`` is
    ``partial`` when the span was deleted but the chunk tag could not be updated.
    """
    collection_id = await access.collection_of_spans(tagger.span, tagger.tag, [span_id])
    await access.require_annotation_edit(tagger.userCollection, current_user, collection_id)
    failed = await tagger.span.delete(span_id=span_id)
    return WriteResult(outcome=outcome_of(1, len(failed)), succeeded=[span_id], failed=failed)


@exp_router.post(
    "/api/tag_spans/in_document/delete",
    response_model=DeleteSpansForTagsResponse,
)
async def delete_spans_for_tags_in_document(
    body: DeleteSpansForTagsRequest,
    tagger: WeaviateAbstraction = Depends(get_search),
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
    grant = await access.require_annotation_edit(tagger.userCollection, current_user, body.collection_id)
    await access.require_tags_in_collection(tagger.tag, body.tag_ids, grant.collection_id)
    document = await access.require_document_in_collection(tagger.userCollection, body.document_id, grant.collection_id)
    result = await tagger.span.delete_all_spans_for_tags_in_document(
        collection_id=str(grant.collection_id),
        document_id=str(document),
        tag_ids=body.tag_ids,
    )
    return DeleteSpansForTagsResponse(**result.model_dump(), deleted=len(result.succeeded))
