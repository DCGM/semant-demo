"""HTTP routes of the Annotations feature (tags and spans); the rules live in ``service.py``."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from semant_demo.features.annotations.schemas import TagSpan
from semant_demo.features.annotations import service
from semant_demo.features.annotations.schemas import (
    MAX_QUERY_TEXT_LENGTH, AnnotatedDocument, AnnotationCounts, AnnotationFilters, AnnotationIds, AnnotationIdsRequest,
    AnnotationPage, AnnotationRanking, AnnotationRestoreRequest, RetrievalMode, TextScope, MAX_TOP_K, DEFAULT_TOP_K,
    AnnotationReviewRequest, AnnotationReviewResult, AnnotationSort, ChunkTagSyncRequest, SpanType,
    BulkUpdateSpansRequest, BulkUpdateSpansResponse, DeleteSpansForTagsRequest, DeleteSpansForTagsResponse,
    PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanBatchRequest, TagSpanWriteResult,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.adapters.sql.attributes import AttributeRepository
from semant_demo.routes.dependencies import get_annotation_store, get_attribute_definitions
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
                     attributes: AttributeRepository = Depends(get_attribute_definitions),
                     current_user: User = Depends(current_active_user)) -> None:
    """
    Deletes the tag with its annotations, then removes it from the collection attributes that
    list it (an attribute that loses its last tag applies to no tag, never to all tags). If a
    step fails, the request fails (500) with the completed steps in the body; completed
    deletions are kept and deleting again continues. When only the last step
    (``remove_from_attributes``) fails, the tag is deleted and stays listed on those attributes.
    """
    await service.delete_tag(store, current_user, tag_uuid, attributes)
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


def annotation_filters(
    tag_id: list[str] | None = _TAG_FILTER,
    types: list[SpanType] | None = _TYPE_FILTER,
    q: str | None = Query(default=None, max_length=MAX_QUERY_TEXT_LENGTH, description=(
        "Words that must each occur inside a word of the fields of text_scope, ignoring case")),
    text_scope: TextScope = Query(default=TextScope.annotation, description=(
        "Where the words of q must occur: annotation (the annotated text), context (left or right "
        "context) or both; each word may occur in another field")),
    document_id: list[str] | None = Query(default=None, description="Only annotations in these documents"),
    year_min: int | None = Query(default=None, description="Only documents issued in or after this year"),
    year_max: int | None = Query(default=None, description="Only documents issued in or before this year"),
    title_contains: list[str] = Query(default=[], description=(
        "Only documents whose title matches one of these (each word inside a title word, any case)")),
    libraries: list[str] = Query(default=[], description="Only documents of these libraries"),
    languages: list[str] = Query(default=[], description="Only documents in these languages"),
    attribute: list[str] | None = Query(default=None, max_length=20, description=(
        "Only annotations with this accepted attribute value, as <attribute id>:<value id> (repeat; values of "
        "one attribute match any, different attributes all)")),
    unassigned: list[str] | None = Query(default=None, max_length=20, description=(
        "Only annotations without an accepted value of this attribute id (repeat)")),
) -> AnnotationFilters:
    """The annotation query (``AnnotationFilters``, #663) of a GET request's parameters. The
    document filters are the shared ``DocumentFilters`` with the parameter names of document
    browsing; an invalid one is refused (422) as there."""
    try:
        return AnnotationFilters.model_validate({
            "tag_ids": tag_id, "types": types, "q": q, "text_scope": text_scope, "document_ids": document_id,
            "document_filters": {"year_min": year_min, "year_max": year_max, "title_contains": title_contains,
                                 "libraries": libraries, "languages": languages},
            "attribute_values": attribute or [], "attribute_unassigned": unassigned or []})
    except ValidationError as e:
        raise RequestValidationError([{**error, "loc": ("query", *error["loc"])} for error in e.errors()]) from e


def annotation_ranking(
    mode: RetrievalMode = Query(default=RetrievalMode.lexical, description=(
        "lexical: every match of the filters; semantic: the k nearest in meaning to q; hybrid: the k best by "
        "meaning and BM25 of q; similar: the k nearest to the annotation similar_to (filters apply first)")),
    k: int = Query(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K, description="Ranked modes: at most this many"),
    similar_to: str | None = Query(default=None, description="Mode similar: the source annotation id"),
    include_source: bool = Query(default=False, description="Mode similar: rank the source annotation too"),
) -> AnnotationRanking:
    """The retrieval mode (``AnnotationRanking``, #664) of a GET request's parameters."""
    try:
        return AnnotationRanking.model_validate({"mode": mode, "k": k, "similar_to": similar_to,
                                                 "include_source": include_source})
    except ValidationError as e:
        raise RequestValidationError([{**error, "loc": ("query", *error["loc"])} for error in e.errors()]) from e


def _unavailable(e: UnavailableFilter) -> HTTPException:
    """A document filter on a property the corpus store does not record (422, never no results)."""
    return HTTPException(status_code=422, detail=str(e))


@span_router.get("/api/user_collections/{collection_id}/annotations", response_model=AnnotationPage)
async def list_collection_annotations(
    collection_id: str,
    filters: AnnotationFilters = Depends(annotation_filters),
    ranking: AnnotationRanking = Depends(annotation_ranking),
    sort: AnnotationSort | None = Query(default=None, description=(
        "Lexical mode: the row order, default document; ranked modes are in relevance order and take none")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    annotation_id: list[str] | None = Query(default=None, max_length=200,
                                            description="Only these annotations"),
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> AnnotationPage:
    """
    One page of the collection's annotations matching the annotation query as concordance
    rows (stored text, left and right context, tag, type, document title and year) and the
    number of all matches. Rows are in a total order, so paging is deterministic. Rows whose
    text is not derived for their current revision have ``textStatus`` other than ``ready``
    and no text. A document filter this corpus database cannot evaluate is refused (422).

    A ranked ``mode`` (#664) pages through its top ``k`` in relevance order, and ``result``
    describes it (``top_k``, truncation, vector coverage). Semantic and hybrid without a
    usable embedding service answer 503; a similar source without a current vector 400.
    """
    try:
        return await service.query_annotations(store, current_user, collection_id, filters, ranking=ranking,
                                               sort=sort, limit=limit, offset=offset, annotation_ids=annotation_id)
    except UnavailableFilter as e:
        raise _unavailable(e) from e


@span_router.get("/api/user_collections/{collection_id}/annotations/counts", response_model=AnnotationCounts)
async def count_collection_annotations(
    collection_id: str,
    tag_id: list[str] | None = _TAG_FILTER,
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> AnnotationCounts:
    """How many approved annotations, unresolved suggestions and rejected suggestions the
    collection holds (of the given tags), e.g. to warn what a delete would remove along."""
    return await service.count_annotations(store, current_user, collection_id, tag_ids=tag_id)


@span_router.get("/api/user_collections/{collection_id}/annotations/documents",
                 response_model=list[AnnotatedDocument])
async def list_annotated_documents(
    collection_id: str,
    filters: AnnotationFilters = Depends(annotation_filters),
    store: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> list[AnnotatedDocument]:
    """The documents with annotations matching the annotation query, with their counts, by
    title: the source filter's choices. ``document_id`` is not applied (it is being chosen)."""
    try:
        return await service.list_annotated_documents(store, current_user, collection_id, filters)
    except UnavailableFilter as e:
        raise _unavailable(e) from e


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
    a query matching more is refused (400), never truncated. A ranked ``ranking`` resolves
    exactly its top ``k`` (#664).
    """
    try:
        return await service.resolve_annotation_ids(store, current_user, collection_id, body)
    except UnavailableFilter as e:
        raise _unavailable(e) from e


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
