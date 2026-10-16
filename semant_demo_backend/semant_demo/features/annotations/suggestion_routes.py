"""
Routes for AI-assisted span suggestion; the workflow lives in ``suggestions.py``.

The suggestion endpoints stream NDJSON (``application/x-ndjson``) so the frontend can
render suggestions progressively: ``SuggestSpansChunkResult`` lines (``"event":
"result"``) as proposals are stored, then one ``SuggestSpansRunEnd`` line (``"event":
"end"``) with the outcome. A stream without the end line was interrupted.

- ``POST /api/ai/suggest_spans/thorough`` — every collection chunk of the document is
  sent to Topicer's ``/v1/tags/propose/texts`` with all selected tags.
- ``POST /api/ai/suggest_spans/optimized`` — per tag, Topicer's
  ``/v1/tags/propose/db/stream`` pre-filters chunks by vector similarity.
- ``POST /api/ai/suggest_spans/selection`` — one user-selected passage.

Access is checked before the stream starts (404/401/403 as for other annotation writes,
400 for invalid requests). Closing the connection stops the remaining work; stored
suggestions remain.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from semant_demo.adapters.topicer.client import TopicerClient
from semant_demo.features.annotations import service, suggestions
from semant_demo.features.annotations.schemas import (
    DeleteAutoSpansRequest, DeleteAutoSpansResponse, SuggestSpansRequest, SuggestSpansSelectionRequest,
)
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.routes.dependencies import get_annotation_store, get_topicer
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

exp_router = APIRouter()

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


class _RunResponse(StreamingResponse):
    """NDJSON stream of a suggestion run that is closed however the response ends.

    Starlette cancels a response whose client disconnected but does not close its
    iterator; closing it here cancels and awaits the run's remaining work.
    """

    def __init__(self, run: suggestions.SuggestionRun):
        self._events = run.events()
        super().__init__(self._lines(), media_type=_NDJSON_MEDIA_TYPE)

    async def _lines(self) -> AsyncGenerator[bytes, None]:
        async for event in self._events:
            yield (event.model_dump_json() + "\n").encode("utf-8")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._events.aclose()


def _stream_responses(description: str) -> dict:
    return {200: {"description": description, "content": {_NDJSON_MEDIA_TYPE: {}}}}


_STREAM_DESCRIPTION = (
    "Stream of SuggestSpansChunkResult, one JSON object per line, ended by one "
    "SuggestSpansRunEnd line (``event == 'end'``)."
)


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
):
    """
    Thorough AI span suggestion: every collection chunk in the document is sent
    to the LLM together with all selected tags.

    Persists each accepted proposal as a span with type ``auto``. The endpoint
    streams NDJSON lines (``application/x-ndjson``): one
    :class:`SuggestSpansChunkResult` per chunk, then a :class:`SuggestSpansRunEnd`.
    """
    run = await suggestions.prepare_document_run(store, provider, current_user, body, "thorough")
    return _RunResponse(run)


@exp_router.post(
    "/api/ai/suggest_spans/optimized",
    response_class=StreamingResponse,
    responses=_stream_responses(_STREAM_DESCRIPTION),
)
async def suggest_spans_optimized(
    body: SuggestSpansRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    provider: TopicerClient = Depends(get_topicer),
    current_user: User = Depends(current_active_user),
):
    """
    Optimized AI span suggestion: per tag, the Topicer service uses vector
    similarity to pre-filter only the most relevant chunks before invoking the
    LLM. Results are streamed as they arrive, then a :class:`SuggestSpansRunEnd`.
    """
    run = await suggestions.prepare_document_run(store, provider, current_user, body, "optimized")
    return _RunResponse(run)


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
    run = await suggestions.prepare_selection_run(store, provider, current_user, body)
    return _RunResponse(run)


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
    result = await service.delete_suggestions_in_document(
        annotations, current_user, body.collection_id, body.document_id, body.tag_ids)
    return DeleteAutoSpansResponse(**result.model_dump(), deleted=len(result.succeeded))
