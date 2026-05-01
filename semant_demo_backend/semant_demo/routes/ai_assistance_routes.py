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
from semant_demo.routes.dependencies import get_search
from semant_demo.schema.ai_assistance import (
    DeleteAutoSpansRequest,
    DeleteAutoSpansResponse,
    SuggestSpansChunkResult,
    SuggestSpansRequest,
    SuggestSpansSelectionRequest,
    SuggestSpansSelectionResponse,
)
from semant_demo.schema.spans import PostSpan
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
    searcher: WeaviateAbstraction,
    *,
    chunk_id: str,
    chunk_length: int,
    tag_id: str,
    span_start: int,
    span_end: int,
    reason: str | None = None,
    confidence: float | None = None,
) -> schemas.TagSpan | None:
    """
    Validate offsets and persist a single proposal as an auto-typed span.

    Returns the created TagSpan, or None on validation failure.
    """
    if span_start is None or span_end is None:
        return None
    start = max(0, int(span_start))
    end = min(int(span_end), chunk_length)
    if end <= start:
        return None
    try:
        return await searcher.span.create(PostSpan(
            chunkId=str(chunk_id),
            tagId=str(tag_id),
            start=start,
            end=end,
            type=schemas.SpanType.auto,
            reason=reason,
            confidence=confidence,
        ))
    except Exception as e:
        logger.warning(
            "Failed to persist auto span (chunk=%s, tag=%s, start=%s, end=%s): %s",
            chunk_id, tag_id, start, end, e,
        )
        return None


# ── Thorough mode ──────────────────────────────────────────────────────────

# Topicer's internal OpenAI semaphore is set to 10, so we match that to
# saturate it without overshooting.
_THOROUGH_CONCURRENCY = 10


async def _thorough_stream(
    searcher: WeaviateAbstraction,
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
            new_spans: list[schemas.TagSpan] = []
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
                span = await _persist_proposal(
                    searcher,
                    chunk_id=str(chunk.id),
                    chunk_length=len(chunk.text or ""),
                    tag_id=str(tag_id),
                    span_start=proposal.get("span_start"),
                    span_end=proposal.get("span_end"),
                    reason=proposal.get("reason"),
                    confidence=proposal.get("confidence"),
                )
                if span is not None:
                    new_spans.append(span)

            return SuggestSpansChunkResult(
                chunk_id=str(chunk.id),
                spans=new_spans,
                error=err,
            )

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
    *,
    collection_id: str,
    document_id: str,
    tag_ids: list[str],
) -> AsyncGenerator[bytes, None]:
    """Yield NDJSON events for the optimized variant."""
    tags = await _load_tag_dicts(searcher, tag_ids)
    if not tags:
        return

    # We need chunk lengths to validate proposal offsets. Load all document
    # chunks (including those outside the current collection) once, since
    # Topicer returns chunk ids that we need to look up.
    all_chunks = await searcher.userCollection.read_all_chunks_by_document(
        document_id, collection_id,
    )
    chunk_text_by_id: dict[str, str] = {str(c.id): (c.text or "") for c in all_chunks}

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
                    chunk_length = len(
                        chunk_text_by_id.get(chunk_id) or event.get("text") or ""
                    )

                    new_spans: list[schemas.TagSpan] = []
                    for proposal in event.get("tag_span_proposals") or []:
                        tag_obj = proposal.get("tag") or {}
                        proposal_tag_id = str(tag_obj.get("id") or tag["id"])
                        span = await _persist_proposal(
                            searcher,
                            chunk_id=chunk_id,
                            chunk_length=chunk_length,
                            tag_id=proposal_tag_id,
                            span_start=proposal.get("span_start"),
                            span_end=proposal.get("span_end"),
                            reason=proposal.get("reason"),
                            confidence=proposal.get("confidence"),
                        )
                        if span is not None:
                            new_spans.append(span)

                    yield _ndjson_line(SuggestSpansChunkResult(
                        chunk_id=chunk_id,
                        spans=new_spans,
                    ))
                    await asyncio.sleep(0)
            except TopicerError as e:
                yield _ndjson_line(SuggestSpansChunkResult(
                    chunk_id="",
                    spans=[],
                    error=f"topicer (tag={tag.get('name')}): {e}",
                ))


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

    return StreamingResponse(
        _thorough_stream(
            searcher,
            collection_id=body.collection_id,
            document_id=body.document_id,
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

    return StreamingResponse(
        _optimized_stream(
            searcher,
            collection_id=body.collection_id,
            document_id=body.document_id,
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

    return StreamingResponse(
        _selection_stream(
            searcher,
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
    searcher: WeaviateAbstraction = Depends(get_search),
    current_user: User = Depends(current_active_user),
) -> DeleteAutoSpansResponse:
    """
    Bulk-delete unresolved AI proposals (``type == 'auto'``) within a single
    (collection, document) for the given tag UUIDs.

    Useful for cleaning up suggestions the user did not get around to
    approving or rejecting.
    """
    if not body.tag_ids:
        return DeleteAutoSpansResponse(deleted=0)

    deleted = await searcher.span.delete_auto_spans_in_scope(
        collection_id=body.collection_id,
        document_id=body.document_id,
        tag_ids=body.tag_ids,
    )
    return DeleteAutoSpansResponse(deleted=deleted)
