"""
Routes for span-discussion chat.

``POST /api/ai/discuss_span`` — streams an assistant reply (NDJSON) reasoning
about whether a single :class:`TagSpan` fits its tag, given the document's
metadata and the chunk text surrounding the span.

The frontend re-sends the full chat history on each turn (so the backend is
stateless w.r.t. conversation memory). Each NDJSON line is a
:class:`SpanChatDelta` event:

- ``{"delta": "..."}`` — incremental text from the assistant
- ``{"done": true}`` — final marker; close the stream client-side
- ``{"error": "..."}`` — surfacing late errors that occur mid-stream
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from semant_demo.ai_assistance.span_chat import stream_span_discussion
from semant_demo.routes.dependencies import get_search
from semant_demo.schema.ai_assistance import (
    DiscussSpanRequest,
    SpanChatDelta,
)
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

logger = logging.getLogger(__name__)

exp_router = APIRouter()

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


def _ndjson(event: SpanChatDelta) -> bytes:
    return (event.model_dump_json(exclude_none=True) + "\n").encode("utf-8")


async def _stream(
    searcher: WeaviateAbstraction,
    *,
    span_id: str,
    collection_id: str,
    body: DiscussSpanRequest,
) -> AsyncGenerator[bytes, None]:
    try:
        async for delta in stream_span_discussion(
            searcher,
            span_id=span_id,
            collection_id=collection_id,
            messages=body.messages,
        ):
            yield _ndjson(SpanChatDelta(delta=delta))
    except Exception as e:
        logger.exception("span discussion stream failed: %s", e)
        yield _ndjson(SpanChatDelta(error=str(e)))
        return
    yield _ndjson(SpanChatDelta(done=True))


@exp_router.post("/api/ai/discuss_span", response_class=StreamingResponse)
async def discuss_span(
    body: DiscussSpanRequest,
    searcher: WeaviateAbstraction = Depends(get_search),
    current_user: User = Depends(current_active_user),
):
    """
    Stream an assistant reply discussing whether the given span fits its tag.

    The request body carries the full chat history; the backend resolves
    span / document / tag context and prepends it as a system message before
    forwarding to the configured OpenAI-compatible Chat Completions endpoint.
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")
    if body.messages[-1].role != "user":
        raise HTTPException(
            status_code=400, detail="last message must be from the user"
        )

    return StreamingResponse(
        _stream(
            searcher,
            span_id=body.span_id,
            collection_id=body.collection_id,
            body=body,
        ),
        media_type=_NDJSON_MEDIA_TYPE,
    )
