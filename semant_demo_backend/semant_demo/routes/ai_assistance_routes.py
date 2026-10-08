"""
Routes for AI-assisted span suggestion.

Two endpoints, both streaming NDJSON results so the frontend can render
suggestions progressively as each chunk completes:

- ``POST /api/ai/suggest_spans/thorough`` —
  For every chunk currently added to the (collection, document) pair, calls
  Topicer's ``/v1/tags/propose/texts`` once with all selected tags. This is
  the most exhaustive variant — every chunk is shown to the LLM.

- ``POST /api/ai/suggest_spans/optimized`` —
  For every selected tag, calls Topicer's ``/v1/tags/propose/db/stream`` which
  performs vector pre-filtering on the database side and streams back only
  the chunks the LLM was asked about. Proxied through to the client as NDJSON.

Each NDJSON line emitted to the client is a :class:`SuggestSpansChunkResult`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from semant_demo import schemas
from semant_demo.ai_assistance.topicer_client import (
    TopicerError,
    propose_for_db_stream,
    propose_for_text_chunk,
    topicer_client,
)
from semant_demo.features.collections import access
from semant_demo.features.annotations import service as annotation_service
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.routes.dependencies import get_annotation_store, get_search
from semant_demo.schema.ai_assistance import (
    DeleteAutoSpansRequest,
    DeleteAutoSpansResponse,
    SuggestSpansChunkResult,
    SuggestSpansRequest,
    SuggestSpansSelectionRequest,
    SuggestSpansSelectionResponse,
)
from semant_demo.features.annotations.schemas import PostSpan
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

logger = logging.getLogger(__name__)

exp_router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────


def _ndjson_line(event: SuggestSpansChunkResult) -> bytes:
    """Serialize one event as a single NDJSON line (UTF-8 with trailing \\n)."""
    return (event.model_dump_json() + "\n").encode("utf-8")


async def _load_tag_dicts(
    searcher: WeaviateAbstraction, tag_ids: list[str]
) -> list[dict[str, Any]]:
    """
    Resolve raw tag dicts (id/name/definition/examples) for the given tag UUIDs.
    Tags that cannot be resolved are skipped.
    """
    out: list[dict[str, Any]] = []
    for tid in tag_ids:
        try:
            tag = await searcher.tag.read(UUID(tid))
        except Exception:
            tag = None
        if tag is None:
            logger.warning("Tag %s not found, skipping", tid)
            continue
        out.append({
            "id": str(tag.id),
            "name": tag.name,
            "definition": tag.definition,
            "examples": list(tag.examples or []),
        })
    return out


async def _persist_proposal(
    annotations: AnnotationStore,
    *,
    chunk_id: str,
    chunk_length: int,
    tag_id: str,
    allowed_tag_ids: set[str],
    span_start: int,
    span_end: int,
    reason: str | None = None,
    confidence: float | None = None,
) -> tuple[schemas.TagSpan | None, str | None]:
    """
    Validate a provider proposal and persist it as an auto-typed span.

    Returns ``(span, None)`` when saved, or ``(None, reason)`` when it was not:
    a tag outside the request, invalid offsets, or a storage failure. A saved span whose
    chunk tag (used by tag-filtered search) could not be updated is ``(span, reason)``.
    """
    if tag_id not in allowed_tag_ids:
        return None, "tag outside the request"
    if span_start is None or span_end is None:
        return None, "invalid offsets"
    start = max(0, int(span_start))
    end = min(int(span_end), chunk_length)
    if end <= start:
        return None, "invalid offsets"
    try:
        result = await annotation_service.save_span(annotations, PostSpan(
            chunkId=str(chunk_id),
            tagId=str(tag_id),
            start=start,
            end=end,
            type=schemas.SpanType.auto,
            reason=reason,
            confidence=confidence,
        ))
        span = schemas.TagSpan(**result.model_dump(include=set(schemas.TagSpan.model_fields)))
        return span, ("search tag not updated" if result.failed else None)
    except Exception as e:
        logger.warning(
            "Failed to persist auto span (chunk=%s, tag=%s, start=%s, end=%s): %s",
            chunk_id, tag_id, start, end, e,
        )
        return None, "storage failure"


class _SaveTally:
    """Saved spans and unsaved proposals of one event, so failures are reported."""

    def __init__(self) -> None:
        self.spans: list[schemas.TagSpan] = []
        self.unsaved = 0
        self.reasons: set[str] = set()
        self.untagged = 0

    def add(self, saved: tuple[schemas.TagSpan | None, str | None]) -> None:
        span, reason = saved
        if span is not None:
            self.spans.append(span)
            if reason:
                self.untagged += 1
        else:
            self.unsaved += 1
            self.reasons.add(reason or "not saved")

    def event(self, chunk_id: str, error: str | None = None) -> SuggestSpansChunkResult:
        errors = [error] if error else []
        if self.unsaved:
            errors.append(f"{self.unsaved} proposal(s) not saved ({', '.join(sorted(self.reasons))})")
        if self.untagged:
            errors.append(f"{self.untagged} saved proposal(s) not yet findable by tag search")
        return SuggestSpansChunkResult(
            chunk_id=chunk_id, spans=self.spans, error="; ".join(errors) or None, unsaved=self.unsaved,
        )


# ── Thorough mode ──────────────────────────────────────────────────────────

# Topicer's internal OpenAI semaphore is set to 10, so we match that to
# saturate it without overshooting.
_THOROUGH_CONCURRENCY = 10


async def _thorough_stream(
    searcher: WeaviateAbstraction,
    annotations: AnnotationStore,
    *,
    collection_id: str,
    document_id: str,
    tag_ids: list[str],
) -> AsyncGenerator[bytes, None]:
    """Yield NDJSON events for the thorough variant.

    Per-chunk Topicer calls are dispatched concurrently (bounded by
    :data:`_THOROUGH_CONCURRENCY`); results are streamed to the client in
    completion order (not original chunk order).
    """
    tags = await _load_tag_dicts(searcher, tag_ids)
    if not tags:
        return
    allowed_tag_ids = {t["id"] for t in tags}

    chunks = await searcher.userCollection.read_all_chunks_by_document(
        document_id, collection_id,
    )
    if not chunks:
        return

    sem = asyncio.Semaphore(_THOROUGH_CONCURRENCY)

    async def process_chunk(
        client, chunk,
    ) -> SuggestSpansChunkResult:
        async with sem:
            tally = _SaveTally()
            err: str | None = None
            try:
                proposals = await propose_for_text_chunk(
                    client,
                    chunk_id=str(chunk.id),
                    chunk_text=chunk.text,
                    tags=tags,
                )
            except TopicerError as e:
                err = f"topicer: {e}"
                proposals = []

            for proposal in proposals:
                tag_obj = proposal.get("tag") or {}
                tag_id = tag_obj.get("id")
                if not tag_id:
                    continue
                tally.add(await _persist_proposal(
                    annotations,
                    chunk_id=str(chunk.id),
                    chunk_length=len(chunk.text or ""),
                    tag_id=str(tag_id),
                    allowed_tag_ids=allowed_tag_ids,
                    span_start=proposal.get("span_start"),
                    span_end=proposal.get("span_end"),
                    reason=proposal.get("reason"),
                    confidence=proposal.get("confidence"),
                ))

            return tally.event(str(chunk.id), err)

    async with topicer_client() as client:
        tasks = [
            asyncio.create_task(process_chunk(client, chunk))
            for chunk in chunks
        ]
        try:
            for coro in asyncio.as_completed(tasks):
                result = await coro
                yield _ndjson_line(result)
        finally:
            # On client disconnect / cancellation, abort any still-running
            # Topicer calls so we free up the upstream slots immediately.
            for t in tasks:
                if not t.done():
                    t.cancel()


# ── Optimized mode ─────────────────────────────────────────────────────────


async def _optimized_stream(
    searcher: WeaviateAbstraction,
    annotations: AnnotationStore,
    *,
    collection_id: str,
    document_id: str,
    tag_ids: list[str],
) -> AsyncGenerator[bytes, None]:
    """Yield NDJSON events for the optimized variant."""
    tags = await _load_tag_dicts(searcher, tag_ids)
    if not tags:
        return
    allowed_tag_ids = {t["id"] for t in tags}

    # The document's chunks in this collection: the only chunks proposals may be
    # saved on (Topicer returns chunk ids itself), and their lengths for validation.
    collection_chunks = await searcher.userCollection.read_all_chunks_by_document(
        document_id, collection_id,
    )
    chunk_text_by_id: dict[str, str] = {str(c.id): (c.text or "") for c in collection_chunks}

    async with topicer_client() as client:
        for tag in tags:
            try:
                async for event in propose_for_db_stream(
                    client,
                    tag=tag,
                    collection_id=collection_id,
                    document_id=document_id,
                ):
                    chunk_id = str(event.get("id") or "")
                    if not chunk_id:
                        continue
                    proposals = event.get("tag_span_proposals") or []
                    tally = _SaveTally()
                    if chunk_id not in chunk_text_by_id:
                        # Not a chunk of this document in this collection: save nothing.
                        tally.unsaved = len(proposals)
                        tally.reasons.add("chunk outside the collection")
                        proposals = []
                    for proposal in proposals:
                        tag_obj = proposal.get("tag") or {}
                        proposal_tag_id = str(tag_obj.get("id") or tag["id"])
                        tally.add(await _persist_proposal(
                            annotations,
                            chunk_id=chunk_id,
                            chunk_length=len(chunk_text_by_id[chunk_id]),
                            tag_id=proposal_tag_id,
                            allowed_tag_ids=allowed_tag_ids,
                            span_start=proposal.get("span_start"),
                            span_end=proposal.get("span_end"),
                            reason=proposal.get("reason"),
                            confidence=proposal.get("confidence"),
                        ))

                    yield _ndjson_line(tally.event(chunk_id))
                    await asyncio.sleep(0)
            except TopicerError as e:
                yield _ndjson_line(SuggestSpansChunkResult(
                    chunk_id="",
                    spans=[],
                    error=f"topicer (tag={tag.get('name')}): {e}",
                ))


# ── Selection mode ─────────────────────────────────────────────────────────


async def _selection_stream(
    searcher: WeaviateAbstraction,
    annotations: AnnotationStore,
    *,
    chunk_ids: list[str],
    selection_start: int,
    selection_end: int,
    tag_ids: list[str],
) -> AsyncGenerator[bytes, None]:
    """Yield NDJSON events for a selection-scoped run.

    The Topicer call itself is not streamed (the per-text endpoint returns
    one batch), but each proposal is persisted and emitted individually so
    the UI can render suggestions as they're being saved. The Topicer call
    is wrapped in a task so a client disconnect / cancel cancels the
    upstream HTTP request promptly.
    """
    tags = await _load_tag_dicts(searcher, tag_ids)
    if not tags:
        return
    allowed_tag_ids = {t["id"] for t in tags}

    # Fetch text of every chunk in the selection so we can concatenate
    # them and compute the slice the LLM should see, plus the cumulative
    # offsets used to remap each proposal back to its starting chunk.
    chunks_collection = searcher.client.collections.get(
        searcher.collectionNames.chunks_collection_name
    )
    chunk_texts: list[str] = []
    for cid in chunk_ids:
        obj = await chunks_collection.query.fetch_object_by_id(cid)
        if obj is None:
            yield _ndjson_line(SuggestSpansChunkResult(
                chunk_id=cid, spans=[], error=f"Chunk {cid} not found",
            ))
            return
        chunk_texts.append(obj.properties.get("text") or "")

    # ``cum_offsets[i]`` = char offset of ``chunk_ids[i]`` from start of
    # the concatenation. ``cum_offsets[len(chunk_ids)]`` = total length.
    cum_offsets: list[int] = [0]
    for text in chunk_texts:
        cum_offsets.append(cum_offsets[-1] + len(text))
    total_length = cum_offsets[-1]

    sel_start = max(0, selection_start)
    sel_end = min(total_length, selection_end)
    if sel_end <= sel_start:
        return
    selected_text = "".join(chunk_texts)[sel_start:sel_end]

    def _anchor_for(span_start: int) -> tuple[int, int] | None:
        """Return (chunk_index, local_start) for a concat-coord offset."""
        for i in range(len(chunk_ids)):
            chunk_start = cum_offsets[i]
            chunk_end = cum_offsets[i + 1]
            # Last chunk gets the inclusive upper bound so a span ending
            # exactly at total_length still maps to the last chunk.
            if span_start < chunk_end or (i == len(chunk_ids) - 1 and span_start <= chunk_end):
                return i, span_start - chunk_start
        return None

    async with topicer_client() as client:
        # Wrap the Topicer call in a task so a client disconnect (StreamingResponse
        # generator cancellation) cancels the upstream HTTP request promptly.
        topicer_task = asyncio.create_task(
            propose_for_text_chunk(
                client,
                chunk_id=chunk_ids[0],
                chunk_text=selected_text,
                tags=tags,
            )
        )
        try:
            try:
                proposals = await topicer_task
            except TopicerError as e:
                yield _ndjson_line(SuggestSpansChunkResult(
                    chunk_id=chunk_ids[0], spans=[], error=f"topicer: {e}",
                ))
                return

            for proposal in proposals:
                tag_obj = proposal.get("tag") or {}
                tag_id = tag_obj.get("id")
                if not tag_id:
                    continue
                sub_start = proposal.get("span_start")
                sub_end = proposal.get("span_end")
                if sub_start is None or sub_end is None:
                    continue
                # Topicer offsets are relative to the substring we sent;
                # shift back into the concatenation coordinate system,
                # then clamp inside the user's highlighted range.
                concat_start = max(sel_start, sel_start + int(sub_start))
                concat_end = min(sel_end, sel_start + int(sub_end))
                if concat_end <= concat_start:
                    continue

                anchor = _anchor_for(concat_start)
                if anchor is None:
                    continue
                anchor_idx, local_start = anchor
                anchor_chunk_id = chunk_ids[anchor_idx]
                # ``end`` measured from the anchor chunk; may exceed the
                # anchor's text length when the proposal extends into
                # later chunks (cross-chunk auto span, same convention
                # as user-created cross-chunk spans).
                local_end = concat_end - cum_offsets[anchor_idx]
                # ``_persist_proposal`` clamps end to its ``chunk_length``
                # argument — pass the remaining concat length so we don't
                # accidentally truncate a cross-chunk span.
                remaining = total_length - cum_offsets[anchor_idx]

                tally = _SaveTally()
                tally.add(await _persist_proposal(
                    annotations,
                    chunk_id=anchor_chunk_id,
                    chunk_length=remaining,
                    tag_id=str(tag_id),
                    allowed_tag_ids=allowed_tag_ids,
                    span_start=local_start,
                    span_end=local_end,
                    reason=proposal.get("reason"),
                    confidence=proposal.get("confidence"),
                ))
                # One event per proposal: the saved span, or an unsaved count with the reason.
                yield _ndjson_line(tally.event(anchor_chunk_id))
        finally:
            if not topicer_task.done():
                topicer_task.cancel()


# ── Endpoints ──────────────────────────────────────────────────────────────


_NDJSON_MEDIA_TYPE = "application/x-ndjson"


@exp_router.post(
    "/api/ai/suggest_spans/thorough",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Stream of SuggestSpansChunkResult, one JSON object per line."
            ),
            "content": {_NDJSON_MEDIA_TYPE: {}},
        }
    },
)
async def suggest_spans_thorough(
    body: SuggestSpansRequest,
    searcher: WeaviateAbstraction = Depends(get_search),
    annotations: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
):
    """
    Thorough AI span suggestion: every collection chunk in the document is sent
    to the LLM together with all selected tags.

    Persists each accepted proposal as a span with type ``auto``. The endpoint
    streams NDJSON lines (``application/x-ndjson``); each line is a
    :class:`SuggestSpansChunkResult`.
    """
    if not body.tag_ids:
        raise HTTPException(status_code=400, detail="tag_ids must not be empty")
    # Checked before the stream starts, so a denied request makes no provider call.
    grant = await access.require_annotation_edit(searcher.userCollection, current_user, body.collection_id)
    await access.require_tags_in_collection(searcher.tag, body.tag_ids, grant.collection_id)
    document_id = await access.require_document_in_collection(searcher.userCollection, body.document_id, grant.collection_id)

    return StreamingResponse(
        _thorough_stream(
            searcher,
            annotations,
            collection_id=str(grant.collection_id),
            document_id=str(document_id),
            tag_ids=body.tag_ids,
        ),
        media_type=_NDJSON_MEDIA_TYPE,
    )


@exp_router.post(
    "/api/ai/suggest_spans/optimized",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Stream of SuggestSpansChunkResult, one JSON object per line."
            ),
            "content": {_NDJSON_MEDIA_TYPE: {}},
        }
    },
)
async def suggest_spans_optimized(
    body: SuggestSpansRequest,
    searcher: WeaviateAbstraction = Depends(get_search),
    annotations: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
):
    """
    Optimized AI span suggestion: per tag, the Topicer service uses vector
    similarity to pre-filter only the most relevant chunks before invoking the
    LLM. NDJSON results are streamed straight through to the client as they
    arrive.
    """
    if not body.tag_ids:
        raise HTTPException(status_code=400, detail="tag_ids must not be empty")
    # Checked before the stream starts, so a denied request makes no provider call.
    grant = await access.require_annotation_edit(searcher.userCollection, current_user, body.collection_id)
    await access.require_tags_in_collection(searcher.tag, body.tag_ids, grant.collection_id)
    document_id = await access.require_document_in_collection(searcher.userCollection, body.document_id, grant.collection_id)

    return StreamingResponse(
        _optimized_stream(
            searcher,
            annotations,
            collection_id=str(grant.collection_id),
            document_id=str(document_id),
            tag_ids=body.tag_ids,
        ),
        media_type=_NDJSON_MEDIA_TYPE,
    )


@exp_router.post(
    "/api/ai/suggest_spans/selection",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Stream of SuggestSpansChunkResult, one JSON object per line. "
                "One event per persisted auto span; a final event with "
                "empty ``spans`` and a populated ``error`` is emitted on "
                "Topicer failure."
            ),
            "content": {_NDJSON_MEDIA_TYPE: {}},
        }
    },
)
async def suggest_spans_selection(
    body: SuggestSpansSelectionRequest,
    searcher: WeaviateAbstraction = Depends(get_search),
    annotations: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
):
    """
    Run AI span suggestion on a single user-selected passage that may
    span multiple consecutive chunks. The frontend sends the chunk IDs
    in document order; offsets are measured against the concatenation of
    their text.

    The endpoint streams NDJSON
    (``application/x-ndjson``) — one :class:`SuggestSpansChunkResult` per
    persisted span — so the UI can render suggestions incrementally and
    abort the run mid-flight by closing the connection.

    Each persisted span is anchored on the chunk that contains its
    *start* offset (mirroring how non-AI cross-chunk spans are stored),
    not on the first chunk of the selection.
    """
    if not body.tag_ids:
        raise HTTPException(status_code=400, detail="tag_ids must not be empty")
    if not body.chunk_ids:
        raise HTTPException(status_code=400, detail="chunk_ids must not be empty")
    if body.selection_end <= body.selection_start:
        raise HTTPException(
            status_code=400,
            detail="selection_end must be greater than selection_start",
        )
    # Checked before the stream starts, so a denied request makes no provider call.
    grant = await access.require_annotation_edit(searcher.userCollection, current_user, body.collection_id)
    await access.require_tags_in_collection(searcher.tag, body.tag_ids, grant.collection_id)
    await access.require_document_in_collection(searcher.userCollection, body.document_id, grant.collection_id)
    await access.require_chunks_in_collection(searcher.userCollection, body.chunk_ids, grant.collection_id, body.document_id)

    return StreamingResponse(
        _selection_stream(
            searcher,
            annotations,
            chunk_ids=body.chunk_ids,
            selection_start=body.selection_start,
            selection_end=body.selection_end,
            tag_ids=body.tag_ids,
        ),
        media_type=_NDJSON_MEDIA_TYPE,
    )


@exp_router.post(
    "/api/ai/auto_spans/delete",
    response_model=DeleteAutoSpansResponse,
)
async def delete_auto_spans(
    body: DeleteAutoSpansRequest,
    annotations: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> DeleteAutoSpansResponse:
    """
    Bulk-delete unresolved AI proposals (``type == 'auto'``) within a single
    (collection, document) for the given tag UUIDs.

    Useful for cleaning up suggestions the user did not get around to
    approving or rejecting. Best effort: ``succeeded`` lists the deleted spans and
    ``failed`` those that could not be deleted (``delete_span``) and the chunk tag
    updates that failed (``update_chunk_tags``, item ``chunk_id:tag_id``).
    """
    result = await annotation_service.delete_suggestions_in_document(
        annotations, current_user, body.collection_id, body.document_id, body.tag_ids)
    return DeleteAutoSpansResponse(**result.model_dump(), deleted=len(result.succeeded))
