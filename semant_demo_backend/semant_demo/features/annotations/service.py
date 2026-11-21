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

Spans are the only stored form of annotations: chunks hold no tag references derived
from them (ADR 0013).

Span creates and boundary (offset) edits also store the span's derived text, context
and positions in the same write and then its contextual vector (#328,
``enrichment.py``): the edit is kept when deriving or embedding fails, which is reported
as step ``derive_annotation`` / ``embed_annotation`` and recorded in the span's status.
Each boundary change increments the span's ``revision``; a vector is stored only while
the span still has the revision it was computed for (``SpanRepository.lock`` within the
process), and reads treat derived data of another revision as absent. Type, tag and AI
metadata changes keep the revision and never call the embedding provider. Saving the same
offsets again retries derived data that is not current.

Span types keep their meaning: ``pos`` a manual or approved annotation, ``auto`` an
unresolved AI suggestion, ``neg`` a rejected suggestion kept as a negative example.
Approving or rejecting is a type change (``auto`` -> ``pos`` / ``neg``).

Provenance and edit versions (#460, once the collection holds them,
``SpanRepository.provenance``): a create records its ``origin`` (``ai`` with the run's
``aiRunId`` for suggestions, else ``manual``), actor and time; every span write (type,
tag, offsets) increments ``editVersion`` and records the last edit, an approve or reject
also the review (a change back to ``auto``, an undo of #461, clears it). ``origin``, ``aiRunId``, ``reason`` and ``confidence`` are never
changed. A write or delete that names the version its caller expects reads the span
under its lock and is refused (``EditConflictError``; per item ``edit_conflict`` in
batches) when the span was written since, unless it already is as the write asks (then
it counts as done and nothing is written: a retry of a write that landed). The lock is
per process: across backend processes a conflict is detectable but not atomic (ADR 0009).
"""
import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from functools import total_ordering
from typing import NamedTuple, Protocol
from datetime import datetime, timezone
from uuid import UUID

from semant_demo.features.annotations.schemas import (
    NearNeighbor, ProximityCoverage,
    MAX_ATTRIBUTE_FILTER_VALUES, MAX_ATTRIBUTE_FILTERS, MAX_RESOLVED_IDS, MAX_REVIEW_BATCH, AnnotatedDocument, AnnotationCounts, AnnotationIds, AnnotationIdsRequest, AnnotationListRow,
    AnnotationFilters, AnnotationOrigin, AnnotationPage, AnnotationQuery, AnnotationRestoreRequest, AnnotationReviewRequest,
    AnnotationReviewResult, AnnotationRow, AnnotationValues, AnnotationSort,
    MAX_TOP_K, AnnotationRanking, AnnotationResultSet, HYBRID_ALPHA, ResultKind, RetrievalMode, HYBRID_FIELDS, VectorCoverage, VectorRanking, EnrichmentStatus, ReviewAction, SpanType, TagSpan, TextScope, TextStatus, VectorStatus,
)
from semant_demo.features.documents.criteria import Condition, document_conditions
from semant_demo.features.documents.schemas import Document
from semant_demo.adapters.sql.tenant_activity import NoTenantActivity, TenantActivity
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.core.errors import (
    EditConflictError, IncompleteWriteError, InvalidRequestError, NotFoundError, ServiceUnavailableError,
)
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import proximity
from semant_demo.features.annotations.collation import NO_SORT_KEYS, sort_key_version, sort_keys
from semant_demo.features.annotations.derivation import DERIVATION_VERSION, DerivedText, MissingChunkPositions, derive
from semant_demo.features.annotations.enrichment import Enrichment, text_current, vector_current
from semant_demo.features.annotations.offsets import InvalidSpanRange, check_span_range
from semant_demo.features.annotations.source import ChunkSource, InvalidDocumentChunks
from semant_demo.features.annotations.schemas import (
    AnnotationChunk, BulkUpdateSpansResponse, PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanWriteResult,
)
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import CollectionGrant, Principal
from semant_demo.core.outcomes import StepFailure, WriteResult, outcome_of

logger = logging.getLogger(__name__)

Id = str | UUID


@dataclass
class AnnotationStore:
    """The repositories annotation use cases read and write (one Weaviate client)."""
    collections: UserCollectionRepository
    tags: TagRepository
    spans: SpanRepository
    documents: DocumentRepository
    activity: TenantActivity | NoTenantActivity = field(default_factory=NoTenantActivity)
    """Records each use of a collection's annotation tenant (idle deactivation)."""
    enrichment: Enrichment = field(default_factory=Enrichment.disabled)
    """Which derived data span writes store (#328)."""


async def use_tenant(store: AnnotationStore, grant: CollectionGrant) -> UUID:
    """The authorized collection whose annotation tenant the caller uses next, after
    recording the use."""
    await store.activity.touch(grant.collection_id)
    return grant.collection_id


@dataclass(frozen=True)
class Actor:
    """Whom span writes are recorded for (#460): the user, and the AI suggestion run that
    proposed the spans it creates."""
    user_id: UUID
    ai_run_id: UUID | None = None

    @classmethod
    def of(cls, user: Principal) -> "Actor":
        return cls(user.id)


EDIT_CONFLICT = "Changed by someone else since it was loaded; nothing was saved."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _created(store: AnnotationStore, actor: Actor | None) -> dict | None:
    """The provenance of a new span, or None when the collection does not hold it."""
    if not store.spans.provenance or actor is None:
        return None
    props: dict = {"origin": (AnnotationOrigin.ai if actor.ai_run_id else AnnotationOrigin.manual).value,
                   "createdBy": actor.user_id, "createdAt": _now(), "editVersion": 0}
    if actor.ai_run_id is not None:
        props["aiRunId"] = actor.ai_run_id
    return props


def _edited(current: TagSpan, patch: PatchSpan, actor: Actor) -> dict:
    """The provenance a patch of ``current`` records: the next version and the last edit,
    and the review when it approves or rejects (changes the type to ``pos`` / ``neg``); a
    change back to ``auto`` (an undone review, #461) clears the review."""
    now = _now()
    props: dict = {"editVersion": current.editVersion + 1, "lastEditedBy": actor.user_id, "lastEditedAt": now}
    if patch.type is not None and patch.type != current.type:
        reviewed = patch.type in (SpanType.pos, SpanType.neg)
        props |= {"reviewedBy": actor.user_id if reviewed else None, "reviewedAt": now if reviewed else None}
    return props


def _already(current: TagSpan, patch: PatchSpan) -> bool:
    """``current`` already has every value the patch sets."""
    return ((patch.start is None or patch.start == current.start) and (patch.end is None or patch.end == current.end)
            and (patch.type is None or patch.type == current.type)
            and (patch.tagId is None or str(access.parse_id(patch.tagId, "Tag")) == current.tagId)
            and (patch.chunkId is None or str(access.parse_id(patch.chunkId, "Chunk")) == current.chunkId))


def _conflict(current: TagSpan) -> EditConflictError:
    return EditConflictError(EDIT_CONFLICT, current.model_dump(mode="json"))


def _conflict_failure(span_id: UUID) -> StepFailure:
    return StepFailure(item_id=str(span_id), step="edit_conflict", message=EDIT_CONFLICT)


def _missing_failure(span_id: UUID) -> StepFailure:
    return StepFailure(item_id=str(span_id), step="find_annotation",
                       message="No such annotation in this collection; it may have been deleted.")


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


class TagReferences(Protocol):
    """Definitions outside this feature that list tags by id (the collection's attributes,
    ``adapters/sql/attributes.py``), so that deleting a tag can remove it from them."""

    async def remove_tag(self, collection_id: UUID, tag_id: UUID) -> list[str]: ...


async def delete_tag(store: AnnotationStore, user: Principal | None, tag_id: Id,
                     references: TagReferences) -> None:
    """
    Deletes the tag with its spans, then removes its id from the
    attributes that list it (#508; ``all_tags`` is never changed, so an attribute that loses
    its last tag applies to no tag). A failed step raises ``IncompleteWriteError`` naming it
    and the completed steps. Deleting again continues a failed cascade; the removal goes last
    so that a tag that still exists is never taken off its attributes. When only the removal
    fails, the tag is gone and its id stays listed, shown as a deleted tag that can be removed
    from the attribute by hand.
    """
    collection_id = await access.collection_of_tags(store.tags, [tag_id])
    grant = await access.require_tag_definition_edit(store.collections, user, collection_id)
    tag = access.parse_id(tag_id, "Tag")
    await store.tags.delete(tag, await use_tenant(store, grant))
    try:
        await references.remove_tag(grant.collection_id, tag)
    except Exception as exc:
        logger.warning("Removing deleted tag %s from the attributes of collection %s failed: %s",
                       tag, grant.collection_id, type(exc).__name__)
        raise IncompleteWriteError(
            f"The tag was deleted, but removing it from the attributes that list it stopped at step "
            f"remove_from_attributes ({type(exc).__name__}). Those attributes show it as a deleted tag; "
            "remove it there when editing their tags.",
            step="remove_from_attributes", completed={"delete_tag": 1}) from exc


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


async def _check_range(source: ChunkSource, chunk_id: UUID, start: int, end: int) -> AnnotationChunk:
    """The offsets must describe text of the chunk's document (``offsets.py``); returns the
    chunk. Reads the anchor and the chunks the span covers (``source.py``)."""
    anchor = await source.chunk(chunk_id)
    if anchor is None:
        raise NotFoundError("Chunk not found")
    check_span_range(await source.covering(anchor, end), start, end)
    return anchor


def _write_result(span: TagSpan, failed: list[StepFailure]) -> TagSpanWriteResult:
    return TagSpanWriteResult(**span.model_dump(), outcome=outcome_of(1, len(failed)),
                              succeeded=[str(span.id)], failed=failed)


async def save_span(store: AnnotationStore, collection_id: UUID, document_id: UUID | None,
                    span: PostSpan, source: ChunkSource | None = None, *,
                    actor: Actor | None = None) -> TagSpanWriteResult:
    """
    Stores a span in the collection's tenant (``document_id``: its chunk's document) with
    its derived fields and the provenance of ``actor``, then stores its contextual vector.
    No access or offset check: the caller has checked annotation-edit access to the
    collection, the tag and the chunk scope (``create_span``, or the AI suggestion run for
    validated provider proposals). ``source`` keeps the chunks
    read across the saves of one run (source text is immutable).
    """
    refresh = None
    if store.enrichment.derived:
        refresh = await derive_refresh(store, span.chunkId, span.start, span.end, 1, source)
    created = _created(store, actor)
    span_id = await store.spans.insert(collection_id, span, document_id,
                                       refresh.properties(reset_vector=True) if refresh else None,
                                       created)
    failed: list[StepFailure] = []
    if refresh is not None:
        failed += refresh.failures + await refresh_vector(store, collection_id, span_id, refresh)
    return _write_result(TagSpan(id=str(span_id), **span.model_dump(),
                                 createdAt=created["createdAt"] if created else None), failed)


async def create_span(store: AnnotationStore, user: Principal | None, span: PostSpan) -> TagSpanWriteResult:
    """
    Creates a span with the tag's collection as scope; the chunk must be in that
    collection and the offsets must describe text of its document (cross-chunk spans
    continue into the following consecutive chunks; see ``offsets.py``).
    ``outcome`` is ``partial`` when the span was saved but its derived data was not.
    """
    collection_id = await access.collection_of_tags(store.tags, [span.tagId])
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    [chunk_id] = await access.require_chunks_in_collection(store.collections, [span.chunkId], collection_id)
    source = ChunkSource(store.documents)
    anchor = await _check_range(source, chunk_id, span.start, span.end)
    return await save_span(store, await use_tenant(store, grant), anchor.document_id, span, source,
                           actor=Actor.of(user))


async def _authorize_span_patch(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                span_ids: list[Id], patch: PatchSpan) -> tuple[UUID, dict[UUID, TagSpan]]:
    """The authorized collection and its spans to patch, after every check."""
    if not patch.model_dump(exclude_none=True):
        raise InvalidRequestError("No fields provided for update")
    if patch.chunkId is not None and (patch.start is None or patch.end is None):
        raise InvalidRequestError("Moving a span to another chunk needs its start and end in that chunk")
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    spans = await access.require_spans_in_collection(store.spans, span_ids, grant.collection_id)
    if patch.tagId is not None:
        await access.require_tags_in_collection(store.tags, [patch.tagId], grant.collection_id)
    if patch.chunkId is not None:
        await access.require_chunks_in_collection(store.collections, [patch.chunkId], grant.collection_id)
    return await use_tenant(store, grant), spans


async def _check_patched_ranges(store: AnnotationStore, spans: dict[UUID, TagSpan], patch: PatchSpan) -> None:
    """Offsets resulting from an offset patch must be valid for every span (on the chunk it
    moves to, which must be of the same document); checked before any write."""
    if patch.start is None and patch.end is None:
        return
    source = ChunkSource(store.documents)
    for span in spans.values():
        chunk_id = access.parse_id(patch.chunkId or span.chunkId, "Chunk")
        anchor = await _check_range(source, chunk_id,
                                    span.start if patch.start is None else patch.start,
                                    span.end if patch.end is None else patch.end)
        if str(chunk_id) != span.chunkId:
            current = await source.chunk(access.parse_id(span.chunkId, "Chunk"))
            if current is None or current.document_id != anchor.document_id:
                raise InvalidRequestError("A span can only move to another chunk of its document")


class _Updated(NamedTuple):
    """One span update: the span read back, the vector to store next, the failures of a
    move's ``text_chunk`` reference, and whether this update wrote the span (false when it
    already was as the patch asks, e.g. another writer made the same change first)."""
    span: TagSpan
    refresh: "Refresh | None"
    failures: list[StepFailure]
    written: bool


async def _update_and_read(store: AnnotationStore, collection_id: UUID, span_id: UUID, patch: PatchSpan,
                           actor: Actor, expected: int | None = None) -> _Updated:
    """Applies the patch (with the span's new derived fields when its offsets are sent, and
    its provenance) and reads the span back.
    ``expected``: the version the caller knows; a span written since raises
    ``EditConflictError`` unless it already is as the patch asks (then nothing is written).
    Under the span's lock the span is read back before the lock is released, so the version
    returned is the one this write saved, never a later writer's; a move also replaces its
    reference there, so overlapping moves leave it at the chunk the span is on."""
    offsets = store.enrichment.derived and (patch.start is not None or patch.end is not None)
    if not (store.spans.provenance or offsets or patch.chunkId is not None):
        await store.spans.update(collection_id, span_id, patch)
        return _Updated(await _read_back(store, collection_id, span_id), None, [], True)
    async with store.spans.lock(span_id):
        provenance = None
        if store.spans.provenance:
            current = await store.spans.read(collection_id, span_id)
            if current is None:
                raise NotFoundError("Span not found")
            if expected is not None and current.editVersion != expected:
                if _already(current, patch):
                    # A retry of a move whose answer was lost also repairs its reference.
                    return _Updated(current, None, await _replace_anchor_reference(store, collection_id, span_id, patch),
                                    False)
                raise _conflict(current)
            provenance = _edited(current, patch, actor)
        refresh = None
        if offsets:
            refresh = await _patch_with_derived(store, collection_id, span_id, patch, provenance)
        else:
            await store.spans.update(collection_id, span_id, patch, provenance=provenance)
        failed = await _replace_anchor_reference(store, collection_id, span_id, patch)
        return _Updated(await _read_back(store, collection_id, span_id), refresh, failed, True)


async def _read_back(store: AnnotationStore, collection_id: UUID, span_id: UUID) -> TagSpan:
    span = await store.spans.read(collection_id, span_id)
    if span is None:
        raise NotFoundError("Span not found")
    return span


async def _patch_with_derived(store: AnnotationStore, collection_id: UUID, span_id: UUID,
                              patch: PatchSpan, provenance: dict | None = None) -> "Refresh | None":
    """An offset patch (under the span's lock): a changed range is a new revision with new
    derived fields; the same range re-derives only what is not current (a retry)."""
    row = await store.spans.read_row(collection_id, span_id)
    if row is None:
        raise NotFoundError("Span not found")
    start = row.start if patch.start is None else patch.start
    end = row.end if patch.end is None else patch.end
    chunk_id = access.parse_id(patch.chunkId, "Chunk") if patch.chunkId is not None else row.chunkId
    moved = (chunk_id, start, end) != (row.chunkId, row.start, row.end)
    vector = store.enrichment.vector
    stale_vector = vector is not None and not vector_current(row, vector.id)
    # Sort keys of another collator alone are left to the backfill: re-deriving here would re-embed.
    if not moved and text_current(row) and not stale_vector:
        await store.spans.update(collection_id, span_id, patch, provenance=provenance)
        return None
    # Re-derived text (also under a changed policy) invalidates the vector embedded from the old one.
    refresh = await derive_refresh(store, chunk_id, start, end, (row.revision or 0) + moved)
    await store.spans.update(collection_id, span_id, patch, refresh.properties(reset_vector=True), provenance)
    return refresh


async def update_span(store: AnnotationStore, user: Principal | None, collection_id: Id, span_id: Id,
                      patch: PatchSpan, expected_version: int | None = None) -> TagSpanWriteResult:
    """
    Updates offsets, type (approve: ``auto`` -> ``pos``, reject: -> ``neg``) or tag of a
    span of the collection, or moves it to another chunk of its document in the collection
    (``chunkId`` with the offsets counted from there; the span keeps its id and provenance).
    Saving the same offsets again retries derived data that is not current. Changed offsets
    are validated like on creation; offsets that are not sent are not re-checked (approving an old
    span works whatever its offsets). ``expected_version``: the span's ``editVersion`` as
    the caller knows it; ``EditConflictError`` (nothing written) when it was written since.
    """
    cid, spans = await _authorize_span_patch(store, user, collection_id, [span_id], patch)
    await _check_patched_ranges(store, spans, patch)
    [sid] = spans
    span, refresh, failed, _ = await _update_and_read(store, cid, sid, patch, Actor.of(user), expected_version)
    if refresh is not None:
        failed += refresh.failures + await refresh_vector(store, cid, sid, refresh)
    return _write_result(span, failed)


async def _replace_anchor_reference(store: AnnotationStore, cid: UUID, span_id: UUID, patch: PatchSpan
                                    ) -> list[StepFailure]:
    """Points a moved span's ``text_chunk`` reference (the statistics' collection filter) at
    the chunk of the move, under the span's lock, best effort: also when the move was
    already applied, so saving the move again repairs a failure (``update_chunk_reference``).
    Nothing for a patch that moves nothing."""
    if patch.chunkId is None:
        return []
    try:
        await store.spans.replace_anchor_reference(cid, span_id, access.parse_id(patch.chunkId, "Chunk"))
    except Exception as e:
        return [step_failure("update_chunk_reference", span_id, e)]
    return []


SPAN_UPDATE_CONCURRENCY = 8
"""At most this many span updates of one request run at a time; clients send large
selections in batches (``AiAssistPanel``)."""


async def bulk_update_spans(store: AnnotationStore, user: Principal | None, collection_id: Id, span_ids: list[Id],
                            patch: PatchSpan, expected_versions: dict[str, int] | None = None
                            ) -> BulkUpdateSpansResponse:
    """
    Applies the same patch to many spans of the collection (the AI panel's
    "approve/reject all selected").

    Every span must be a span of the collection, which the user may annotate, and the
    whole batch is validated before any write; otherwise nothing is updated. Updates are
    best effort: ``spans`` holds the updated spans and ``failed`` the spans that could not
    be updated (``update_span``), those written by someone else since their version in
    ``expected_versions`` (``edit_conflict``, their current state in ``conflicts``) and
    failed best-effort steps of updated spans (derived data, vectors, a move's reference).
    """
    if patch.chunkId is not None:
        raise InvalidRequestError("Spans are moved to another chunk one at a time")
    if not span_ids:
        return BulkUpdateSpansResponse(outcome=outcome_of(0, 0), spans=[])
    cid, spans = await _authorize_span_patch(store, user, collection_id, span_ids, patch)
    await _check_patched_ranges(store, spans, patch)
    expected = {access.parse_id(i, "Span"): v for i, v in (expected_versions or {}).items()}
    updated, failed, conflicts, _ = await _update_spans(store, cid, spans, dict.fromkeys(spans, patch),
                                                        Actor.of(user), expected)
    return BulkUpdateSpansResponse(outcome=outcome_of(len(updated), len(failed)),
                                   succeeded=[s.id for s in updated], failed=failed, spans=updated,
                                   conflicts=conflicts)


async def _update_spans(store: AnnotationStore, cid: UUID, spans: dict[UUID, TagSpan],
                        patches: dict[UUID, PatchSpan], actor: Actor, expected: dict[UUID, int] | None = None
                        ) -> tuple[list[TagSpan], list[StepFailure], list[TagSpan], set[UUID]]:
    """Applies each span's checked patch concurrently (each checked against its version in
    ``expected``), then stores new vectors; returns the updated spans in request order, the
    failures, the current state of the conflicting spans and the ids this call wrote (not
    those it found already as asked)."""
    updated: list[TagSpan] = []
    failed: list[StepFailure] = []
    conflicts: list[TagSpan] = []
    written: set[UUID] = set()
    refreshes: dict[UUID, Refresh] = {}
    ids = list(spans)
    expected = expected or {}
    # Bounded: a bulk approval of over a thousand suggestions must not open that many
    # concurrent storage requests (#464).
    sem = asyncio.Semaphore(SPAN_UPDATE_CONCURRENCY)

    async def bounded(sid: UUID):
        async with sem:
            return await _update_and_read(store, cid, sid, patches[sid], actor, expected.get(sid))

    results = await _gather(*(bounded(sid) for sid in ids))
    for sid, res in zip(ids, results):
        if isinstance(res, EditConflictError):
            failed.append(_conflict_failure(sid))
            conflicts.append(TagSpan.model_validate(res.current))
        elif isinstance(res, NotFoundError):
            failed.append(_missing_failure(sid))
        elif isinstance(res, Exception):
            failed.append(step_failure("update_span", sid, res))
        else:
            updated.append(res.span)
            failed += res.failures
            if res.written:
                written.add(sid)
            if res.refresh is not None:
                refreshes[sid] = res.refresh
    for sid, refresh in refreshes.items():
        failed += refresh.failures + await refresh_vector(store, cid, sid, refresh)
    return updated, failed, conflicts, written


@dataclass
class Refresh:
    """Derived fields computed for one revision of a span, and what is still to store
    (also used by the backfill, ``backfill.py``)."""
    revision: int
    derived: DerivedText | None
    status: EnrichmentStatus
    failures: list[StepFailure] = field(default_factory=list)
    needs_vector: bool = True
    vector_stored: bool = False
    """Set by ``refresh_vector`` when the vector was written."""
    sort_keys: bool = False
    """The collection holds the sort keys (#666): they are written with the text."""

    def properties(self, *, reset_vector: bool, with_revision: bool = True) -> dict:
        """The derived fields (when derived) and their state; with ``reset_vector`` the
        vector is marked pending. ``with_revision`` adds the revision itself, which only
        the span's own write (create, boundary edit) may set: a write of derived data
        alone must never move the revision back."""
        props: dict = {"enrichmentStatus": self.status.value, "enrichedRevision": self.revision,
                       "derivationVersion": DERIVATION_VERSION}
        if with_revision:
            props["revision"] = self.revision
        if reset_vector:
            props["vectorStatus"] = VectorStatus.pending.value
        d = self.derived
        if d is None:
            # Text of an earlier revision or policy must not stay searchable or sortable (#329).
            props |= {"text": "", "leftContext": "", "rightContext": ""}
            if self.sort_keys:
                props |= NO_SORT_KEYS
        else:
            props |= {"text": d.text, "leftContext": d.left_context, "rightContext": d.right_context,
                      "documentStartChar": d.start_char,
                      "documentEndChar": d.end_char, "documentStartWord": d.start_word,
                      "documentEndWord": d.end_word}
            if self.sort_keys:
                props |= sort_keys(d.text, d.left_context, d.right_context).properties(self.revision)
        return props


def _derivation_failure(chunk_id: Id, exc: Exception) -> StepFailure:
    if not isinstance(exc, (MissingChunkPositions, InvalidDocumentChunks)):
        return step_failure("derive_annotation", chunk_id, exc)
    logger.warning("Deriving the annotation on chunk %s failed: %s", chunk_id, exc)
    what = ("chunk positions are missing or inconsistent (#463)" if isinstance(exc, MissingChunkPositions)
            else "the document's chunk orders are not consecutive")
    return StepFailure(item_id=str(chunk_id), step="derive_annotation", message=f"{type(exc).__name__}: {what}")


async def derive_refresh(store: AnnotationStore, chunk_id: Id, start: int, end: int, revision: int,
                         source: ChunkSource | None = None) -> Refresh:
    """The derived fields of a span from its anchor chunk and the chunks around it
    (``source.py``; ``source``: the chunks already read, filled further). A failed read, a
    chunk without a stored position or a document whose chunk orders are not consecutive is
    a ``derive_annotation`` failure (never a reason to read the whole document); offsets
    that describe no text (or a missing anchor chunk or document) are ``invalid``."""
    source = source or ChunkSource(store.documents)
    keys = store.enrichment.sort_keys
    try:
        anchor = await source.chunk(access.parse_id(chunk_id, "Chunk"))
        if anchor is None or anchor.document_id is None:
            return Refresh(revision, None, EnrichmentStatus.invalid, sort_keys=keys)
        derived = derive(await source.span_source(anchor, start, end), start, end)
        return Refresh(revision, derived, EnrichmentStatus.ready, sort_keys=keys)
    except InvalidSpanRange:
        return Refresh(revision, None, EnrichmentStatus.invalid, sort_keys=keys)
    except Exception as e:
        return Refresh(revision, None, EnrichmentStatus.failed, [_derivation_failure(chunk_id, e)], sort_keys=keys)


async def write_if_revision(store: AnnotationStore, collection_id: UUID, span_id: UUID, revision: int,
                            properties: dict, vector: tuple[str, list[float]] | None = None,
                            *, unless_vector: str | None = None) -> bool:
    """Writes derived data computed for ``revision`` unless the span has another revision
    by now (then the write is dropped: a newer edit has its own derivation), or, with
    ``unless_vector``, already has a current vector of that configuration."""
    async with store.spans.lock(span_id):
        row = await store.spans.read_row(collection_id, span_id)
        if row is None or (row.revision or 0) != revision:
            return False
        if unless_vector is not None and vector_current(row, unless_vector):
            return False
        await store.spans.write_derived(collection_id, span_id, properties, vector)
        return True


def _embedding_failure(span_id: UUID, exc: Exception) -> StepFailure:
    logger.warning("Embedding annotation %s failed: %s", span_id, type(exc).__name__)
    return StepFailure(item_id=str(span_id), step="embed_annotation",
                       message=f"{type(exc).__name__}: the contextual vector could not be computed")


async def refresh_vector(store: AnnotationStore, collection_id: UUID, span_id: UUID,
                         refresh: Refresh) -> list[StepFailure]:
    """Embeds the span's derived text and stores the vector for its revision; returns an
    ``embed_annotation`` failure when that fails (the span is then marked ``failed``)."""
    vector = store.enrichment.vector
    if vector is None or refresh.derived is None or not refresh.needs_vector:
        return []
    state = {"vectorRevision": refresh.revision, "vectorConfig": vector.id}
    try:
        embedding = await vector.embed(refresh.derived)
    except Exception as e:
        failure = _embedding_failure(span_id, e)
        try:
            await write_if_revision(store, collection_id, span_id, refresh.revision,
                                    state | {"vectorStatus": VectorStatus.failed.value}, unless_vector=vector.id)
        except Exception as mark:
            logger.warning("Marking the vector of annotation %s failed: %s", span_id, type(mark).__name__)
        return [failure]
    try:
        refresh.vector_stored = await write_if_revision(
            store, collection_id, span_id, refresh.revision, state | {"vectorStatus": VectorStatus.ready.value},
            (vector.target_vector, embedding))
    except Exception as e:
        return [step_failure("embed_annotation", span_id, e)]
    return []


async def _gather(*aws):
    """``asyncio.gather`` returning exceptions, except cancellation and other non-``Exception`` errors."""
    results = await asyncio.gather(*aws, return_exceptions=True)
    for res in results:
        if isinstance(res, BaseException) and not isinstance(res, Exception):
            raise res
    return results


async def _delete_checked(store: AnnotationStore, cid: UUID, span_id: UUID, expected: int | None) -> None:
    """Deletes the span; with ``expected``, under its lock and only while it has that
    version (``EditConflictError`` otherwise, ``NotFoundError`` when it is gone)."""
    if expected is None or not store.spans.provenance:
        await store.spans.delete(cid, span_id)
        return
    async with store.spans.lock(span_id):
        current = await store.spans.read(cid, span_id)
        if current is None:
            raise NotFoundError("Span not found")
        if current.editVersion != expected:
            raise _conflict(current)
        await store.spans.delete(cid, span_id)


async def delete_span(store: AnnotationStore, user: Principal | None, collection_id: Id, span_id: Id,
                      expected_version: int | None = None) -> WriteResult:
    """
    Deletes a span of the collection. ``expected_version``: the span's ``editVersion`` as
    the caller knows it; ``EditConflictError`` (nothing deleted) when it was written since.
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    spans = await access.require_spans_in_collection(store.spans, [span_id], grant.collection_id)
    cid = await use_tenant(store, grant)
    [sid] = spans
    await _delete_checked(store, cid, sid, expected_version)
    return WriteResult(outcome=outcome_of(1, 0), succeeded=[str(sid)])


async def _delete_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                              document_id: Id, tag_ids: list[Id], span_type: SpanType) -> WriteResult:
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    document = await access.require_document_in_collection(store.collections, document_id, grant.collection_id)
    if not tag_ids:
        return WriteResult(outcome=outcome_of(0, 0))
    tags = await access.require_tags_in_collection(store.tags, tag_ids, grant.collection_id)
    cid = await use_tenant(store, grant)

    deleted, failed, _ = await _delete_spans(
        store, cid, await store.spans.list_in_document(cid, document, tags, span_type))
    return WriteResult(outcome=outcome_of(len(deleted), len(failed)), succeeded=deleted, failed=failed)


async def _delete_spans(store: AnnotationStore, cid: UUID, span_ids: list[UUID],
                        expected: dict[UUID, int] | None = None
                        ) -> tuple[list[str], list[StepFailure], dict[UUID, int]]:
    """Deletes the listed spans one by one (each checked against its version in
    ``expected``), keeping going after a failure; returns the deleted ids, the failures
    and the current versions of the conflicting spans."""
    deleted: list[str] = []
    failed: list[StepFailure] = []
    conflicts: dict[UUID, int] = {}
    for sid in span_ids:
        try:
            await _delete_checked(store, cid, sid, (expected or {}).get(sid))
            deleted.append(str(sid))
        except EditConflictError as e:
            failed.append(_conflict_failure(sid))
            conflicts[sid] = e.current.get("editVersion", 0)
        except NotFoundError:
            failed.append(_missing_failure(sid))
        except Exception as e:
            failed.append(step_failure("delete_span", sid, e))
    return deleted, failed, conflicts


async def delete_approved_spans_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                            document_id: Id, tag_ids: list[Id]) -> WriteResult:
    """
    Deletes the approved (``pos``) spans of the tags on the document's chunks within the
    collection. Rejections (``neg``) and unresolved suggestions (``auto``) are kept.
    Best effort: ``succeeded`` lists the deleted spans; ``failed`` the spans that could
    not be deleted (``delete_span``).
    The spans are listed before deleting, so failing deletions cannot loop.
    """
    return await _delete_in_document(store, user, collection_id, document_id, tag_ids, SpanType.pos)


async def delete_suggestions_in_document(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                         document_id: Id, tag_ids: list[Id]) -> WriteResult:
    """Like ``delete_approved_spans_in_document`` for unresolved AI suggestions (``auto``)."""
    return await _delete_in_document(store, user, collection_id, document_id, tag_ids, SpanType.auto)


async def delete_selected_suggestions_in_document(
        store: AnnotationStore, user: Principal | None, collection_id: Id, document_id: Id,
        span_ids: list[Id], expected_versions: dict[str, int] | None = None) -> WriteResult:
    """Best-effort id-scoped removal. Never remove a reviewed span or one of another document.

    Check its type, chunk and optional edit version under the per-span write lock.
    The lock is process-local, matching the existing versioned edit contract (#460).
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    document = await access.require_document_in_collection(store.collections, document_id, grant.collection_id)
    ids = list(dict.fromkeys(access.parse_id(sid, "Span") for sid in span_ids))
    if not ids:
        return WriteResult(outcome=outcome_of(0, 0))
    cid = await use_tenant(store, grant)
    known = await store.spans.read_many(cid, ids)
    chunks = list({UUID(span.chunkId) for span in known.values()})
    allowed_chunks = await store.collections.chunk_ids_in_collection(chunks, cid, document)
    expected = {access.parse_id(sid, "Span"): version for sid, version in (expected_versions or {}).items()}

    deleted: list[str] = []
    failed: list[StepFailure] = []
    for sid in ids:
        try:
            async with store.spans.lock(sid):
                current = await store.spans.read(cid, sid)
                if current is None or UUID(current.chunkId) not in allowed_chunks:
                    raise NotFoundError("Suggestion not found in this document")
                if store.spans.provenance and sid in expected and current.editVersion != expected[sid]:
                    raise _conflict(current)
                if current.type != SpanType.auto:
                    raise InvalidRequestError("Only pending AI suggestions can be deleted")
                await store.spans.delete(cid, sid)
                deleted.append(str(sid))
        except EditConflictError:
            failed.append(_conflict_failure(sid))
        except NotFoundError:
            failed.append(_missing_failure(sid))
        except InvalidRequestError:
            failed.append(StepFailure(item_id=str(sid), step="check_type",
                                      message="The annotation is no longer a pending suggestion."))
        except Exception as error:
            failed.append(step_failure("delete_span", sid, error))
    return WriteResult(outcome=outcome_of(len(deleted), len(failed)), succeeded=deleted, failed=failed)


#############################
# Annotation rows (#328)    #
#############################

_MAX_ROWS = 1000
_HIDDEN_WHEN_STALE = ("text", "leftContext", "rightContext", "documentStartChar",
                      "documentEndChar", "documentStartWord", "documentEndWord")


def _check_limit(limit: int, offset: int = 0) -> None:
    if not 1 <= limit <= _MAX_ROWS or offset < 0:
        raise InvalidRequestError(f"limit must be between 1 and {_MAX_ROWS} and offset not negative")


async def _visible(store: AnnotationStore, rows: list[AnnotationRow]) -> list[AnnotationRow]:
    """Rows without derived fields that are not current, with their document's title and
    year (one read per page of rows)."""
    documents = await store.documents.read_many(list({r.documentId for r in rows if r.documentId is not None}))
    result = []
    for row in rows:
        update: dict = {} if text_current(row) else dict.fromkeys(_HIDDEN_WHEN_STALE)
        document = documents.get(row.documentId) if row.documentId is not None else None
        if document is not None:
            update |= {"documentTitle": document.title, "documentYear": document.yearIssued}
        result.append(row.model_copy(update=update))
    return result


async def list_annotation_rows(store: AnnotationStore, user: Principal | None, collection_id: Id, *,
                               tag_ids: list[Id] | None = None, document_id: Id | None = None,
                               limit: int = 100, offset: int = 0) -> list[AnnotationRow]:
    """
    One page of the collection's annotations as concordance rows: stored text, context
    and positions, read from the annotations only (no source chunks). A row whose derived
    data is missing or belongs to an older revision has none (``text`` is ``None``).
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    _check_limit(limit, offset)
    tags = [access.parse_id(t, "Tag") for t in tag_ids] if tag_ids else None
    document = access.parse_id(document_id, "Document") if document_id is not None else None
    rows = await store.spans.read_rows(await use_tenant(store, grant), tag_ids=tags, document_id=document,
                                       limit=limit, offset=offset)
    return await _visible(store, rows)


################################
# Concordance queries (#329)   #
################################

_MAX_PAGE = 200
# Weaviate returns no rows beyond offset + limit = QUERY_MAXIMUM_RESULTS (default 10,000).
_MAX_WINDOW = 10_000
# Annotated documents a document-ordered or year-filtered query reads (one aggregation).
_MAX_DOCUMENTS = 10_000
_MAX_WORDS = 10
_WORD = re.compile(r"[^\W_]+")
"""A query word: a run of letters and digits, split as Weaviate's ``word`` tokenization splits the
searched text (also at underscores; the workspace highlights by the same rule, #663)."""
DEFAULT_TYPES = (SpanType.pos, SpanType.auto)


def _parse_ids(values: list[Id] | None, kind: str) -> list[UUID] | None:
    if not values:
        return None
    try:
        return [UUID(str(v)) for v in values]
    except ValueError:
        raise InvalidRequestError(f"Malformed {kind} id") from None


ATTRIBUTES_NOT_ENABLED = ("Attributes are not enabled on this store: run "
                          "python -m semant_demo.maintenance.annotation_attributes add-schema and restart the backend.")


def _require_attribute_properties(store: AnnotationStore, query: AnnotationQuery) -> None:
    """Attribute filters on a store without the attribute properties would fail in Weaviate
    (an undeclared property): refuse them with 503 as assignments are (#331)."""
    if (query.attribute_values or query.attribute_unassigned) and not store.spans.attributes:
        raise ServiceUnavailableError(ATTRIBUTES_NOT_ENABLED)


def _attribute_filter(values: list[str] | None, unassigned: list[Id] | None
                      ) -> tuple[dict[UUID, list[UUID]], list[UUID]]:
    """The attribute conditions of a query from ``<attribute id>:<value id>`` pairs and attribute
    ids (#331). Ids of other collections are not checked: they match nothing in this tenant."""
    if len(values or []) > MAX_ATTRIBUTE_FILTER_VALUES:
        raise InvalidRequestError(f"Filter by at most {MAX_ATTRIBUTE_FILTER_VALUES} attribute values")
    try:
        pairs = [codec.decode(v) for v in values or []]
    except ValueError:
        raise InvalidRequestError("Malformed attribute value filter") from None
    wanted: dict[UUID, list[UUID]] = {}
    for attribute, value in pairs:
        wanted.setdefault(attribute, [])
        if value not in wanted[attribute]:
            wanted[attribute].append(value)
    missing = _parse_ids(unassigned, "attribute") or []
    if len(wanted) + len(missing) > MAX_ATTRIBUTE_FILTERS:
        raise InvalidRequestError(f"Filter by at most {MAX_ATTRIBUTE_FILTERS} attributes")
    return wanted, list(dict.fromkeys(missing))


def _concordance_query(tag_ids: list[Id] | None, types: list[SpanType] | None, text: str | None,
                       ids: list[UUID] | None = None, attribute_values: list[str] | None = None,
                       attribute_unassigned: list[Id] | None = None,
                       text_scope: TextScope = TextScope.annotation) -> AnnotationQuery:
    # Composed (NFC), as the corpus text is stored: a decomposed query (e.g. pasted) still matches.
    words = _WORD.findall(unicodedata.normalize("NFC", text or ""))
    if len(words) > _MAX_WORDS:
        raise InvalidRequestError(f"Search for at most {_MAX_WORDS} words")
    wanted, missing = _attribute_filter(attribute_values, attribute_unassigned)
    return AnnotationQuery(tag_ids=_parse_ids(tag_ids, "tag"), types=list(dict.fromkeys(types or DEFAULT_TYPES)),
                           words=words, text_scope=text_scope, derivation_version=DERIVATION_VERSION, ids=ids,
                           attribute_values=wanted, attribute_unassigned=missing)


def _filters_query(filters: AnnotationFilters, ids: list[UUID] | None = None) -> AnnotationQuery:
    """The stored-field conditions of an annotation query (#663); its document filters are
    applied to the annotated documents (``_annotated_documents``)."""
    return _concordance_query(filters.tag_ids, filters.types, filters.q, ids, filters.attribute_values,
                              filters.attribute_unassigned, filters.text_scope)


@dataclass
class _Near:
    """A proximity filter's outcome (#333): its coverage and the neighbors explaining each match."""
    coverage: ProximityCoverage
    neighbors: dict[UUID, list[NearNeighbor]]


async def _apply_near(store: AnnotationStore, cid: UUID, filters: AnnotationFilters, query: AnnotationQuery,
                      conditions: list[Condition]) -> tuple[AnnotationQuery, _Near | None]:
    """``query`` restricted by the proximity filter ``filters.near`` (#333), applied before any
    counting or paging, and its outcome; ``query`` unchanged without one.

    Reads the neighbors' documents (one aggregation), then the positions of the neighbors and of
    the annotations matching ``query`` in those documents only (at most
    ``proximity.MAX_NEAR_ANNOTATIONS`` each; more is refused, never truncated), and matches them
    per document. The result is the matching annotation ids. With ``absent`` the annotations of
    every document are read (not only those with a neighbor), so an annotation without current
    positions never proves absence, even in a document without any neighbor; it counts as unknown."""
    near = filters.near
    if near is None:
        return query, None
    neighbor_query = _concordance_query(near.tag_ids, near.types, None, attribute_values=near.attribute_values)
    _require_attribute_properties(store, neighbor_query)
    counts = await store.spans.count_by_document(cid, neighbor_query, _MAX_DOCUMENTS + 1, filters.document_ids or None)
    if len(counts) > _MAX_DOCUMENTS:
        raise InvalidRequestError(f"The neighbor annotations are in more than {_MAX_DOCUMENTS} documents; "
                                  "choose fewer neighbor tags or documents.")
    documents = list(counts)
    if conditions and documents:  # annotations of other documents are filtered out anyway
        documents = list(await store.documents.read_eligible(documents, conditions=conditions, include_restricted=True))
    limit = proximity.MAX_NEAR_ANNOTATIONS
    if sum(counts[d] for d in documents) > limit:
        raise InvalidRequestError(f"More than {limit} neighbor annotations would have to be compared; "
                                  "choose fewer neighbor tags or filter by document.")
    # Absence is decided per annotation everywhere; presence needs only documents with a neighbor.
    primary_documents = (filters.document_ids or None) if near.absent else documents
    if near.absent and conditions:
        # Only the documents the document filters select: their candidates, not the tenant's, are capped.
        annotated = await store.spans.count_by_document(cid, query, _MAX_DOCUMENTS + 1, primary_documents)
        if len(annotated) > _MAX_DOCUMENTS:
            raise InvalidRequestError(f"The annotations are in more than {_MAX_DOCUMENTS} documents; "
                                      "filter by tag or text first.")
        primary_documents = list(await store.documents.read_eligible(list(annotated), conditions=conditions, include_restricted=True)) \
            if annotated else []
        candidates = sum(annotated[d] for d in primary_documents)
    elif primary_documents is None or primary_documents:
        candidates = await store.spans.count_rows(cid, query, primary_documents)
    else:
        candidates = 0
    if candidates > limit:
        where = "" if near.absent else " in documents with a neighbor"
        raise InvalidRequestError(f"More than {limit} annotations{where} would have to be compared; narrow the filters.")
    primary, neighbors = await asyncio.gather(
        store.spans.query_positions(cid, query, document_ids=primary_documents, limit=limit),
        store.spans.query_positions(cid, neighbor_query, document_ids=documents, limit=limit))
    try:
        matched = proximity.match(primary, neighbors, near)
    except proximity.TooManyComparisons:
        raise InvalidRequestError("The proximity filter would compare too many annotations; "
                                  "use a smaller distance or narrow the filters.") from None
    return query.model_copy(update={"near_ids": matched.ids}), _Near(
        coverage=ProximityCoverage(primary=matched.primary, unknown=matched.unknown,
                                   neighbors=matched.neighbors_found,
                                   neighbors_unpositioned=matched.neighbors_unpositioned),
        neighbors={a: [NearNeighbor(id=b.id, tagId=b.tag, start=b.start_char - matched.starts[a],
                                    end=b.end_char - matched.starts[a]) for b in found]
                   for a, found in matched.neighbors.items()})


def _text_status(row: AnnotationRow) -> TextStatus:
    if text_current(row):
        return TextStatus.ready
    if row.enrichmentStatus in (EnrichmentStatus.failed, EnrichmentStatus.invalid) \
            and (row.enrichedRevision or 0) == (row.revision or 0):
        return TextStatus(row.enrichmentStatus.value)
    return TextStatus.pending


def _list_row(row: AnnotationRow, document: Document | None, near: _Near | None = None) -> AnnotationListRow:
    ready = text_current(row)
    return AnnotationListRow(
        neighbors=near.neighbors.get(row.id, []) if near is not None else [],
        id=row.id, tagId=row.tagId, type=row.type, chunkId=row.chunkId, documentId=row.documentId,
        start=row.start, end=row.end, revision=row.revision or 0, textStatus=_text_status(row),
        text=row.text if ready else None, leftContext=row.leftContext if ready else None,
        rightContext=row.rightContext if ready else None, documentAvailable=document is not None,
        documentTitle=document.title if document else None, documentYear=document.yearIssued if document else None,
        editVersion=row.editVersion or 0, provenance=row.provenance(),
        attributes=codec.group(row.attributeValues) if row.type == SpanType.pos else {}, attributeVersion=row.attributeVersion or 0)


def _title_key(document: Document | None) -> tuple:
    title = document.title if document is not None else None
    return (title is None, (title or "").casefold(), title or "")


def _year_key(document: Document | None) -> tuple:
    year = document.yearIssued if document is not None else None
    return (year is None, year or 0)


@total_ordering
class _Reversed:
    """A sort key component in reverse order."""
    __slots__ = ("value",)

    def __init__(self, value) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Reversed) and self.value == other.value

    def __lt__(self, other: "_Reversed") -> bool:
        return other.value < self.value


def _descending(key: tuple) -> tuple:
    """A ``(missing, *values)`` key with its values reversed and missing values still last."""
    missing, *values = key
    return (missing, *(_Reversed(v) for v in values))


@dataclass
class _Documents:
    """The annotated documents of a query, filtered and in row order, with their counts."""
    order: list[UUID]
    counts: dict[UUID, int]
    documents: dict[UUID, Document]


async def _annotated_documents(store: AnnotationStore, cid: UUID, query: AnnotationQuery, sort: AnnotationSort,
                               document_ids: list[UUID] | None, conditions: list[Condition],
                               descending: bool = False) -> _Documents:
    """The documents with annotations matching ``query`` (of ``document_ids`` when given) and
    their counts; with document ``conditions`` (``DocumentFilters``) only the documents they
    select, read by one ``Documents`` query with the shared predicates (#663). ``descending``
    reverses titles and years; documents without them stay last, ties stay by id. Raises
    ``UnavailableFilter`` (adapter) for a condition the corpus store cannot evaluate."""
    counts = await store.spans.count_by_document(cid, query, _MAX_DOCUMENTS + 1, document_ids)
    if len(counts) > _MAX_DOCUMENTS:
        raise InvalidRequestError(
            f"The annotations are in more than {_MAX_DOCUMENTS} documents; filter by tag or text first.")
    if conditions:
        documents = await store.documents.read_eligible(list(counts), conditions=conditions, include_restricted=True)
        counts = {d: n for d, n in counts.items() if d in documents}
    else:
        documents = await store.documents.read_many(list(counts))

    def key(d: UUID) -> tuple:
        title, year = _title_key(documents.get(d)), _year_key(documents.get(d))
        if descending:
            title, year = _descending(title), _descending(year)
        return (*(year + title if sort == AnnotationSort.year else title + year), str(d))
    return _Documents(order=sorted(counts, key=key), counts=counts, documents=documents)


async def _rows_in_document_order(store: AnnotationStore, cid: UUID, query: AnnotationQuery, found: _Documents,
                                  limit: int, offset: int) -> list[AnnotationRow]:
    """The page ``[offset, offset + limit)`` of the rows of ``found.order``'s documents in
    that order, each by position: documents entirely inside the page are read by one query,
    the first and last documents of the page by their own when the page cuts them."""
    slices: list[tuple[UUID, int, int]] = []  # document, rows skipped, rows taken
    position = 0
    for document in found.order:
        count = found.counts[document]
        skip, end = max(0, offset - position), min(count, offset + limit - position)
        if end > skip:
            slices.append((document, skip, end - skip))
        position += count
        if position >= offset + limit:
            break
    whole = [d for d, skip, take in slices if skip == 0 and take == found.counts[d]]

    async def cut(document: UUID, skip: int, take: int) -> list[AnnotationRow]:
        if skip + take > _MAX_WINDOW:
            raise InvalidRequestError(f"Rows beyond the first {_MAX_WINDOW} of one document cannot be paged.")
        return await store.spans.query_rows(cid, query, document_ids=[document], limit=take, offset=skip)

    async def read_whole() -> list[AnnotationRow]:
        if not whole:
            return []
        return await store.spans.query_rows(cid, query, document_ids=whole,
                                            limit=sum(found.counts[d] for d in whole))

    parts = await asyncio.gather(read_whole(), *(cut(d, s, t) for d, s, t in slices if d not in whole))
    by_document: dict[UUID, list[AnnotationRow]] = {d: [] for d, _, _ in slices}
    for row in parts[0]:  # partitioning keeps each document's position order
        by_document[row.documentId].append(row)
    for (document, _, _), rows in zip([s for s in slices if s[0] not in whole], parts[1:]):
        by_document[document] = rows
    return [row for document, _, _ in slices for row in by_document[document]]


SEMANTIC_NOT_CONFIGURED = "Search by meaning is not configured on this server (no annotation vector)."
EMBEDDING_UNAVAILABLE = ("The embedding service is unavailable, so search by meaning cannot run now. "
                         "Lexical search and Find similar still work.")
NO_SOURCE_VECTOR = ("This annotation has no current vector yet (it is pending, failed or of an older edit), "
                    "so similar annotations cannot be found from it.")
_MAX_CANDIDATES = 4 * (MAX_TOP_K + 1)
"""Ranked candidates read at most to find ``k`` + 1 with a current vector (#664)."""


@dataclass
class _Ranked:
    """A ranked annotation query's top ``k`` (relevance, then id) and what they are of."""
    ids: list[UUID]
    result: AnnotationResultSet
    documents: dict[UUID, Document] | None
    """The annotated documents, when document filters had to read them."""


def _ranking_query(filters: AnnotationFilters, ranking: AnnotationRanking,
                   ids: list[UUID] | None = None) -> tuple[AnnotationQuery, str | None]:
    """The stored-field conditions of a ranked query and the text it ranks by (#716): ``semantic``
    and ``hybrid`` rank by ``ranking_query`` (required); ``similar`` ranks by its source and takes
    none. ``q`` is a lexical filter in every mode, applied before ranking. Checked before any read
    or provider call."""
    text = " ".join((filters.ranking_query or "").split())
    if ranking.mode == RetrievalMode.similar:
        if text:
            raise InvalidRequestError("Find similar ranks by its source annotation; it takes no similarity text.")
        return _filters_query(filters, ids), None
    if not text:
        raise InvalidRequestError("Enter a text to search by meaning.")
    return _filters_query(filters, ids), text


async def _query_vector(store: AnnotationStore, cid: UUID, ranking: AnnotationRanking,
                        text: str | None) -> tuple[list[float], UUID | None]:
    """The vector to rank by and the annotation never to rank: the query embedding of ``text``,
    or the stored current vector of the ``similar`` source (no provider call)."""
    vector = store.enrichment.vector
    assert vector is not None
    if ranking.mode == RetrievalMode.similar:
        found = await store.spans.read_vector(cid, ranking.similar_to, vector.target_vector)
        if found is None:
            raise NotFoundError("Annotation not found")
        source, stored = found
        if stored is None or not vector_current(source, vector.id):
            raise InvalidRequestError(NO_SOURCE_VECTOR)
        return stored, None if ranking.include_source else source.id
    try:
        return await vector.embed_query(text), None
    except Exception as exc:
        logger.warning("Embedding an annotation query failed: %s", type(exc).__name__)
        raise ServiceUnavailableError(EMBEDDING_UNAVAILABLE) from exc


async def _rank(store: AnnotationStore, cid: UUID, filters: AnnotationFilters, ranking: AnnotationRanking,
                query: AnnotationQuery, text: str | None, conditions: list[Condition]) -> _Ranked:
    """The top ``ranking.k`` annotations matching ``query``, ``filters.document_ids`` and the
    document ``conditions``, by relevance then id, and their vector coverage (#664). Every
    filter applies before ranking. A candidate whose vector is ``ready`` but not of its current
    revision (not filterable in Weaviate) is skipped and counted as uncovered; more candidates
    are read until ``k`` + 1 current ones are found, so pages are never silently short."""
    vector = store.enrichment.vector
    assert vector is not None
    documents, joined = filters.document_ids or None, None
    if conditions:
        found = await _annotated_documents(store, cid, query, AnnotationSort.document, documents, conditions)
        documents, joined, matching = found.order, found.documents, sum(found.counts.values())
    else:
        matching = None
    embedded, exclude = await _query_vector(store, cid, ranking, text)
    ranked_query = query.model_copy(update={"vector_config": vector.id})
    order = VectorRanking(target_vector=vector.target_vector, vector=embedded, exclude=exclude,
                          **({"text": text, "fields": HYBRID_FIELDS, "alpha": HYBRID_ALPHA}
                             if ranking.mode == RetrievalMode.hybrid else {}))
    counts = [store.spans.count_rows(cid, ranked_query, documents)]
    if matching is None:
        counts.append(store.spans.count_rows(cid, query, documents))
    limit = ranking.k + 1
    candidates, *counted = await asyncio.gather(
        store.spans.rank(cid, ranked_query, order, document_ids=documents, limit=limit), *counts)
    while True:
        current = [c for c in candidates if vector_current(c, vector.id)]
        if len(current) > ranking.k or len(candidates) < limit or limit >= _MAX_CANDIDATES:
            break
        limit = min(2 * limit, _MAX_CANDIDATES)
        candidates = await store.spans.rank(cid, ranked_query, order, document_ids=documents, limit=limit)
    with_vector = counted[0] - (len(candidates) - len(current))
    if matching is None:
        matching = counted[1]
    if ranking.mode == RetrievalMode.hybrid:
        current.sort(key=lambda c: (-(c.score or 0.0), str(c.id)))
    else:
        current.sort(key=lambda c: (c.distance if c.distance is not None else float("inf"), str(c.id)))
    truncated = len(current) > ranking.k or (len(candidates) == limit and limit >= _MAX_CANDIDATES)
    return _Ranked(ids=[c.id for c in current[:ranking.k]], documents=joined, result=AnnotationResultSet(
        kind=ResultKind.top_k, mode=ranking.mode, k=ranking.k, truncated=truncated,
        coverage=VectorCoverage(matching=matching, with_vector=max(0, min(with_vector, matching)))))


def _check_ranking(store: AnnotationStore, ranking: AnnotationRanking, sort: AnnotationSort | None,
                   descending: bool = False) -> None:
    if sort is not None or descending:
        raise InvalidRequestError("Ranked results are in order of relevance; they cannot be sorted.")
    if store.enrichment.vector is None:
        raise ServiceUnavailableError(SEMANTIC_NOT_CONFIGURED)


_TEXT_SORTS = (AnnotationSort.text, AnnotationSort.left, AnnotationSort.right)
_SORT_KEY_PROPERTIES = {AnnotationSort.text: "textSortKey", AnnotationSort.left: "leftSortKey",
                        AnnotationSort.right: "rightSortKey"}
SORT_KEYS_NOT_ENABLED = ("Sorting by the context needs the annotation sort keys, which this store does not hold yet: run "
                         "python -m semant_demo.maintenance.annotation_enrichment add-schema and restart the backend.")
_MAX_PARTITION_QUERIES = 16
"""Partition counts of the attribute sort run at once."""


async def _none() -> None:
    return None


def _sort_property(store: AnnotationStore, sort: AnnotationSort) -> str:
    """The property a text or context sort orders by: its sort key (#666), or, on a store without
    the keys, ``text`` for the text sort (the code-point order of before)."""
    if store.enrichment.sort_keys:
        return _SORT_KEY_PROPERTIES[sort]
    if sort == AnnotationSort.text:
        return "text"
    raise ServiceUnavailableError(SORT_KEYS_NOT_ENABLED)


class AttributeDefinitions(Protocol):
    """The collection's attribute definitions (``adapters/sql/attributes.py``): the value order of
    the attribute sort (#666). ``read`` returns an attribute with ``values`` in definition order,
    each with ``id`` and ``retired``, or None."""

    async def read(self, collection_id: UUID, attribute_id: UUID): ...


async def _attribute_order(store: AnnotationStore, collection_id: UUID, attribute_id: Id | None,
                           attributes: AttributeDefinitions | None, descending: bool) -> list[str]:
    """The stored elements (``<attribute id>:<value id>``) of the sort attribute's values in sort
    order: active values in definition order, then retired ones; ``descending`` reverses each
    group (retired values stay after active ones)."""
    if attribute_id is None:
        raise InvalidRequestError("Choose the attribute to sort by (sort_attribute)")
    if not store.spans.attributes:
        raise ServiceUnavailableError(ATTRIBUTES_NOT_ENABLED)
    attribute = await attributes.read(collection_id, access.parse_id(attribute_id, "Attribute")) \
        if attributes is not None else None
    if attribute is None:
        raise NotFoundError("Attribute not found")
    active = [v.id for v in attribute.values if not v.retired]
    retired = [v.id for v in attribute.values if v.retired]
    if descending:
        active, retired = active[::-1], retired[::-1]
    return [codec.encode(attribute.id, v) for v in active + retired]


async def _rows_by_attribute(store: AnnotationStore, cid: UUID, query: AnnotationQuery, found: _Documents,
                             document_ids: list[UUID] | None, values: list[str], limit: int,
                             offset: int) -> list[AnnotationRow]:
    """The page ``[offset, offset + limit)`` of the attribute sort: one partition per value in
    ``values`` order, holding the approved annotations with that value and none before it (so an
    annotation with several values appears once, under its first), then the rest (no value of the
    attribute, or not approved); each partition in ``found``'s document order. Counts every
    partition per document (one aggregation each, bounded by the attribute's value count), then
    reads only the partitions the page touches, as ``_rows_in_document_order``. ``document_ids``:
    the documents the query is restricted to (``None``: those of ``found``, all annotated ones)."""
    partitions = [query.model_copy(update={"holds_value": v, "holds_none_of": values[:i]})
                  for i, v in enumerate(values)]
    partitions.append(query.model_copy(update={"holds_none_of": values}))
    limiter = asyncio.Semaphore(_MAX_PARTITION_QUERIES)

    async def count(partition: AnnotationQuery) -> dict[UUID, int]:
        async with limiter:
            return await store.spans.count_by_document(cid, partition, _MAX_DOCUMENTS + 1, document_ids)
    counts = await asyncio.gather(*(count(p) for p in partitions))
    rows: list[AnnotationRow] = []
    position = 0
    for partition, by_document in zip(partitions, counts):
        within = _Documents(order=[d for d in found.order if by_document.get(d)], counts=by_document,
                            documents=found.documents)
        size = sum(by_document[d] for d in within.order)
        skip, end = max(0, offset - position), min(size, offset + limit - position)
        if end > skip:
            rows += await _rows_in_document_order(store, cid, partition, within, end - skip, skip)
        position += size
        if position >= offset + limit:
            break
    return rows


async def count_annotations(store: AnnotationStore, user: Principal | None, collection_id: Id, *,
                            tag_ids: list[Id] | None = None) -> AnnotationCounts:
    """
    How many annotations the collection holds per type, of some tags only when ``tag_ids``
    is given. Counts only: reads no annotation rows and no documents.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    queries = [_concordance_query(tag_ids, [t], None) for t in (SpanType.pos, SpanType.auto, SpanType.neg)]
    cid = await use_tenant(store, grant)
    approved, suggestions, rejected = await asyncio.gather(*(store.spans.count_rows(cid, q) for q in queries))
    return AnnotationCounts(approved=approved, suggestions=suggestions, rejected=rejected)


async def query_annotations(store: AnnotationStore, user: Principal | None, collection_id: Id,
                            filters: AnnotationFilters | None = None, *,
                            ranking: AnnotationRanking | None = None, sort: AnnotationSort | None = None,
                            descending: bool = False, limit: int = 50, offset: int = 0, annotation_ids: list[Id] | None = None,
                            sort_attribute: Id | None = None,
                            attributes: "AttributeDefinitions | None" = None) -> AnnotationPage:
    """
    One page of the collection's annotations matching the annotation query ``filters``
    (``AnnotationFilters``, #663) as concordance (KWIC) rows, and the number of all that match.
    The order is total (``AnnotationSort``, reversed when ``descending``: documents without a
    title or year and rows without text last, rows of one document still in reading order, ties
    by id), so pages do not overlap or skip rows while the annotations do not change. ``annotation_ids``: only these annotations (the workspace reads
    one it shows as it is now, whether or not it still matches the page's filters; #460).

    Text and context sorts (#666) use the stored Czech sort keys (``collation.py``) when the
    collection holds them (the text sort falls back to Weaviate's order of the text otherwise; the
    context sorts are unavailable, 503) and report how many rows have no current keys
    (``unsortable``). The attribute sort (``sort_attribute``, read from ``attributes`` after
    authorization) pages through one partition per value of the attribute (``_rows_by_attribute``).

    Reads the annotations and, for document order or document filters, the metadata of the
    annotated documents once (at most ``_MAX_DOCUMENTS``); never the source chunks.

    A ranked ``ranking`` (#664) pages through its top ``k`` instead, in relevance order (``sort``
    must be absent); ``semantic`` and ``hybrid`` embed ``q`` (one provider call per page, after
    authorization and validation), ``similar`` reads its source's stored vector.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    if not 1 <= limit <= _MAX_PAGE or offset < 0:
        raise InvalidRequestError(f"limit must be between 1 and {_MAX_PAGE} and offset not negative")
    filters, ranking = filters or AnnotationFilters(), ranking or AnnotationRanking()
    ids = _parse_ids(annotation_ids, "annotation")
    if ranking.ranked:
        _check_ranking(store, ranking, sort, descending)
        query, text = _ranking_query(filters, ranking, ids)
    else:
        if filters.ranking_query:
            raise InvalidRequestError("A similarity text needs a ranked mode (semantic or hybrid).")
        query, text = _filters_query(filters, ids), None
    sort = sort or AnnotationSort.document
    _require_attribute_properties(store, query)
    if sort_attribute is not None and sort != AnnotationSort.attribute:
        raise InvalidRequestError("sort_attribute is only used with the attribute sort")
    sort_by = _sort_property(store, sort) if sort in _TEXT_SORTS else None
    documents = filters.document_ids or None
    conditions = document_conditions(filters.document_filters)
    values = None
    if sort == AnnotationSort.attribute:
        values = await _attribute_order(store, grant.collection_id, sort_attribute, attributes, descending)
    cid = await use_tenant(store, grant)
    query, near = await _apply_near(store, cid, filters, query, conditions)
    coverage = near.coverage if near is not None else None
    if ranking.ranked:
        ranked = await _rank(store, cid, filters, ranking, query, text, conditions)
        page = ranked.ids[offset:offset + limit]
        found_rows = await store.spans.read_rows_by_id(cid, page)
        rows = [found_rows[i] for i in page if i in found_rows]
        joined = ranked.documents if ranked.documents is not None else await store.documents.read_many(
            list({r.documentId for r in rows if r.documentId is not None}))
        return AnnotationPage(rows=[_list_row(r, joined.get(r.documentId) if r.documentId else None, near)
                                    for r in rows], total=len(ranked.ids), offset=offset, limit=limit,
                              result=ranked.result, proximity=coverage)
    unsortable = None
    if sort in _TEXT_SORTS:
        if offset + limit > _MAX_WINDOW:
            raise InvalidRequestError(f"Rows beyond the first {_MAX_WINDOW} cannot be paged; narrow the filters.")
        if conditions:
            found = await _annotated_documents(store, cid, query, AnnotationSort.document, documents, conditions)
            total, documents, joined = sum(found.counts.values()), found.order, found.documents
        else:
            total, joined = await store.spans.count_rows(cid, query, documents), None
        keyed = query.model_copy(update={"sort_key_version": sort_key_version()})
        rows, sortable = await asyncio.gather(
            store.spans.query_rows(cid, query, sort_by=sort_by, document_ids=documents, limit=limit, offset=offset,
                                   descending=descending),
            store.spans.count_rows(cid, keyed, documents) if store.enrichment.sort_keys else _none())
        if sortable is not None:
            unsortable = max(0, total - sortable)
        if joined is None:
            joined = await store.documents.read_many(list({r.documentId for r in rows if r.documentId is not None}))
    else:
        found = await _annotated_documents(store, cid, query, sort if sort != AnnotationSort.attribute
                                           else AnnotationSort.document, documents, conditions,
                                           descending and sort != AnnotationSort.attribute)
        total = sum(found.counts.values())
        if sort == AnnotationSort.attribute:
            rows = await _rows_by_attribute(store, cid, query, found, found.order if conditions else documents,
                                            values, limit, offset)
        else:
            rows = await _rows_in_document_order(store, cid, query, found, limit, offset)
        joined = found.documents
    return AnnotationPage(rows=[_list_row(r, joined.get(r.documentId) if r.documentId else None, near) for r in rows],
                          total=total, offset=offset, limit=limit, unsortable=unsortable, proximity=coverage)


async def list_annotated_documents(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                   filters: AnnotationFilters | None = None) -> list[AnnotatedDocument]:
    """The documents with annotations matching the annotation query ``filters`` and how many,
    by title: the choices of the concordance's source filter. Its ``document_ids`` are not
    applied (they are what is being chosen); every other filter is."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    filters = filters or AnnotationFilters()
    query = _filters_query(filters)
    _require_attribute_properties(store, query)
    cid, conditions = await use_tenant(store, grant), document_conditions(filters.document_filters)
    # The neighbors may be in any document: the choice of documents is what is listed.
    query, _ = await _apply_near(store, cid, filters.model_copy(update={"document_ids": None}), query, conditions)
    found = await _annotated_documents(store, cid, query, AnnotationSort.document, None, conditions)
    def listed(d: UUID) -> AnnotatedDocument:
        document = found.documents.get(d)
        if document is None:
            return AnnotatedDocument(id=d, count=found.counts[d], available=False)
        return AnnotatedDocument(id=d, title=document.title, year=document.yearIssued, library=document.library,
                                 language=document.language, count=found.counts[d], available=True)
    return [listed(d) for d in found.order]


######################################
# Selection and review (#459)        #
######################################

async def resolve_annotation_ids(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                 request: AnnotationIdsRequest) -> AnnotationIds:
    """
    The ids of all annotations matching the concordance filters now (``within``: only
    among these), for a selection that must not change with later filters. At most
    ``MAX_RESOLVED_IDS``; a query matching more is refused, never truncated. A ranked
    ``request.ranking`` (#664) resolves exactly its top ``k`` (of ``within``), in relevance order.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    within = list(dict.fromkeys(request.within)) if request.within is not None else None
    if within is not None and len(within) > MAX_RESOLVED_IDS:
        raise InvalidRequestError(f"Ask about at most {MAX_RESOLVED_IDS} annotations")
    ranking = request.ranking
    filters = request
    if ranking.ranked:
        _check_ranking(store, ranking, None)
        query, text = _ranking_query(filters, ranking)  # ``within`` is applied to the top k, not before ranking
    else:
        if filters.ranking_query:
            raise InvalidRequestError("A similarity text needs a ranked mode (semantic or hybrid).")
        query, text = _filters_query(filters, within), None
    _require_attribute_properties(store, query)
    documents = request.document_ids or None
    conditions = document_conditions(request.document_filters)
    cid = await use_tenant(store, grant)
    if within == []:
        return AnnotationIds(ids=[], versions={}, attribute_versions={},
                             result=AnnotationResultSet(kind=ResultKind.top_k, mode=ranking.mode, k=ranking.k)
                             if ranking.ranked else AnnotationResultSet())
    query, _ = await _apply_near(store, cid, filters, query, conditions)
    if ranking.ranked:
        ranked, chosen = await _rank(store, cid, filters, ranking, query, text, conditions), set(within or ())
        versions = await store.spans.query_ids(cid, query.model_copy(update={"ids": ranked.ids}), limit=len(ranked.ids))
        top = [i for i in ranked.ids if i in versions and (within is None or i in chosen)]
        return AnnotationIds(ids=top, versions={i: versions[i][0] for i in top},
                             attribute_versions={i: versions[i][1] for i in top}, result=ranked.result)
    if conditions:
        found = await _annotated_documents(store, cid, query, AnnotationSort.document, documents, conditions)
        total, documents = sum(found.counts.values()), found.order
    else:
        total = await store.spans.count_rows(cid, query, documents)
    if total > MAX_RESOLVED_IDS:
        raise InvalidRequestError(
            f"{total} annotations match; at most {MAX_RESOLVED_IDS} can be selected at once. Narrow the filters.")
    versions = await store.spans.query_ids(cid, query, document_ids=documents, limit=MAX_RESOLVED_IDS)
    return AnnotationIds(ids=list(versions), versions={i: v[0] for i, v in versions.items()},
                         attribute_versions={i: v[1] for i, v in versions.items()})


_REVIEW_PATCHES = {ReviewAction.approve: PatchSpan(type=SpanType.pos), ReviewAction.reject: PatchSpan(type=SpanType.neg)}


async def review_annotations(store: AnnotationStore, user: Principal | None, collection_id: Id,
                             request: AnnotationReviewRequest) -> AnnotationReviewResult:
    """
    Approves, rejects, retags or deletes annotations of the collection (at most
    ``MAX_REVIEW_BATCH``), each on its own: an id that is no annotation of the collection
    (deleted meanwhile, or of another collection) is reported as ``find_annotation`` and
    not changed, the others are written best effort and reported per item. Type and tag
    changes keep offsets, revision and derived data (no embedding). Each annotation is
    checked against its expected version (``edit_conflict``, not changed, when it was
    written since); one already as the action asks counts as succeeded. ``previous`` holds
    the type or tag of each annotation the action changed as it was, for an undo.
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    ids = list(dict.fromkeys(request.annotation_ids))
    if not 1 <= len(ids) <= MAX_REVIEW_BATCH:
        raise InvalidRequestError(f"Review between 1 and {MAX_REVIEW_BATCH} annotations at once")
    if request.action == ReviewAction.retag:
        if request.tag_id is None:
            raise InvalidRequestError("Choose the new tag")
        await access.require_tags_in_collection(store.tags, [request.tag_id], grant.collection_id)
    cid = await use_tenant(store, grant)
    spans = await store.spans.read_many(cid, ids)
    missing = [_missing_failure(i) for i in ids if i not in spans]
    found = {i: spans[i] for i in ids if i in spans}
    expected = {i: request.expected_versions[i] for i in found}
    versions: dict[UUID, int] = {}
    previous: dict[UUID, AnnotationValues] = {}
    if not found:
        succeeded, failed = [], []
    elif request.action == ReviewAction.delete:
        succeeded, failed, versions = await _delete_spans(
            store, cid, list(found), expected)
    else:
        patch = _REVIEW_PATCHES.get(request.action) or PatchSpan(tagId=str(request.tag_id))
        updated, failed, conflicts, written = await _update_spans(store, cid, found, dict.fromkeys(found, patch),
                                                                  Actor.of(user), expected)
        succeeded = [str(s.id) for s in updated]
        versions = {UUID(str(s.id)): s.editVersion for s in [*updated, *conflicts]}
        # Only what this request changed can be undone: not an annotation already as the
        # action asks (also when another writer made the same change after it was read), and
        # only from values read at the version the write was checked against.
        for span in updated:
            sid = UUID(str(span.id))
            before = found[sid]
            if sid not in written or before.editVersion != expected[sid]:
                continue
            if patch.type is not None and before.type is not None and before.type != patch.type:
                previous[sid] = AnnotationValues(type=before.type)
            elif patch.tagId is not None and before.tagId and before.tagId != patch.tagId:
                previous[sid] = AnnotationValues(tag_id=before.tagId)
    failed = missing + failed
    return AnnotationReviewResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded,
                                  failed=failed, versions=versions, previous=previous)


def _restore_patch(values: AnnotationValues) -> PatchSpan:
    return PatchSpan(type=values.type, start=values.start, end=values.end,
                     tagId=str(values.tag_id) if values.tag_id else None,
                     chunkId=str(values.chunk_id) if values.chunk_id else None)


async def restore_annotations(store: AnnotationStore, user: Principal | None, collection_id: Id,
                              request: AnnotationRestoreRequest) -> AnnotationReviewResult:
    """
    Undo (#461): puts back the previous values of annotations of the collection that a
    review or boundary edit changed, each only while it still has the version that change
    left (``edit_conflict``, not restored, when it was written since). An ordinary edit by
    ``user``: a new version and last edit, a restored range a new revision derived again,
    a type restored to ``auto`` no longer reviewed. Per item like ``review_annotations``,
    with ``check_range`` for a range that no longer describes the document's text. Needs
    the collection's edit versions: without them an undo could overwrite anyone's change.
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    if not store.spans.provenance:
        raise InvalidRequestError("Undo needs the annotations' edit versions, which this collection does not record yet")
    values = {i.id: i.values for i in request.items}
    tags = {str(v.tag_id) for v in values.values() if v.tag_id is not None}
    if tags:
        await access.require_tags_in_collection(store.tags, list(tags), grant.collection_id)
    chunks = {str(v.chunk_id) for v in values.values() if v.chunk_id is not None}
    if chunks:
        await access.require_chunks_in_collection(store.collections, list(chunks), grant.collection_id)
    cid = await use_tenant(store, grant)
    spans = await store.spans.read_many(cid, list(values))
    failed = [_missing_failure(i) for i in values if i not in spans]
    patches: dict[UUID, PatchSpan] = {}
    for sid in values:
        if sid not in spans:
            continue
        patch = _restore_patch(values[sid])
        try:
            await _check_patched_ranges(store, {sid: spans[sid]}, patch)
        except (InvalidRequestError, NotFoundError) as e:  # also InvalidSpanRange
            failed.append(StepFailure(item_id=str(sid), step="check_range", message=str(e)))
            continue
        patches[sid] = patch
    versions: dict[UUID, int] = {}
    succeeded: list[str] = []
    if patches:
        found = {sid: spans[sid] for sid in patches}
        expected = {i.id: i.expected_version for i in request.items if i.id in patches}
        updated, update_failed, conflicts, _ = await _update_spans(store, cid, found, patches, Actor.of(user),
                                                                   expected)
        succeeded = [str(s.id) for s in updated]
        versions = {UUID(str(s.id)): s.editVersion for s in [*updated, *conflicts]}
        failed += update_failed
    return AnnotationReviewResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded,
                                  failed=failed, versions=versions)
