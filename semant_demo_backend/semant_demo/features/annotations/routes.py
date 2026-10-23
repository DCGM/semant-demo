"""HTTP routes of the Annotations feature (tags and spans); the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, Query, Response, status

from semant_demo.features.annotations.schemas import TagSpan
from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import (
    AnnotatedDocument, AnnotationIds, AnnotationIdsRequest, AnnotationPage, AnnotationRestoreRequest,
    AnnotationReviewRequest, AnnotationReviewResult, AnnotationSort, ChunkTagSyncRequest, SpanType,
    BulkUpdateSpansRequest, BulkUpdateSpansResponse, DeleteSpansForTagsRequest, DeleteSpansForTagsResponse,
    PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanBatchRequest, TagSpanWriteResult,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.routes.dependencies import get_annotation_store
from semant_demo.core.outcomes import WriteResult
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


@span_router.get("/api/tag_spans", response_model=list[TagSpan])
async def read_tag_spans(
    collection_id: str = Query(description="Collection whose annotations to return"),
    chunk_id: str | None = Query(
        default=None, description="Filter spans by chunk ID"),
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> list[TagSpan]:
    """
    Get stored TagSpans of a collection, optionally for one chunk.
    """
    return await service.list_spans(store, current_user, collection_id, chunk_id)


@span_router.post("/api/tag_spans/batch", response_model=dict[str, list[TagSpan]])
async def read_tag_spans_batch(
    body: TagSpanBatchRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> dict[str, list[TagSpan]]:
    """
    Get stored TagSpans of a collection for multiple chunk IDs in a single request.
    """
    return await service.list_spans_by_chunks(store, current_user, body.collection_id, body.chunk_ids)


_SPAN_COLLECTION = Query(description="Collection of the span; a span of another collection is not found")
_EXPECTED_VERSION = Query(default=None, description=(
    "The span's editVersion as the client knows it: when someone else wrote the span since, nothing is "
    "changed and the answer is 409 with the current span (``current``)"))


@span_router.patch("/api/tag_spans/{span_id}", response_model=TagSpanWriteResult)
async def update_tag_span(
    span_id: str,
    body: PatchSpan,
    collection_id: str = _SPAN_COLLECTION,
    expected_version: int | None = _EXPECTED_VERSION,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
):
    """
    Update TagSpan's information (start, end, tagId, ...), then re-derive the chunk tag
    references of its (chunk, tag) pair (and the new pair on a tag change), so saving again
    retries a failed chunk tag update. ``outcome`` is ``partial`` when the span was updated
    but the chunk tags could not be. A span written by someone else since
    ``expected_version`` is not changed (409), unless it already is as the patch asks.
    """
    return await service.update_span(store, current_user, collection_id, span_id, body, expected_version)


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

    All spans must belong to ``collection_id``, which the user may annotate; otherwise
    nothing is updated. Updates are best effort: ``spans`` holds the updated spans and
    ``failed`` the spans that could not be updated (``update_span``) and the chunk tag
    updates that failed (``update_chunk_tags``, item ``chunk_id:tag_id``). Spans written by
    someone else since their version in ``expected_versions`` are not changed
    (``edit_conflict``; their current state in ``conflicts``).
    """
    return await service.bulk_update_spans(store, current_user, body.collection_id, body.span_ids, body.update,
                                           body.expected_versions)


@span_router.delete("/api/tag_spans/{span_id}", response_model=WriteResult)
async def delete_tag_span(
    span_id: str,
    collection_id: str = _SPAN_COLLECTION,
    expected_version: int | None = _EXPECTED_VERSION,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> WriteResult:
    """
    Delete a TagSpan and the chunk tag reference no other span backs. ``outcome`` is
    ``partial`` when the span was deleted but the chunk tag could not be updated. A span
    written by someone else since ``expected_version`` is not deleted (409).
    """
    return await service.delete_span(store, current_user, collection_id, span_id, expected_version)


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


#############################
# Concordance (KWIC, #329)  #
#############################

_TAG_FILTER = Query(default=None, description="Only annotations of these tags (repeat the parameter)")
_TYPE_FILTER = Query(default=None, alias="type", description=(
    "Only annotations of these types: pos (manual or approved), auto (unresolved suggestion), "
    "neg (rejected); default pos and auto"))


@span_router.get("/api/user_collections/{collection_id}/annotations", response_model=AnnotationPage)
async def list_collection_annotations(
    collection_id: str,
    tag_id: list[str] | None = _TAG_FILTER,
    types: list[SpanType] | None = _TYPE_FILTER,
    q: str | None = Query(default=None, max_length=500,
                          description="Words that must each occur in the annotated text (inside a word, any case)"),
    document_id: list[str] | None = Query(default=None, description="Only annotations in these documents"),
    year_from: int | None = Query(default=None, description="Only documents issued in or after this year"),
    year_to: int | None = Query(default=None, description="Only documents issued in or before this year"),
    sort: AnnotationSort = AnnotationSort.document,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    annotation_id: list[str] | None = Query(default=None, max_length=200,
                                            description="Only these annotations"),
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> AnnotationPage:
    """
    One page of the collection's annotations as concordance rows (stored text, left and
    right context, tag, type, document title and year) and the number of all matches.
    Rows are in a total order, so paging is deterministic. Rows whose text is not derived
    for their current revision have ``textStatus`` other than ``ready`` and no text.
    """
    return await service.query_annotations(
        store, current_user, collection_id, tag_ids=tag_id, types=types, text=q, document_ids=document_id,
        year_from=year_from, year_to=year_to, sort=sort, limit=limit, offset=offset, annotation_ids=annotation_id)


@span_router.get("/api/user_collections/{collection_id}/annotations/documents",
                 response_model=list[AnnotatedDocument])
async def list_annotated_documents(
    collection_id: str,
    tag_id: list[str] | None = _TAG_FILTER,
    types: list[SpanType] | None = _TYPE_FILTER,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> list[AnnotatedDocument]:
    """The documents with annotations of the given tags and types, with their counts, by title."""
    return await service.list_annotated_documents(store, current_user, collection_id, tag_ids=tag_id, types=types)


###################################
# Selection and review (#459)     #
###################################

@span_router.post("/api/user_collections/{collection_id}/annotations/ids", response_model=AnnotationIds)
async def resolve_collection_annotation_ids(
    collection_id: str,
    body: AnnotationIdsRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> AnnotationIds:
    """
    The ids of all annotations matching the concordance filters now, or of those among
    ``within`` that match (which members of a selection the filters show). At most 5,000;
    a query matching more is refused (400), never truncated.
    """
    return await service.resolve_annotation_ids(store, current_user, collection_id, body)


@span_router.post("/api/user_collections/{collection_id}/annotations/review", response_model=AnnotationReviewResult)
async def review_collection_annotations(
    collection_id: str,
    body: AnnotationReviewRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> AnnotationReviewResult:
    """
    Approve (``pos``), reject (``neg``, kept), retag or delete up to 200 annotations of the
    collection, each expected at its version in ``expected_versions``. Best effort and per
    item: ``succeeded`` lists the changed annotations, ``failed`` the ones not changed or
    uncertain, those written by someone else since (``edit_conflict``) and the ids that are
    no annotation of the collection (``find_annotation``); ``versions`` the new versions.
    Nothing is rolled back.
    """
    return await service.review_annotations(store, current_user, collection_id, body)


@span_router.post("/api/user_collections/{collection_id}/annotations/restore", response_model=AnnotationReviewResult)
async def restore_collection_annotations(
    collection_id: str,
    body: AnnotationRestoreRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> AnnotationReviewResult:
    """
    Undo the last review or boundary change (#461): put back the previous values of up to
    200 annotations of the collection, each only while it still has the version that change
    left. Per item like a review: ``edit_conflict`` for an annotation written since (not
    restored), ``find_annotation`` for one deleted meanwhile, ``check_range`` for a range
    that no longer fits the document's text. Refused (400) where annotations have no edit
    versions.
    """
    return await service.restore_annotations(store, current_user, collection_id, body)


@span_router.post("/api/user_collections/{collection_id}/annotations/chunk-tags/sync", response_model=WriteResult)
async def sync_collection_annotation_chunk_tags(
    collection_id: str,
    body: ChunkTagSyncRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> WriteResult:
    """
    Re-derive the tag-filtered search references of up to 1,000 (chunk, tag) pairs of the
    collection's tags from its annotations: repairs the ``update_chunk_tags`` failures of a
    review, also after a deletion. Needs annotation-edit access.
    """
    return await service.sync_annotation_chunk_tags(store, current_user, collection_id, body)
