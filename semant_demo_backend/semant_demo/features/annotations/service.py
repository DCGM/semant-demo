"""Annotation use cases: tag definitions and span annotations of a collection.

Every public function checks access itself (``features/user_collections/access.py``, ADR 0007)
before any other read or write, so callers outside HTTP get the same rules: reading
needs collection read access, span writes need annotation-edit access, tag definition
writes need tag-definition-edit access (owner and shared users for all three). Spans
belong to the collection of their tag and are placed only on chunks of that collection.
They are stored in that collection's annotation tenant (#327): span reads and writes
name the collection, it is authorized first, and only then is its tenant used, so span
ids of other collections are "not found". Each use of a tenant is recorded for the idle
deactivation (``store.activity``). ``user`` is the authenticated user or ``None``; ids
may be strings or UUIDs, malformed ids are "not found".

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
from dataclasses import dataclass, field
from uuid import UUID

from semant_demo.features.annotations.schemas import SpanType, TagSpan
from semant_demo.adapters.sql.tenant_activity import NoTenantActivity, TenantActivity
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag, ChunkTagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository, pair_of
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.core.errors import IncompleteWriteError, InvalidRequestError, NotFoundError
from semant_demo.features.annotations.offsets import InvalidSpanRange, check_span_range
from semant_demo.features.annotations.schemas import (
    AnnotationChunk, BulkUpdateSpansResponse, PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanWriteResult,
)
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import CollectionGrant, Principal
from semant_demo.core.outcomes import StepFailure, WriteResult, outcome_of

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
    activity: TenantActivity | NoTenantActivity = field(default_factory=NoTenantActivity)
    """Records each use of a collection's annotation tenant (idle deactivation)."""


async def use_tenant(store: AnnotationStore, grant: CollectionGrant) -> UUID:
    """The authorized collection whose annotation tenant the caller uses next, after
    recording the use."""
    await store.activity.touch(grant.collection_id)
    return grant.collection_id


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
    deletion fails too, the step is ``delete_unlinked_tag``, the message says the link
    failed and an unreachable tag may remain, and ``uncertain`` is set when either
    write timed out.
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
            cleanup = step_failure("delete_unlinked_tag", tag_id, cleanup_exc)
            raise IncompleteWriteError(
                f"The tag could not be added to the collection (step link_collection failed), and "
                f"removing it again failed: an unreachable tag {tag_id} may remain in storage. "
                f"Creating the tag again is safe.",
                step="delete_unlinked_tag", completed={"insert_tag": 1},
                uncertain=link.uncertain or cleanup.uncertain) from cleanup_exc
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
    grant = await access.require_tag_definition_edit(store.collections, user, collection_id)
    await store.tags.delete(access.parse_id(tag_id, "Tag"), await use_tenant(store, grant))


#########
# Spans #
#########

async def list_spans(store: AnnotationStore, user: Principal | None, collection_id: Id,
                     chunk_id: Id | None = None) -> list[TagSpan]:
    """The collection's spans, optionally only those starting on one chunk."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    chunk = access.parse_id(chunk_id, "Chunk") if chunk_id is not None else None
    return await store.spans.read_by_collection(await use_tenant(store, grant), chunk)


async def list_spans_by_chunks(store: AnnotationStore, user: Principal | None, collection_id: Id,
                               chunk_ids: list[Id] | None) -> dict[str, list[TagSpan]]:
    """The collection's spans starting on each chunk, keyed by the chunk ids as given."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    if not chunk_ids:
        return {}
    by_id = await store.spans.read_by_chunks(
        await use_tenant(store, grant), list(dict.fromkeys(access.parse_id(c, "Chunk") for c in chunk_ids)))
    return {str(c): by_id.get(str(access.parse_id(c, "Chunk")), []) for c in chunk_ids}


async def _check_range(store: AnnotationStore, chunk_id: UUID, start: int, end: int) -> AnnotationChunk:
    """The offsets must describe text of the chunk's document (``offsets.py``); returns the chunk."""
    anchor = await store.documents.read_chunk_text(chunk_id)
    if anchor is None:
        raise NotFoundError("Chunk not found")
    chunks = [anchor]
    while True:
        try:
            check_span_range(chunks, start, end)
            return anchor
        except InvalidSpanRange as e:
            if e.code != "past_end" or anchor.document_id is None:
                raise
            more = await store.documents.read_following_chunk_texts(
                anchor.document_id, chunks[-1].order, _FOLLOWING_CHUNKS_PAGE)
            if not more:
                raise
            chunks += more


def _write_result(span: TagSpan, failed: list[StepFailure]) -> TagSpanWriteResult:
    return TagSpanWriteResult(**span.model_dump(), outcome=outcome_of(1, len(failed)),
                              succeeded=[str(span.id)], failed=failed)


async def save_span(store: AnnotationStore, collection_id: UUID, document_id: UUID | None,
                    span: PostSpan) -> TagSpanWriteResult:
    """
    Stores a span in the collection's tenant (``document_id``: its chunk's document) and
    re-derives its chunk tag. No access or offset check: the caller has checked
    annotation-edit access to the collection, the tag and the chunk scope
    (``create_span``, or the AI suggestion run for validated provider proposals).
    """
    pairs = {ChunkTag.of(span.chunkId, span.tagId)}
    try:
        span_id = await store.spans.insert(collection_id, span, document_id)
    except Exception:
        await store.chunk_tags.sync(collection_id, pairs)
        raise
    failed = await store.chunk_tags.sync(collection_id, pairs)
    return _write_result(TagSpan(id=str(span_id), **span.model_dump()), failed)


async def create_span(store: AnnotationStore, user: Principal | None, span: PostSpan) -> TagSpanWriteResult:
    """
    Creates a span with the tag's collection as scope; the chunk must be in that
    collection and the offsets must describe text of its document (cross-chunk spans
    continue into the following consecutive chunks; see ``offsets.py``).
    ``outcome`` is ``partial`` when the span was saved but its chunk tag was not.
    """
    collection_id = await access.collection_of_tags(store.tags, [span.tagId])
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    [chunk_id] = await access.require_chunks_in_collection(store.collections, [span.chunkId], collection_id)
    anchor = await _check_range(store, chunk_id, span.start, span.end)
    return await save_span(store, await use_tenant(store, grant), anchor.document_id, span)


async def _authorize_span_patch(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                span_ids: list[Id], patch: PatchSpan) -> tuple[UUID, dict[UUID, TagSpan]]:
    """The authorized collection and its spans to patch, after every check."""
    if not patch.model_dump(exclude_none=True):
        raise InvalidRequestError("No fields provided for update")
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    spans = await access.require_spans_in_collection(store.spans, span_ids, grant.collection_id)
    if patch.tagId is not None:
        await access.require_tags_in_collection(store.tags, [patch.tagId], grant.collection_id)
    return await use_tenant(store, grant), spans


async def _check_patched_ranges(store: AnnotationStore, spans: dict[UUID, TagSpan], patch: PatchSpan) -> None:
    """Offsets resulting from an offset patch must be valid for every span; checked before any write."""
    if patch.start is None and patch.end is None:
        return
    for span in spans.values():
        await _check_range(store, access.parse_id(span.chunkId, "Chunk"),
                           span.start if patch.start is None else patch.start,
                           span.end if patch.end is None else patch.end)


def _pairs_touched_by(spans: dict[UUID, TagSpan], patch: PatchSpan) -> set[ChunkTag]:
    """The spans' current (chunk, tag) pairs and, on a tag change, the new tag's pairs."""
    pairs = {pair_of(span) for span in spans.values()}
    if patch.tagId is not None:
        pairs |= {ChunkTag.of(p.chunk_id, patch.tagId) for p in pairs}
    return pairs


async def _update_and_read(store: AnnotationStore, collection_id: UUID, span_id: UUID, patch: PatchSpan) -> TagSpan:
    await store.spans.update(collection_id, span_id, patch)
    span = await store.spans.read(collection_id, span_id)
    if span is None:
        raise NotFoundError("Span not found")
    return span


async def update_span(store: AnnotationStore, user: Principal | None, collection_id: Id, span_id: Id,
                      patch: PatchSpan) -> TagSpanWriteResult:
    """
    Updates offsets, type (approve: ``auto`` -> ``pos``, reject: -> ``neg``) or tag of a
    span of the collection, then re-derives the span's (chunk, tag) pair and, on a tag
    change, the new pair. This runs for every patch, also offset-only, so saving a span
    again retries a chunk tag update that failed before. Changed offsets are validated
    like on creation; offsets that are not sent are not re-checked (approving an old
    span works whatever its offsets).
    """
    cid, spans = await _authorize_span_patch(store, user, collection_id, [span_id], patch)
    await _check_patched_ranges(store, spans, patch)
    pairs = _pairs_touched_by(spans, patch)
    [sid] = spans
    try:
        span = await _update_and_read(store, cid, sid, patch)
    except Exception:
        # The update may have been partly applied (or applied despite a timeout).
        await store.chunk_tags.sync(cid, pairs)
        raise
    return _write_result(span, await store.chunk_tags.sync(cid, pairs))


async def bulk_update_spans(store: AnnotationStore, user: Principal | None, collection_id: Id, span_ids: list[Id],
                            patch: PatchSpan) -> BulkUpdateSpansResponse:
    """
    Applies the same patch to many spans of the collection (the AI panel's
    "approve/reject all selected").

    Every span must be a span of the collection, which the user may annotate, and the
    whole batch is validated before any write; otherwise nothing is updated. Updates are
    best effort: ``spans`` holds the updated spans and ``failed`` the spans that could not
    be updated (``update_span``) and the chunk tag updates that failed
    (``update_chunk_tags``). Chunk tags are re-derived once per touched pair after all
    span updates, also for spans whose update failed.
    """
    if not span_ids:
        return BulkUpdateSpansResponse(outcome=outcome_of(0, 0), spans=[])
    cid, spans = await _authorize_span_patch(store, user, collection_id, span_ids, patch)
    await _check_patched_ranges(store, spans, patch)
    pairs = _pairs_touched_by(spans, patch)

    updated: list[TagSpan] = []
    failed: list[StepFailure] = []
    ids = list(spans)
    for sid, res in zip(ids, await _gather(*(_update_and_read(store, cid, sid, patch) for sid in ids))):
        if isinstance(res, Exception):
            failed.append(step_failure("update_span", sid, res))
        else:
            updated.append(res)
    failed += await store.chunk_tags.sync(cid, pairs)
    return BulkUpdateSpansResponse(outcome=outcome_of(len(updated), len(failed)),
                                   succeeded=[s.id for s in updated], failed=failed, spans=updated)


async def _gather(*aws):
    """``asyncio.gather`` returning exceptions, except cancellation and other non-``Exception`` errors."""
    results = await asyncio.gather(*aws, return_exceptions=True)
    for res in results:
        if isinstance(res, BaseException) and not isinstance(res, Exception):
            raise res
    return results


async def delete_span(store: AnnotationStore, user: Principal | None, collection_id: Id, span_id: Id) -> WriteResult:
    """
    Deletes a span of the collection, then removes chunk tag references no other span
    backs. ``outcome`` is ``partial`` when the span was deleted but the chunk tag could
    not be updated.
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    spans = await access.require_spans_in_collection(store.spans, [span_id], grant.collection_id)
    cid = await use_tenant(store, grant)
    [(sid, span)] = spans.items()
    pairs = {pair_of(span)}
    try:
        await store.spans.delete(cid, sid)
    except Exception:
        # A timed-out delete may still have been applied.
        await store.chunk_tags.sync(cid, pairs)
        raise
    failed = await store.chunk_tags.sync(cid, pairs)
    return WriteResult(outcome=outcome_of(1, len(failed)), succeeded=[str(sid)], failed=failed)


async def _delete_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                              document_id: Id, tag_ids: list[Id], span_type: SpanType) -> WriteResult:
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    document = await access.require_document_in_collection(store.collections, document_id, grant.collection_id)
    if not tag_ids:
        return WriteResult(outcome=outcome_of(0, 0))
    tags = await access.require_tags_in_collection(store.tags, tag_ids, grant.collection_id)
    cid = await use_tenant(store, grant)

    spans = await store.spans.list_in_document(cid, document, tags, span_type)
    deleted: list[str] = []
    failed: list[StepFailure] = []
    for sid in spans:
        try:
            await store.spans.delete(cid, sid)
            deleted.append(str(sid))
        except Exception as e:
            failed.append(step_failure("delete_span", sid, e))
    # Re-derived after all deletions, also for spans whose deletion failed.
    tag_failures = await store.chunk_tags.sync(cid, set().union(*spans.values()) if spans else set())
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
    return await _delete_in_document(store, user, collection_id, document_id, tag_ids, SpanType.pos)


async def delete_suggestions_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                         document_id: Id, tag_ids: list[Id]) -> WriteResult:
    """Like ``delete_approved_spans_in_document`` for unresolved AI suggestions (``auto``)."""
    return await _delete_in_document(store, user, collection_id, document_id, tag_ids, SpanType.auto)
