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
also the review. ``origin``, ``aiRunId``, ``reason`` and ``confidence`` are never
changed. A write or delete that names the version its caller expects reads the span
under its lock and is refused (``EditConflictError``; per item ``edit_conflict`` in
batches) when the span was written since, unless it already is as the write asks (then
it counts as done and nothing is written: a retry of a write that landed). The lock is
per process: across backend processes a conflict is detectable but not atomic (ADR 0009).
"""
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from semant_demo.features.annotations.schemas import (
    MAX_RESOLVED_IDS, MAX_REVIEW_BATCH, AnnotatedDocument, AnnotationIds, AnnotationIdsRequest, AnnotationListRow,
    AnnotationOrigin, AnnotationPage, AnnotationQuery, AnnotationReviewRequest, AnnotationReviewResult,
    AnnotationRow, AnnotationSort, ChunkTagSyncRequest, EnrichmentStatus, ReviewAction, SpanType, TagSpan, TextStatus, VectorStatus,
)
from semant_demo.features.documents.schemas import Document
from semant_demo.adapters.sql.tenant_activity import NoTenantActivity, TenantActivity
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag, ChunkTagRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.spans import SpanRepository, pair_of
from semant_demo.adapters.weaviate.tags import TagRepository
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.core.errors import EditConflictError, IncompleteWriteError, InvalidRequestError, NotFoundError
from semant_demo.features.annotations.derivation import DERIVATION_VERSION, DerivedText, DocumentText
from semant_demo.features.annotations.enrichment import Enrichment, text_current, vector_current
from semant_demo.features.annotations.offsets import InvalidSpanRange, check_span_range
from semant_demo.features.annotations.schemas import (
    AnnotationChunk, BulkUpdateSpansResponse, PatchSpan, PatchTag, PostSpan, PostTag, Tag, TagSpanWriteResult,
)
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import CollectionGrant, Principal
from semant_demo.core.outcomes import StepFailure, WriteResult, outcome_of

logger = logging.getLogger(__name__)

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
    and the review when it approves or rejects (changes the type to ``pos`` / ``neg``)."""
    now = _now()
    props: dict = {"editVersion": current.editVersion + 1, "lastEditedBy": actor.user_id, "lastEditedAt": now}
    if patch.type in (SpanType.pos, SpanType.neg) and patch.type != current.type:
        props |= {"reviewedBy": actor.user_id, "reviewedAt": now}
    return props


def _already(current: TagSpan, patch: PatchSpan) -> bool:
    """``current`` already has every value the patch sets."""
    return ((patch.start is None or patch.start == current.start) and (patch.end is None or patch.end == current.end)
            and (patch.type is None or patch.type == current.type)
            and (patch.tagId is None or str(access.parse_id(patch.tagId, "Tag")) == current.tagId))


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
                    span: PostSpan, texts: dict[UUID, DocumentText] | None = None, *,
                    actor: Actor | None = None) -> TagSpanWriteResult:
    """
    Stores a span in the collection's tenant (``document_id``: its chunk's document) with
    its derived fields and the provenance of ``actor``, re-derives its chunk tag, then
    stores its contextual vector. No access or offset check: the caller has checked
    annotation-edit access to the collection, the tag and the chunk scope (``create_span``,
    or the AI suggestion run for validated provider proposals). ``texts`` caches document
    texts across the saves of one run (source text is immutable).
    """
    pairs = {ChunkTag.of(span.chunkId, span.tagId)}
    refresh = None
    if store.enrichment.derived:
        refresh = await derive_refresh(store, document_id, span.chunkId, span.start, span.end, 1, texts=texts)
    try:
        span_id = await store.spans.insert(collection_id, span, document_id,
                                           refresh.properties(reset_vector=True) if refresh else None,
                                           _created(store, actor))
    except Exception:
        await store.chunk_tags.sync(collection_id, pairs)
        raise
    failed = await store.chunk_tags.sync(collection_id, pairs)
    if refresh is not None:
        failed += refresh.failures + await refresh_vector(store, collection_id, span_id, refresh)
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
    return await save_span(store, await use_tenant(store, grant), anchor.document_id, span, actor=Actor.of(user))


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


async def _update_and_read(store: AnnotationStore, collection_id: UUID, span_id: UUID, patch: PatchSpan,
                           actor: Actor, expected: int | None = None) -> tuple[TagSpan, "Refresh | None"]:
    """Applies the patch (with the span's new derived fields when its offsets are sent, and
    its provenance) and reads the span back; the refresh tells which vector to store next.
    ``expected``: the version the caller knows; a span written since raises
    ``EditConflictError`` unless it already is as the patch asks (then nothing is written)."""
    refresh = None
    offsets = store.enrichment.derived and (patch.start is not None or patch.end is not None)
    if store.spans.provenance:
        async with store.spans.lock(span_id):
            current = await store.spans.read(collection_id, span_id)
            if current is None:
                raise NotFoundError("Span not found")
            if expected is not None and current.editVersion != expected:
                if _already(current, patch):
                    return current, None
                raise _conflict(current)
            provenance = _edited(current, patch, actor)
            if offsets:
                refresh = await _patch_with_derived(store, collection_id, span_id, patch, provenance)
            else:
                await store.spans.update(collection_id, span_id, patch, provenance=provenance)
    elif offsets:
        async with store.spans.lock(span_id):
            refresh = await _patch_with_derived(store, collection_id, span_id, patch)
    else:
        await store.spans.update(collection_id, span_id, patch)
    span = await store.spans.read(collection_id, span_id)
    if span is None:
        raise NotFoundError("Span not found")
    return span, refresh


async def _patch_with_derived(store: AnnotationStore, collection_id: UUID, span_id: UUID,
                              patch: PatchSpan, provenance: dict | None = None) -> "Refresh | None":
    """An offset patch (under the span's lock): a changed range is a new revision with new
    derived fields; the same range re-derives only what is not current (a retry)."""
    row = await store.spans.read_row(collection_id, span_id)
    if row is None:
        raise NotFoundError("Span not found")
    start = row.start if patch.start is None else patch.start
    end = row.end if patch.end is None else patch.end
    moved = (start, end) != (row.start, row.end)
    vector = store.enrichment.vector
    stale_vector = vector is not None and not vector_current(row, vector.id)
    if not moved and text_current(row) and not stale_vector:
        await store.spans.update(collection_id, span_id, patch, provenance=provenance)
        return None
    # Re-derived text (also under a changed policy) invalidates the vector embedded from the old one.
    refresh = await derive_refresh(store, row.documentId, row.chunkId, start, end, (row.revision or 0) + moved)
    await store.spans.update(collection_id, span_id, patch, refresh.properties(reset_vector=True), provenance)
    return refresh


async def update_span(store: AnnotationStore, user: Principal | None, collection_id: Id, span_id: Id,
                      patch: PatchSpan, expected_version: int | None = None) -> TagSpanWriteResult:
    """
    Updates offsets, type (approve: ``auto`` -> ``pos``, reject: -> ``neg``) or tag of a
    span of the collection, then re-derives the span's (chunk, tag) pair and, on a tag
    change, the new pair. This runs for every patch, also offset-only, so saving a span
    again retries a chunk tag update that failed before. Changed offsets are validated
    like on creation; offsets that are not sent are not re-checked (approving an old
    span works whatever its offsets). ``expected_version``: the span's ``editVersion`` as
    the caller knows it; ``EditConflictError`` (nothing written) when it was written since.
    """
    cid, spans = await _authorize_span_patch(store, user, collection_id, [span_id], patch)
    await _check_patched_ranges(store, spans, patch)
    pairs = _pairs_touched_by(spans, patch)
    [sid] = spans
    try:
        span, refresh = await _update_and_read(store, cid, sid, patch, Actor.of(user), expected_version)
    except EditConflictError:
        raise
    except Exception:
        # The update may have been partly applied (or applied despite a timeout).
        await store.chunk_tags.sync(cid, pairs)
        raise
    failed = await store.chunk_tags.sync(cid, pairs)
    if refresh is not None:
        failed += refresh.failures + await refresh_vector(store, cid, sid, refresh)
    return _write_result(span, failed)


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
    ``expected_versions`` (``edit_conflict``, their current state in ``conflicts``) and the
    chunk tag updates that failed (``update_chunk_tags``). Chunk tags are re-derived once
    per touched pair after all span updates, also for spans whose update failed.
    """
    if not span_ids:
        return BulkUpdateSpansResponse(outcome=outcome_of(0, 0), spans=[])
    cid, spans = await _authorize_span_patch(store, user, collection_id, span_ids, patch)
    await _check_patched_ranges(store, spans, patch)
    expected = {access.parse_id(i, "Span"): v for i, v in (expected_versions or {}).items()}
    updated, failed, conflicts = await _update_spans(store, cid, spans, patch, Actor.of(user), expected)
    return BulkUpdateSpansResponse(outcome=outcome_of(len(updated), len(failed)),
                                   succeeded=[s.id for s in updated], failed=failed, spans=updated,
                                   conflicts=conflicts)


async def _update_spans(store: AnnotationStore, cid: UUID, spans: dict[UUID, TagSpan], patch: PatchSpan,
                        actor: Actor, expected: dict[UUID, int] | None = None
                        ) -> tuple[list[TagSpan], list[StepFailure], list[TagSpan]]:
    """Applies a checked patch to the spans concurrently (each checked against its version
    in ``expected``), then re-derives every touched chunk tag pair once (also of spans whose
    update failed) and stores new vectors; returns the updated spans in request order, the
    failures and the current state of the conflicting spans."""
    updated: list[TagSpan] = []
    failed: list[StepFailure] = []
    conflicts: list[TagSpan] = []
    refreshes: dict[UUID, Refresh] = {}
    ids = list(spans)
    expected = expected or {}
    results = await _gather(*(_update_and_read(store, cid, sid, patch, actor, expected.get(sid)) for sid in ids))
    for sid, res in zip(ids, results):
        if isinstance(res, EditConflictError):
            failed.append(_conflict_failure(sid))
            conflicts.append(TagSpan.model_validate(res.current))
        elif isinstance(res, NotFoundError):
            failed.append(_missing_failure(sid))
        elif isinstance(res, Exception):
            failed.append(step_failure("update_span", sid, res))
        else:
            updated.append(res[0])
            if res[1] is not None:
                refreshes[sid] = res[1]
    failed += await store.chunk_tags.sync(cid, _pairs_touched_by(spans, patch))
    for sid, refresh in refreshes.items():
        failed += refresh.failures + await refresh_vector(store, cid, sid, refresh)
    return updated, failed, conflicts


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
        else:
            props |= {"text": d.text, "leftContext": d.left_context, "rightContext": d.right_context,
                      "positionSegment": d.segment, "documentStartChar": d.start_char,
                      "documentEndChar": d.end_char, "documentStartWord": d.start_word,
                      "documentEndWord": d.end_word}
        return props


async def derive_refresh(store: AnnotationStore, document_id: UUID | None, chunk_id: Id, start: int, end: int,
                         revision: int, text: DocumentText | None = None,
                         texts: dict[UUID, DocumentText] | None = None) -> Refresh:
    """The derived fields of a span from its document's text (``text``: already read;
    ``texts``: a cache by document to read from and fill); a failed read is a
    ``derive_annotation`` failure, offsets that describe no text (or a missing anchor chunk
    or document) are ``invalid``."""
    try:
        if text is None:
            if document_id is None:
                anchor = await store.documents.read_chunk_text(access.parse_id(chunk_id, "Chunk"))
                document_id = anchor.document_id if anchor is not None else None
            if document_id is None:
                return Refresh(revision, None, EnrichmentStatus.invalid)
            text = (texts or {}).get(document_id)
            if text is None:
                text = DocumentText(await store.documents.read_chunk_texts(document_id))
                if texts is not None:
                    texts[document_id] = text
        return Refresh(revision, text.derive(chunk_id, start, end), EnrichmentStatus.ready)
    except InvalidSpanRange:
        return Refresh(revision, None, EnrichmentStatus.invalid)
    except Exception as e:
        return Refresh(revision, None, EnrichmentStatus.failed, [step_failure("derive_annotation", chunk_id, e)])


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
    Deletes a span of the collection, then removes chunk tag references no other span
    backs. ``outcome`` is ``partial`` when the span was deleted but the chunk tag could
    not be updated. ``expected_version``: the span's ``editVersion`` as the caller knows
    it; ``EditConflictError`` (nothing deleted) when it was written since.
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    spans = await access.require_spans_in_collection(store.spans, [span_id], grant.collection_id)
    cid = await use_tenant(store, grant)
    [(sid, span)] = spans.items()
    pairs = {pair_of(span)}
    try:
        await _delete_checked(store, cid, sid, expected_version)
    except EditConflictError:
        raise
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

    deleted, failed, _ = await _delete_spans(
        store, cid, await store.spans.list_in_document(cid, document, tags, span_type))
    return WriteResult(outcome=outcome_of(len(deleted), len(failed)), succeeded=deleted, failed=failed)


async def _delete_spans(store: AnnotationStore, cid: UUID, spans: dict[UUID, set[ChunkTag]],
                        expected: dict[UUID, int] | None = None
                        ) -> tuple[list[str], list[StepFailure], dict[UUID, int]]:
    """Deletes the listed spans one by one (each checked against its version in
    ``expected``), keeping going after a failure, then re-derives their chunk tag pairs,
    also of spans whose deletion failed (it may have been applied); returns the deleted
    ids, the failures and the current versions of the conflicting spans."""
    deleted: list[str] = []
    failed: list[StepFailure] = []
    conflicts: dict[UUID, int] = {}
    for sid in spans:
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
    failed += await store.chunk_tags.sync(cid, set().union(*spans.values()) if spans else set())
    return deleted, failed, conflicts


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


#############################
# Annotation rows (#328)    #
#############################

_MAX_ROWS = 1000
_HIDDEN_WHEN_STALE = ("text", "leftContext", "rightContext", "positionSegment", "documentStartChar",
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


async def similar_annotations(store: AnnotationStore, user: Principal | None, collection_id: Id, query: str, *,
                              tag_ids: list[Id] | None = None, limit: int = 20) -> list[AnnotationRow]:
    """
    The collection's annotations nearest in meaning to ``query`` (its query embedding
    against the contextual vectors), nearest first. Only vectors of the span's current
    revision and of the configured vector count: a span whose vector is pending, failed,
    stale or of another configuration is left out, so fewer than ``limit`` may return.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    _check_limit(limit)
    vector = store.enrichment.vector
    if vector is None:
        raise InvalidRequestError("Semantic annotation search is not configured.")
    tags = [access.parse_id(t, "Tag") for t in tag_ids] if tag_ids else None
    cid = await use_tenant(store, grant)
    rows = await store.spans.near_vector(cid, vector.target_vector, await vector.embed_query(query), vector.id,
                                         limit, tags)
    return await _visible(store, [r for r in rows if vector_current(r, vector.id) and text_current(r)])


################################
# Concordance queries (#329)   #
################################

_MAX_PAGE = 200
# Weaviate returns no rows beyond offset + limit = QUERY_MAXIMUM_RESULTS (default 10,000).
_MAX_WINDOW = 10_000
# Annotated documents a document-ordered or year-filtered query reads (one aggregation).
_MAX_DOCUMENTS = 10_000
_MAX_WORDS = 10
_WORD = re.compile(r"\w+")
DEFAULT_TYPES = (SpanType.pos, SpanType.auto)


def _parse_ids(values: list[Id] | None, kind: str) -> list[UUID] | None:
    if not values:
        return None
    try:
        return [UUID(str(v)) for v in values]
    except ValueError:
        raise InvalidRequestError(f"Malformed {kind} id") from None


def _concordance_query(tag_ids: list[Id] | None, types: list[SpanType] | None, text: str | None,
                       ids: list[UUID] | None = None) -> AnnotationQuery:
    words = _WORD.findall(text or "")
    if len(words) > _MAX_WORDS:
        raise InvalidRequestError(f"Search for at most {_MAX_WORDS} words")
    return AnnotationQuery(tag_ids=_parse_ids(tag_ids, "tag"), types=list(dict.fromkeys(types or DEFAULT_TYPES)),
                           words=words, derivation_version=DERIVATION_VERSION, ids=ids)


def _text_status(row: AnnotationRow) -> TextStatus:
    if text_current(row):
        return TextStatus.ready
    if row.enrichmentStatus in (EnrichmentStatus.failed, EnrichmentStatus.invalid) \
            and (row.enrichedRevision or 0) == (row.revision or 0):
        return TextStatus(row.enrichmentStatus.value)
    return TextStatus.pending


def _list_row(row: AnnotationRow, document: Document | None) -> AnnotationListRow:
    ready = text_current(row)
    return AnnotationListRow(
        id=row.id, tagId=row.tagId, type=row.type, chunkId=row.chunkId, documentId=row.documentId,
        start=row.start, end=row.end, revision=row.revision or 0, textStatus=_text_status(row),
        text=row.text if ready else None, leftContext=row.leftContext if ready else None,
        rightContext=row.rightContext if ready else None, documentAvailable=document is not None,
        documentTitle=document.title if document else None, documentYear=document.yearIssued if document else None,
        editVersion=row.editVersion or 0, provenance=row.provenance())


def _title_key(document: Document | None) -> tuple:
    title = document.title if document is not None else None
    return (title is None, (title or "").casefold(), title or "")


def _year_key(document: Document | None) -> tuple:
    year = document.yearIssued if document is not None else None
    return (year is None, year or 0)


@dataclass
class _Documents:
    """The annotated documents of a query, filtered and in row order, with their counts."""
    order: list[UUID]
    counts: dict[UUID, int]
    documents: dict[UUID, Document]


async def _annotated_documents(store: AnnotationStore, cid: UUID, query: AnnotationQuery, sort: AnnotationSort,
                               document_ids: list[UUID] | None, year_from: int | None,
                               year_to: int | None) -> _Documents:
    counts = await store.spans.count_by_document(cid, query, _MAX_DOCUMENTS + 1, document_ids)
    if len(counts) > _MAX_DOCUMENTS:
        raise InvalidRequestError(
            f"The annotations are in more than {_MAX_DOCUMENTS} documents; filter by tag or text first.")
    documents = await store.documents.read_many(list(counts))
    if year_from is not None or year_to is not None:
        def in_range(year: int | None) -> bool:
            return year is not None and (year_from is None or year >= year_from) and (year_to is None or year <= year_to)
        counts = {d: n for d, n in counts.items()
                  if d in documents and in_range(documents[d].yearIssued)}

    def key(d: UUID) -> tuple:
        title, year = _title_key(documents.get(d)), _year_key(documents.get(d))
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
        return await store.spans.query_rows(cid, query, by_text=False, document_ids=[document], limit=take, offset=skip)

    async def read_whole() -> list[AnnotationRow]:
        if not whole:
            return []
        return await store.spans.query_rows(cid, query, by_text=False, document_ids=whole,
                                            limit=sum(found.counts[d] for d in whole))

    parts = await asyncio.gather(read_whole(), *(cut(d, s, t) for d, s, t in slices if d not in whole))
    by_document: dict[UUID, list[AnnotationRow]] = {d: [] for d, _, _ in slices}
    for row in parts[0]:  # partitioning keeps each document's position order
        by_document[row.documentId].append(row)
    for (document, _, _), rows in zip([s for s in slices if s[0] not in whole], parts[1:]):
        by_document[document] = rows
    return [row for document, _, _ in slices for row in by_document[document]]


async def query_annotations(store: AnnotationStore, user: Principal | None, collection_id: Id, *,
                            tag_ids: list[Id] | None = None, types: list[SpanType] | None = None,
                            text: str | None = None, document_ids: list[Id] | None = None,
                            year_from: int | None = None, year_to: int | None = None,
                            sort: AnnotationSort = AnnotationSort.document, limit: int = 50,
                            offset: int = 0) -> AnnotationPage:
    """
    One page of the collection's annotations as concordance (KWIC) rows, and the number of
    all that match: of some tags, types (default ``pos`` and ``auto``; rejected ``neg``
    only when asked), documents and document years, and whose annotated text contains each
    word of ``text`` (inside a word, ignoring case). The order is total (``AnnotationSort``),
    so pages do not overlap or skip rows while the annotations do not change.

    Reads the annotations and, for document order or a year filter, the metadata of the
    annotated documents once (at most ``_MAX_DOCUMENTS``); never the source chunks.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    if not 1 <= limit <= _MAX_PAGE or offset < 0:
        raise InvalidRequestError(f"limit must be between 1 and {_MAX_PAGE} and offset not negative")
    query = _concordance_query(tag_ids, types, text)
    documents = _parse_ids(document_ids, "document")
    cid = await use_tenant(store, grant)
    by_year = year_from is not None or year_to is not None
    if sort == AnnotationSort.text and not by_year:
        if offset + limit > _MAX_WINDOW:
            raise InvalidRequestError(f"Rows beyond the first {_MAX_WINDOW} cannot be paged; narrow the filters.")
        total, rows = await asyncio.gather(
            store.spans.count_rows(cid, query, documents),
            store.spans.query_rows(cid, query, by_text=True, document_ids=documents, limit=limit, offset=offset))
        joined = await store.documents.read_many(list({r.documentId for r in rows if r.documentId is not None}))
    else:
        found = await _annotated_documents(store, cid, query, sort, documents, year_from, year_to)
        total = sum(found.counts.values())
        if sort == AnnotationSort.text:
            if offset + limit > _MAX_WINDOW:
                raise InvalidRequestError(f"Rows beyond the first {_MAX_WINDOW} cannot be paged; narrow the filters.")
            rows = await store.spans.query_rows(cid, query, by_text=True, document_ids=found.order,
                                                limit=limit, offset=offset)
        else:
            rows = await _rows_in_document_order(store, cid, query, found, limit, offset)
        joined = found.documents
    return AnnotationPage(rows=[_list_row(r, joined.get(r.documentId) if r.documentId else None) for r in rows],
                          total=total, offset=offset, limit=limit)


async def list_annotated_documents(store: AnnotationStore, user: Principal | None, collection_id: Id, *,
                                   tag_ids: list[Id] | None = None, types: list[SpanType] | None = None
                                   ) -> list[AnnotatedDocument]:
    """The documents with annotations of the given tags and types (default ``pos`` and
    ``auto``) and how many, by title: the choices of the concordance's source and year
    filters."""
    grant = await access.require_collection_read(store.collections, user, collection_id)
    query = AnnotationQuery(tag_ids=_parse_ids(tag_ids, "tag"), types=list(dict.fromkeys(types or DEFAULT_TYPES)))
    found = await _annotated_documents(store, await use_tenant(store, grant), query, AnnotationSort.document,
                                       None, None, None)
    return [AnnotatedDocument(id=d, title=found.documents[d].title if d in found.documents else None,
                              year=found.documents[d].yearIssued if d in found.documents else None,
                              count=found.counts[d], available=d in found.documents) for d in found.order]


######################################
# Selection and review (#459)        #
######################################

async def resolve_annotation_ids(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                 request: AnnotationIdsRequest) -> AnnotationIds:
    """
    The ids of all annotations matching the concordance filters now (``within``: only
    among these), for a selection that must not change with later filters. At most
    ``MAX_RESOLVED_IDS``; a query matching more is refused, never truncated.
    """
    grant = await access.require_collection_read(store.collections, user, collection_id)
    within = list(dict.fromkeys(request.within)) if request.within is not None else None
    if within is not None and len(within) > MAX_RESOLVED_IDS:
        raise InvalidRequestError(f"Ask about at most {MAX_RESOLVED_IDS} annotations")
    query = _concordance_query(request.tag_ids, request.types, request.q, within)
    documents = request.document_ids or None
    cid = await use_tenant(store, grant)
    if within == []:
        return AnnotationIds(ids=[], versions={})
    if request.year_from is not None or request.year_to is not None:
        found = await _annotated_documents(store, cid, query, AnnotationSort.document, documents,
                                           request.year_from, request.year_to)
        total, documents = sum(found.counts.values()), found.order
    else:
        total = await store.spans.count_rows(cid, query, documents)
    if total > MAX_RESOLVED_IDS:
        raise InvalidRequestError(
            f"{total} annotations match; at most {MAX_RESOLVED_IDS} can be selected at once. Narrow the filters.")
    versions = await store.spans.query_ids(cid, query, document_ids=documents, limit=MAX_RESOLVED_IDS)
    return AnnotationIds(ids=list(versions), versions=versions)


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
    written since); one already as the action asks counts as succeeded.
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
    if not found:
        succeeded, failed = [], []
    elif request.action == ReviewAction.delete:
        succeeded, failed, versions = await _delete_spans(
            store, cid, {i: {pair_of(s)} for i, s in found.items()}, expected)
    else:
        patch = _REVIEW_PATCHES.get(request.action) or PatchSpan(tagId=str(request.tag_id))
        updated, failed, conflicts = await _update_spans(store, cid, found, patch, Actor.of(user), expected)
        succeeded = [str(s.id) for s in updated]
        versions = {UUID(str(s.id)): s.editVersion for s in [*updated, *conflicts]}
    failed = missing + failed
    return AnnotationReviewResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded,
                                  failed=failed, versions=versions)


async def sync_annotation_chunk_tags(store: AnnotationStore, user: Principal | None, collection_id: Id,
                                     request: ChunkTagSyncRequest) -> WriteResult:
    """
    Re-derives the tag-filtered search references of (chunk, tag) pairs of the
    collection's tags from the annotations stored now: the repair of ``update_chunk_tags``
    failures, which also works after the annotation was deleted. Idempotent. ``succeeded``
    and ``failed`` name the pairs as ``chunk_id:tag_id``.
    """
    grant = await access.require_annotation_edit(store.collections, user, collection_id)
    pairs = sorted({ChunkTag.of(p.chunk_id, p.tag_id) for p in request.pairs})
    await access.require_tags_in_collection(store.tags, [p.tag_id for p in pairs], grant.collection_id)
    cid = await use_tenant(store, grant)
    failed = await store.chunk_tags.sync(cid, pairs)
    unsynced = {f.item_id for f in failed}
    succeeded = [p.label() for p in pairs if p.label() not in unsynced]
    return WriteResult(outcome=outcome_of(len(succeeded), len(failed)), succeeded=succeeded, failed=failed)
