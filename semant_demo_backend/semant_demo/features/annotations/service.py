"""Annotation use cases: tag definitions and span annotations of a collection.

Every public function checks access itself (``features/collections/access.py``, ADR 0007)
before any other read or write, so callers outside HTTP get the same rules: reading
needs collection read access, span writes need annotation-edit access, tag definition
writes need tag-definition-edit access (owner and shared users for all three). Spans
belong to the collection of their tag and are placed only on chunks of that collection.
``user`` is the authenticated user or ``None``; ids may be strings or UUIDs, malformed
ids are "not found".

Span writes are followed by the re-derivation of the chunk tag references that
tag-filtered search uses (ADR 0004, ``adapters/weaviate/chunk_tags.py``) for every
(chunk, tag) pair they touched, also when the span write raised (a timed-out write may
have landed). That second write is best effort (ADR 0002): its failure keeps the span
write and is reported as step ``update_chunk_tags``.

Span types keep their meaning: ``pos`` a manual or approved annotation, ``auto`` an
unresolved AI suggestion, ``neg`` a rejected suggestion kept as a negative example.
Approving or rejecting is a type change (``auto`` -> ``pos`` / ``neg``).
"""
import asyncio
from dataclasses import dataclass
from uuid import UUID

import semant_demo.schemas as schemas
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag, ChunkTagRepository
from semant_demo.adapters.weaviate.collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.core.errors import IncompleteWriteError, InvalidRequestError, NotFoundError
from semant_demo.features.annotations.offsets import InvalidSpanRange, check_span_range
from semant_demo.features.annotations.schemas import (
    BulkUpdateSpansResponse, PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanWriteResult,
)
from semant_demo.features.collections import access
from semant_demo.features.collections.access import Principal
from semant_demo.schema.outcomes import StepFailure, WriteResult, outcome_of

Id = str | UUID

# Following chunks read per round when a span continues past its anchor chunk.
_FOLLOWING_CHUNKS_PAGE = 20


@dataclass
class AnnotationStore:
    """The repositories annotation use cases read and write (one Weaviate client)."""
    collections: UserCollectionRepository
    tags: TagRepository
    spans: SpanRepository
    chunk_tags: ChunkTagRepository
    documents: DocumentRepository


########
# Tags #
########

async def create_tag(store: AnnotationStore, user: Principal | None, collection_id: Id, tag: PostTag) -> Tag:
    """
    Creates a tag in the collection, or returns the collection's tag with exactly the
    same fields.

    Two writes: the tag is inserted, then linked to its collection. A tag without the
    link belongs to no collection and nobody can reach it, so when linking fails the new
    tag is deleted again (best effort) and ``IncompleteWriteError`` (step
    ``link_collection``) is raised: nothing was created and retrying is safe. If that
    deletion fails too, the message says an unreachable tag may remain.
    """
    grant = await access.require_tag_definition_edit(store.collections, user, collection_id)
    same = await store.tags.find_same(grant.collection_id, tag)
    if same is not None:
        return same
    tag_id = await store.tags.insert(tag)
    try:
        await store.tags.link_to_collection(tag_id, grant.collection_id)
    except Exception as exc:
        link = step_failure("link_collection", tag_id, exc)
        try:
            await store.tags.delete_unlinked(tag_id)
        except Exception as cleanup_exc:
            step_failure("delete_unlinked_tag", tag_id, cleanup_exc)
            raise IncompleteWriteError(
                f"The tag could not be added to the collection, and removing it again failed: an "
                f"unreachable tag {tag_id} may remain in storage. Creating the tag again is safe.",
                step="link_collection", completed={"insert_tag": 1}, uncertain=link.uncertain) from exc
        raise IncompleteWriteError(
            "The tag could not be added to the collection; nothing was saved. Creating it again is safe.",
            step="link_collection", completed={}, uncertain=link.uncertain) from exc
    return Tag(id=tag_id, **tag.model_dump())


async def get_tag(store: AnnotationStore, user: Principal | None, tag_id: Id) -> Tag:
    await access.require_collection_read(store.collections, user, await access.collection_of_tags(store.tags, [tag_id]))
    tag = await store.tags.read(access.parse_id(tag_id, "Tag"))
    if tag is None:
        raise NotFoundError(f"Tag with id {tag_id} not found")
    return tag


async def update_tag(store: AnnotationStore, user: Principal | None, tag_id: Id, patch: PatchTag) -> Tag:
    """Sets the fields given with a value; omitted or null fields are kept."""
    collection_id = await access.collection_of_tags(store.tags, [tag_id])
    await access.require_tag_definition_edit(store.collections, user, collection_id)
    return await store.tags.update(access.parse_id(tag_id, "Tag"), patch)


async def delete_tag(store: AnnotationStore, user: Principal | None, tag_id: Id) -> None:
    """
    Deletes the tag with its spans and chunk tag references. A failed step raises
    ``IncompleteWriteError`` naming it and the completed steps; deleting again continues.
    """
    collection_id = await access.collection_of_tags(store.tags, [tag_id])
    await access.require_tag_definition_edit(store.collections, user, collection_id)
    await store.tags.delete(access.parse_id(tag_id, "Tag"))


#########
# Spans #
#########

async def list_spans(store: AnnotationStore, user: Principal | None, collection_id: Id,
                     chunk_id: Id | None = None) -> list[schemas.TagSpan]:
    """The collection's spans, optionally only those starting on one chunk."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    chunk = access.parse_id(chunk_id, "Chunk") if chunk_id is not None else None
    return await store.spans.read_by_collection(grant.collection_id, chunk)


async def list_spans_by_chunks(store: AnnotationStore, user: Principal | None, collection_id: Id,
                               chunk_ids: list[Id] | None) -> dict[str, list[schemas.TagSpan]]:
    """The collection's spans starting on each chunk, keyed by the chunk ids as given."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    if not chunk_ids:
        return {}
    by_id = await store.spans.read_by_chunks(
        grant.collection_id, list(dict.fromkeys(access.parse_id(c, "Chunk") for c in chunk_ids)))
    return {str(c): by_id.get(str(access.parse_id(c, "Chunk")), []) for c in chunk_ids}


async def _check_range(store: AnnotationStore, chunk_id: UUID, start: int, end: int) -> None:
    """The offsets must describe text of the chunk's document (``offsets.py``)."""
    anchor = await store.documents.read_chunk_text(chunk_id)
    if anchor is None:
        raise NotFoundError("Chunk not found")
    chunks = [anchor]
    while True:
        try:
            check_span_range(chunks, start, end)
            return
        except InvalidSpanRange as e:
            if e.code != "past_end" or anchor.document_id is None:
                raise
            more = await store.documents.read_following_chunk_texts(
                anchor.document_id, chunks[-1].order, _FOLLOWING_CHUNKS_PAGE)
            if not more:
                raise
            chunks += more


def _write_result(span: schemas.TagSpan, failed: list[StepFailure]) -> TagSpanWriteResult:
    return TagSpanWriteResult(**span.model_dump(), outcome=outcome_of(1, len(failed)),
                              succeeded=[str(span.id)], failed=failed)


async def _pairs_of_spans(store: AnnotationStore, span_ids: list[UUID]) -> set[ChunkTag]:
    refs = await store.spans.read_refs(span_ids)
    return {ChunkTag(c, t) for tags, chunks in refs.values() for t in tags for c in chunks}


async def save_span(store: AnnotationStore, span: PostSpan) -> TagSpanWriteResult:
    """
    Stores a span and re-derives its chunk tag. No access or offset check: the caller has
    checked annotation-edit access, the tag and the chunk scope (``create_span``, or the
    AI suggestion route for validated provider proposals).
    """
    pairs = {ChunkTag.of(span.chunkId, span.tagId)}
    try:
        span_id = await store.spans.insert(span)
    except Exception:
        await store.chunk_tags.sync(pairs)
        raise
    failed = await store.chunk_tags.sync(pairs)
    return _write_result(schemas.TagSpan(id=str(span_id), **span.model_dump()), failed)


async def create_span(store: AnnotationStore, user: Principal | None, span: PostSpan) -> TagSpanWriteResult:
    """
    Creates a span with the tag's collection as scope; the chunk must be in that
    collection and the offsets must describe text of its document (cross-chunk spans
    continue into the following consecutive chunks; see ``offsets.py``).
    ``outcome`` is ``partial`` when the span was saved but its chunk tag was not.
    """
    collection_id = await access.collection_of_tags(store.tags, [span.tagId])
    await access.require_annotation_edit(store.collections, user, collection_id)
    [chunk_id] = await access.require_chunks_in_collection(store.collections, [span.chunkId], collection_id)
    await _check_range(store, chunk_id, span.start, span.end)
    return await save_span(store, span)


async def _authorize_span_patch(store: AnnotationStore, user: Principal | None, span_ids: list[UUID],
                                patch: PatchSpan) -> None:
    if not patch.model_dump(exclude_none=True):
        raise InvalidRequestError("No fields provided for update")
    collection_id = await access.collection_of_spans(store.spans, store.tags, span_ids)
    await access.require_annotation_edit(store.collections, user, collection_id)
    if patch.tagId is not None:
        await access.require_tags_in_collection(store.tags, [patch.tagId], collection_id)


async def _check_patched_ranges(store: AnnotationStore, span_ids: list[UUID], patch: PatchSpan) -> None:
    """Offsets resulting from an offset patch must be valid for every span; checked before any write."""
    if patch.start is None and patch.end is None:
        return
    for span_id in span_ids:
        span = await store.spans.read(span_id)
        if span is None:
            raise NotFoundError("Span not found")
        await _check_range(store, access.parse_id(span.chunkId, "Chunk"),
                           span.start if patch.start is None else patch.start,
                           span.end if patch.end is None else patch.end)


async def _pairs_touched_by(store: AnnotationStore, span_ids: list[UUID], patch: PatchSpan) -> set[ChunkTag]:
    """The spans' current (chunk, tag) pairs and, on a tag change, the new tag's pairs."""
    pairs = await _pairs_of_spans(store, span_ids)
    if patch.tagId is not None:
        pairs |= {ChunkTag.of(p.chunk_id, patch.tagId) for p in pairs}
    return pairs


async def _update_and_read(store: AnnotationStore, span_id: UUID, patch: PatchSpan) -> schemas.TagSpan:
    await store.spans.update(span_id, patch)
    span = await store.spans.read(span_id)
    if span is None:
        raise NotFoundError("Span not found")
    return span


async def update_span(store: AnnotationStore, user: Principal | None, span_id: Id,
                      patch: PatchSpan) -> TagSpanWriteResult:
    """
    Updates offsets, type (approve: ``auto`` -> ``pos``, reject: -> ``neg``) or tag, then
    re-derives the span's (chunk, tag) pair and, on a tag change, the new pair. This runs
    for every patch, also offset-only, so saving a span again retries a chunk tag update
    that failed before. Changed offsets are validated like on creation; offsets that are
    not sent are not re-checked (approving an old span works whatever its offsets).
    """
    sid = access.parse_id(span_id, "Span")
    await _authorize_span_patch(store, user, [sid], patch)
    await _check_patched_ranges(store, [sid], patch)
    pairs = await _pairs_touched_by(store, [sid], patch)
    try:
        span = await _update_and_read(store, sid, patch)
    except Exception:
        # The update may have been partly applied (or applied despite a timeout).
        await store.chunk_tags.sync(pairs)
        raise
    return _write_result(span, await store.chunk_tags.sync(pairs))


async def bulk_update_spans(store: AnnotationStore, user: Principal | None, span_ids: list[Id],
                            patch: PatchSpan) -> BulkUpdateSpansResponse:
    """
    Applies the same patch to many spans (the AI panel's "approve/reject all selected").

    All spans must belong to one collection the user may annotate and the whole batch is
    validated before any write; otherwise nothing is updated. Updates are best effort:
    ``spans`` holds the updated spans and ``failed`` the spans that could not be updated
    (``update_span``) and the chunk tag updates that failed (``update_chunk_tags``).
    Chunk tags are re-derived once per touched pair after all span updates, also for
    spans whose update failed.
    """
    if not span_ids:
        return BulkUpdateSpansResponse(outcome=outcome_of(0, 0), spans=[])
    ids = list(dict.fromkeys(access.parse_id(s, "Span") for s in span_ids))
    await _authorize_span_patch(store, user, ids, patch)
    await _check_patched_ranges(store, ids, patch)
    pairs = await _pairs_touched_by(store, ids, patch)

    updated: list[schemas.TagSpan] = []
    failed: list[StepFailure] = []
    for sid, res in zip(ids, await _gather(*(_update_and_read(store, sid, patch) for sid in ids))):
        if isinstance(res, Exception):
            failed.append(step_failure("update_span", sid, res))
        else:
            updated.append(res)
    failed += await store.chunk_tags.sync(pairs)
    return BulkUpdateSpansResponse(outcome=outcome_of(len(updated), len(failed)),
                                   succeeded=[s.id for s in updated], failed=failed, spans=updated)


async def _gather(*aws):
    """``asyncio.gather`` returning exceptions, except cancellation and other non-``Exception`` errors."""
    results = await asyncio.gather(*aws, return_exceptions=True)
    for res in results:
        if isinstance(res, BaseException) and not isinstance(res, Exception):
            raise res
    return results


async def delete_span(store: AnnotationStore, user: Principal | None, span_id: Id) -> WriteResult:
    """
    Deletes a span, then removes chunk tag references no other span backs. ``outcome`` is
    ``partial`` when the span was deleted but the chunk tag could not be updated.
    """
    sid = access.parse_id(span_id, "Span")
    collection_id = await access.collection_of_spans(store.spans, store.tags, [sid])
    await access.require_annotation_edit(store.collections, user, collection_id)
    pairs = await _pairs_of_spans(store, [sid])
    try:
        await store.spans.delete(sid)
    except Exception:
        # A timed-out delete may still have been applied.
        await store.chunk_tags.sync(pairs)
        raise
    failed = await store.chunk_tags.sync(pairs)
    return WriteResult(outcome=outcome_of(1, len(failed)), succeeded=[str(sid)], failed=failed)


async def _delete_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                              document_id: Id, tag_ids: list[Id], span_type: schemas.SpanType) -> WriteResult:
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    document = await access.require_document_in_collection(store.collections, document_id, grant.collection_id)
    if not tag_ids:
        return WriteResult(outcome=outcome_of(0, 0))
    tags = await access.require_tags_in_collection(store.tags, tag_ids, grant.collection_id)

    spans = await store.spans.list_in_document(grant.collection_id, document, tags, span_type)
    deleted: list[str] = []
    failed: list[StepFailure] = []
    for sid in spans:
        try:
            await store.spans.delete(sid)
            deleted.append(str(sid))
        except Exception as e:
            failed.append(step_failure("delete_span", sid, e))
    # Re-derived after all deletions, also for spans whose deletion failed.
    tag_failures = await store.chunk_tags.sync(set().union(*spans.values()) if spans else set())
    return WriteResult(outcome=outcome_of(len(deleted), len(failed) + len(tag_failures)),
                       succeeded=deleted, failed=failed + tag_failures)


async def delete_approved_spans_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                            document_id: Id, tag_ids: list[Id]) -> WriteResult:
    """
    Deletes the approved (``pos``) spans of the tags on the document's chunks within the
    collection. Rejections (``neg``) and unresolved suggestions (``auto``) are kept.
    Best effort: ``succeeded`` lists the deleted spans; ``failed`` the spans that could
    not be deleted (``delete_span``) and failed chunk tag updates (``update_chunk_tags``).
    The spans are listed before deleting, so failing deletions cannot loop.
    """
    return await _delete_in_document(store, user, collection_id, document_id, tag_ids, schemas.SpanType.pos)


async def delete_suggestions_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                         document_id: Id, tag_ids: list[Id]) -> WriteResult:
    """Like ``delete_approved_spans_in_document`` for unresolved AI suggestions (``auto``)."""
    return await _delete_in_document(store, user, collection_id, document_id, tag_ids, schemas.SpanType.auto)
