"""Chunk-level tag references derived from span annotations (ADR 0004, #204).

Search filters chunks by their ``automaticTag`` / ``positiveTag`` / ``negativeTag``
references. These are a projection of the spans: a chunk references tag ``T`` through
the property of span type ``X`` exactly when at least one span of type ``X`` with tag
``T`` is anchored on that chunk (its ``text_chunk`` reference; a cross-chunk span is
anchored on its first chunk). Tags belong to one collection, so a (chunk, tag) pair
needs no further scope.

``sync_chunk_tags`` re-derives the references of the given (chunk, tag) pairs from the
spans currently stored. Span writes call it for every pair they touched, after the span
write, so it is safe to repeat and keeps a reference while another span still backs it.
It is not atomic with the span write: a failure is returned as a ``StepFailure`` and the
span write is kept (ADR 0002).

``ChunkTagRepository`` (used by the Annotations service) runs the re-derivation of one
pair at a time within the process (#206). Every span write is followed by a sync that
starts after it, so the last sync of a pair reads all earlier span writes and the pair
ends consistent. Without this, two requests could interleave: one reads the spans, the
other changes them and syncs, the first applies its stale result. The lock is
process-local: with several worker processes the race remains (saving or deleting a
span of that pair again, or the audit, re-derives it).

``audit_chunk_tags`` and ``apply_chunk_tag_fixes`` serve the separate, reviewed cleanup
of existing data (``python -m semant_demo.maintenance.chunk_tag_audit``); nothing calls
them during startup or normal requests.
"""
import asyncio
import weakref
from dataclasses import dataclass
from typing import Callable, Iterable
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference

import semant_demo.schemas as schemas
from semant_demo.features.annotations.schemas import SpanType
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.adapters.weaviate.writes import step_failure
from semant_demo.schema.outcomes import StepFailure

REF_BY_TYPE: dict[str, str] = {
    SpanType.auto.value: "automaticTag",
    SpanType.pos.value: "positiveTag",
    SpanType.neg.value: "negativeTag",
}
CHUNK_TAG_REFS: tuple[str, ...] = tuple(REF_BY_TYPE.values())

_SYNC_CONCURRENCY = 8


@dataclass(frozen=True, order=True)
class ChunkTag:
    """One (chunk, tag) pair whose chunk-level references are derived from its spans."""
    chunk_id: UUID
    tag_id: UUID

    @classmethod
    def of(cls, chunk_id, tag_id) -> "ChunkTag":
        return cls(UUID(str(chunk_id)), UUID(str(tag_id)))

    def label(self) -> str:
        return f"{self.chunk_id}:{self.tag_id}"


def _ref_ids(obj, prop: str) -> list[UUID]:
    block = (obj.references or {}).get(prop) if obj is not None else None
    return [UUID(str(r.uuid)) for r in (block.objects if block else [])]


async def required_refs(client: WeaviateAsyncClient, names: schemas.CollectionNames, pair: ChunkTag) -> set[str]:
    """Reference properties the spans of ``pair`` require on its chunk."""
    spans = client.collections.get(names.span_collection_name)
    objs = await fetch_all(
        spans,
        filters=(Filter.by_ref("tag").by_id().equal(pair.tag_id)
                 & Filter.by_ref("text_chunk").by_id().equal(pair.chunk_id)),
        return_properties=["type"],
    )
    return {REF_BY_TYPE[o.properties.get("type")] for o in objs if o.properties.get("type") in REF_BY_TYPE}


async def _chunk_refs(client: WeaviateAsyncClient, names: schemas.CollectionNames, chunk_id: UUID):
    """The chunk object with its tag references, or ``None`` when the chunk does not exist."""
    return await client.collections.get(names.chunks_collection_name).query.fetch_object_by_id(
        chunk_id,
        return_properties=[],
        return_references=[QueryReference(link_on=p, return_properties=[]) for p in CHUNK_TAG_REFS],
    )


async def _sync_pair(client: WeaviateAsyncClient, names: schemas.CollectionNames, pair: ChunkTag,
                     *, add: bool, remove: bool) -> None:
    required = await required_refs(client, names, pair)
    chunk = await _chunk_refs(client, names, pair.chunk_id)
    if chunk is None:
        # No chunk, no searchable state; a span on a missing chunk is a separate problem.
        return
    data = client.collections.get(names.chunks_collection_name).data
    for prop in CHUNK_TAG_REFS:
        present = pair.tag_id in _ref_ids(chunk, prop)
        if add and prop in required and not present:
            await data.reference_add(from_uuid=pair.chunk_id, from_property=prop, to=pair.tag_id)
        elif remove and prop not in required and present:
            await data.reference_delete(from_uuid=pair.chunk_id, from_property=prop, to=pair.tag_id)


async def sync_chunk_tags(client: WeaviateAsyncClient, names: schemas.CollectionNames,
                          pairs: Iterable[ChunkTag], *, add: bool = True, remove: bool = True,
                          lock_for: Callable[[ChunkTag], asyncio.Lock] | None = None,
                          ) -> tuple[list[ChunkTag], list[StepFailure]]:
    """Make the chunk tag references of ``pairs`` match their spans.

    Returns the pairs that were brought in line (including those already consistent)
    and a ``update_chunk_tags`` failure for each pair whose read or write failed. A failed
    read is a failure, never taken as "no spans". ``add`` / ``remove`` restrict which
    corrections are made (the cleanup command uses them); span writes pass neither.
    ``lock_for`` serializes the re-derivation of each pair (see ``ChunkTagRepository``).
    """
    pairs = sorted(set(pairs))
    sem = asyncio.Semaphore(_SYNC_CONCURRENCY)

    async def one(pair: ChunkTag):
        async with sem:
            if lock_for is None:
                await _sync_pair(client, names, pair, add=add, remove=remove)
            else:
                async with lock_for(pair):
                    await _sync_pair(client, names, pair, add=add, remove=remove)

    results = await asyncio.gather(*(one(p) for p in pairs), return_exceptions=True)
    done: list[ChunkTag] = []
    failed: list[StepFailure] = []
    for pair, res in zip(pairs, results):
        if isinstance(res, BaseException):
            if not isinstance(res, Exception):
                raise res
            failed.append(step_failure("update_chunk_tags", pair.label(), res))
        else:
            done.append(pair)
    return done, failed


class ChunkTagRepository:
    """Chunk tag re-derivation for span writes, one pair at a time within the process."""

    def __init__(self, client: WeaviateAsyncClient, collectionNames: schemas.CollectionNames):
        self.client = client
        self.collectionNames = collectionNames
        # A lock exists while some sync holds or waits for it.
        self._locks: weakref.WeakValueDictionary[ChunkTag, asyncio.Lock] = weakref.WeakValueDictionary()

    def _lock(self, pair: ChunkTag) -> asyncio.Lock:
        lock = self._locks.get(pair)
        if lock is None:
            lock = self._locks[pair] = asyncio.Lock()
        return lock

    async def sync(self, pairs: Iterable[ChunkTag]) -> list[StepFailure]:
        """Re-derive the pairs' references; returns a ``update_chunk_tags`` failure per failed pair."""
        _, failed = await sync_chunk_tags(self.client, self.collectionNames, pairs, lock_for=self._lock)
        return failed


# ── Audit of existing data ────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class ChunkTagIssue:
    chunk_id: UUID
    tag_id: UUID
    ref: str
    """``automaticTag``, ``positiveTag`` or ``negativeTag``."""
    kind: str
    """``unbacked``: the chunk holds the reference but no span of that type and tag is
    anchored on it. ``missing``: such a span exists but the chunk lacks the reference."""

    @property
    def pair(self) -> ChunkTag:
        return ChunkTag(self.chunk_id, self.tag_id)


async def audit_chunk_tags(client: WeaviateAsyncClient, names: schemas.CollectionNames) -> list[ChunkTagIssue]:
    """Every chunk tag reference without a backing span and every span-required reference
    that is missing. Read-only. Reads all chunks and spans (iterator, no result limit)."""
    present: set[tuple[UUID, UUID, str]] = set()
    chunks = client.collections.get(names.chunks_collection_name)
    async for obj in chunks.iterator(
            return_properties=[],
            return_references=[QueryReference(link_on=p, return_properties=[]) for p in CHUNK_TAG_REFS]):
        chunk_id = UUID(str(obj.uuid))
        for prop in CHUNK_TAG_REFS:
            for tag_id in _ref_ids(obj, prop):
                present.add((chunk_id, tag_id, prop))

    required: set[tuple[UUID, UUID, str]] = set()
    spans = client.collections.get(names.span_collection_name)
    async for obj in spans.iterator(
            return_properties=["type"],
            return_references=[QueryReference(link_on="tag", return_properties=[]),
                               QueryReference(link_on="text_chunk", return_properties=[])]):
        prop = REF_BY_TYPE.get(obj.properties.get("type"))
        if prop is None:
            continue
        for chunk_id in _ref_ids(obj, "text_chunk"):
            for tag_id in _ref_ids(obj, "tag"):
                required.add((chunk_id, tag_id, prop))

    issues = [ChunkTagIssue(c, t, p, "unbacked") for c, t, p in present - required]
    issues += [ChunkTagIssue(c, t, p, "missing") for c, t, p in required - present]
    return sorted(issues)


async def apply_chunk_tag_fixes(client: WeaviateAsyncClient, names: schemas.CollectionNames,
                                issues: Iterable[ChunkTagIssue], *, remove_unbacked: bool, add_missing: bool,
                                ) -> tuple[list[ChunkTag], list[StepFailure]]:
    """Re-check and correct the pairs of reported issues of the selected kinds.

    Each pair is re-derived from the spans stored now, not from the report, so a span
    created since the audit keeps its reference. A pair is corrected in both selected
    directions, which may also fix a reference the report did not list for that pair.
    """
    kinds = {k for k, on in (("unbacked", remove_unbacked), ("missing", add_missing)) if on}
    pairs = {i.pair for i in issues if i.kind in kinds}
    return await sync_chunk_tags(client, names, pairs, add=add_missing, remove=remove_unbacked)
