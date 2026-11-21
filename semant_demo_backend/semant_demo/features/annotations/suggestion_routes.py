"""
Routes for AI-assisted span suggestion; the workflow lives in ``suggestions.py``.

The suggestion endpoints stream NDJSON (``application/x-ndjson``) so the frontend can
render suggestions progressively: ``SuggestSpansChunkResult`` lines (``"event":
"result"``) as proposals are stored, then one ``SuggestSpansRunEnd`` line (``"event":
"end"``) with the outcome. A stream without the end line was interrupted.

- ``POST /api/ai/suggest_spans/thorough`` — every collection chunk of the document is
  sent to Topicer's ``/v1/tags/propose/texts`` with all selected tags.
- ``POST /api/ai/suggest_spans/optimized`` — per tag, only the chunks most similar to
  it (ranked by semANT's hybrid search, #792) are sent to ``/v1/tags/propose/texts``.
- ``POST /api/ai/suggest_spans/selection`` — one user-selected passage.
- ``GET /api/ai/topicer_configs`` — the Topicer configurations a request may name in
  ``config_name`` (#189); without one, the server default is used.

Access is checked before the stream starts (404/401/403 as for other annotation writes,
400 for invalid requests). Each chunk, tag or selection is then one operation of the
account's daily AI allowance (#408): the first is admitted before the stream starts (a
refusal is the structured 429), later ones as the run proceeds; a later refusal stops the
run with ``stop_reason == "quota_exhausted"`` in its end line. Closing the connection
stops the remaining work; stored suggestions remain.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import partial
import logging

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from semant_demo.adapters.topicer.client import TopicerClient
from semant_demo.adapters.sql.ai_runs import AiRunRepository
from semant_demo.features.annotations import service, suggestions
from semant_demo.features.user_collections import access
from semant_demo.features.annotations.candidates import rank_candidates
from semant_demo.features.annotations.schemas import (
    AiSuggestionRunInfo, DeleteAutoSpansRequest, DeleteAutoSpansResponse,
    SuggestSpansRequest, SuggestSpansSelectionRequest, TopicerConfigsResponse,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.quota.principal import get_allowance_budget
from semant_demo.features.quota.schemas import QUOTA_EXHAUSTED_RESPONSES
from semant_demo.features.quota.service import AllowanceBudget
from semant_demo.features.search.service import SearchBackends
from semant_demo.routes.dependencies import (
    get_ai_run_history, get_annotation_store, get_search_backends, get_topicer,
)
from semant_demo.routes.streaming import OperationStreamingResponse
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

exp_router = APIRouter()
logger = logging.getLogger(__name__)

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


async def _recorded_lines(run: suggestions.SuggestionRun, history: AiRunRepository) -> AsyncGenerator[bytes, None]:
    """Finish the SQL record even when the client closes the stream (#563)."""
    try:
        async with aclosing(_lines(run.events())) as lines:
            async for line in lines:
                yield line
    finally:
        # _lines closes run.events() before we inspect the final summary.
        with anyio.CancelScope(shield=True):
            summary = run.summary
            try:
                await history.finish(run.run_id, summary.outcome.value if summary else "cancelled",
                                     summary.saved if summary else 0)
            except Exception:
                logger.exception("Failed to save AI run completion")


def _run_response(run: suggestions.SuggestionRun, history: AiRunRepository | None = None) -> OperationStreamingResponse:
    """NDJSON stream; close the run on disconnect and retain its metadata."""
    lines = _recorded_lines(run, history) if history and run.run_id else _lines(run.events())
    return OperationStreamingResponse(lines, run, _NDJSON_MEDIA_TYPE)


async def _registered_response(run: suggestions.SuggestionRun, body: SuggestSpansRequest | SuggestSpansSelectionRequest,
                               user: User, history: AiRunRepository, mode: str) -> OperationStreamingResponse:
    if not run.run_id or not run.config_name:
        await run.release()
        raise RuntimeError("AI run provenance unavailable")
    try:
        await history.start(run.run_id, body.collection_id, body.document_id, user.id,
                            mode, run.config_name, body.tag_ids)
    except Exception:
        await run.release()  # Return the already reserved allowance if recording failed.
        raise
    return _run_response(run, history)


async def _lines(events: AsyncGenerator[suggestions.SuggestionEvent, None]) -> AsyncGenerator[bytes, None]:
    async with aclosing(events):
        async for event in events:
            yield (event.model_dump_json() + "\n").encode("utf-8")


def _stream_responses(description: str) -> dict:
    return {200: {"description": description, "content": {_NDJSON_MEDIA_TYPE: {}}}, **QUOTA_EXHAUSTED_RESPONSES}


_STREAM_DESCRIPTION = (
    "Stream of SuggestSpansChunkResult, one JSON object per line, ended by one "
    "SuggestSpansRunEnd line (``event == 'end'``)."
)


@exp_router.get("/api/ai/suggestion_runs", response_model=list[AiSuggestionRunInfo])
async def list_suggestion_runs(
    collection_id: str,
    document_id: str,
    annotations: AnnotationStore = Depends(get_annotation_store),
    history: AiRunRepository = Depends(get_ai_run_history),
    current_user: User = Depends(current_active_user),
) -> list[AiSuggestionRunInfo]:
    """Read run history for an accessible collection/document, newest first."""
    grant = await access.require_collection_read(annotations.collections, current_user, collection_id)
    document = await access.require_document_in_collection(annotations.collections, document_id, grant.collection_id)
    return await history.list_document(str(grant.collection_id), str(document))


@exp_router.get("/api/ai/topicer_configs", response_model=TopicerConfigsResponse)
async def get_topicer_configs(
    provider: TopicerClient = Depends(get_topicer),
    current_user: User = Depends(current_active_user),
) -> TopicerConfigsResponse:
    """
    The Topicer configurations (AI models) that suggestion requests may name in
    ``config_name``, as Topicer lists them, and the server default. 503 when Topicer
    cannot be asked.
    """
    return TopicerConfigsResponse(configs=await suggestions.topicer_configs(provider),
                                  default_config=provider.config_name)


@exp_router.post(
    "/api/ai/suggest_spans/thorough",
    response_class=StreamingResponse,
    responses=_stream_responses(_STREAM_DESCRIPTION),
)
async def suggest_spans_thorough(
    body: SuggestSpansRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    provider: TopicerClient = Depends(get_topicer),
    current_user: User = Depends(current_active_user),
    budget: AllowanceBudget = Depends(get_allowance_budget),
    history: AiRunRepository = Depends(get_ai_run_history),
):
    """
    Thorough AI span suggestion: every collection chunk in the document is sent
    to the LLM together with all selected tags.

    Persists each accepted proposal as a span with type ``auto``. The endpoint
    streams NDJSON lines (``application/x-ndjson``): one
    :class:`SuggestSpansChunkResult` per chunk, then a :class:`SuggestSpansRunEnd`.
    """
    run = await suggestions.prepare_document_run(store, provider, current_user, body, "thorough", budget)
    return await _registered_response(run, body, current_user, history, "thorough")


@exp_router.post(
    "/api/ai/suggest_spans/optimized",
    response_class=StreamingResponse,
    responses=_stream_responses(_STREAM_DESCRIPTION),
)
async def suggest_spans_optimized(
    body: SuggestSpansRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    provider: TopicerClient = Depends(get_topicer),
    backends: SearchBackends = Depends(get_search_backends),
    current_user: User = Depends(current_active_user),
    budget: AllowanceBudget = Depends(get_allowance_budget),
    history: AiRunRepository = Depends(get_ai_run_history),
):
    """
    Optimized AI span suggestion: per tag, a hybrid search picks the document's chunks
    most similar to the tag, at most ``TOPICER_MAX_CHUNKS_PER_TAG`` (never set by the
    caller), and only those are sent to the LLM with that tag. Results are streamed as
    they arrive, then a :class:`SuggestSpansRunEnd` that lists the tags that reached the
    limit.
    """
    run = await suggestions.prepare_document_run(store, provider, current_user, body, "optimized", budget,
                                                 partial(rank_candidates, backends))
    return await _registered_response(run, body, current_user, history, "optimized")


@exp_router.post(
    "/api/ai/suggest_spans/selection",
    response_class=StreamingResponse,
    responses=_stream_responses(
        "Stream of SuggestSpansChunkResult, one JSON object per line. "
        "One event per proposal (the persisted auto span, or ``unsaved`` with the reason); "
        "an event with empty ``spans`` and a populated ``error`` on Topicer failure; "
        "ended by one SuggestSpansRunEnd line (``event == 'end'``)."
    ),
)
async def suggest_spans_selection(
    body: SuggestSpansSelectionRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    provider: TopicerClient = Depends(get_topicer),
    current_user: User = Depends(current_active_user),
    budget: AllowanceBudget = Depends(get_allowance_budget),
    history: AiRunRepository = Depends(get_ai_run_history),
):
    """
    Run AI span suggestion on a single user-selected passage that may
    span multiple chunks of the collection. The frontend sends the chunk IDs
    in document order; offsets are measured in UTF-16 code units against the
    concatenation of their text.

    The endpoint streams NDJSON
    (``application/x-ndjson``) — one :class:`SuggestSpansChunkResult` per
    proposal, then a :class:`SuggestSpansRunEnd` — so the UI can render
    suggestions incrementally and abort the run mid-flight by closing the connection.

    Each persisted span is anchored on the chunk that contains its
    *start* offset (mirroring how non-AI cross-chunk spans are stored),
    not on the first chunk of the selection.
    """
    run = await suggestions.prepare_selection_run(store, provider, current_user, body, budget)
    return await _registered_response(run, body, current_user, history, "selection")


@exp_router.post(
    "/api/ai/auto_spans/delete",
    response_model=DeleteAutoSpansResponse,
)
async def delete_auto_spans(
    body: DeleteAutoSpansRequest,
    annotations: AnnotationStore = Depends(get_annotation_store),
    current_user: User = Depends(current_active_user),
) -> DeleteAutoSpansResponse:
    """Delete unresolved AI spans by tag (legacy cleanup) or explicitly selected ids."""
    if body.span_ids is not None:
        result = await service.delete_selected_suggestions_in_document(
            annotations, current_user, body.collection_id, body.document_id,
            body.span_ids, body.expected_versions)
    else:
        result = await service.delete_suggestions_in_document(
            annotations, current_user, body.collection_id, body.document_id, body.tag_ids or [])
    return DeleteAutoSpansResponse(**result.model_dump(), deleted=len(result.succeeded))
