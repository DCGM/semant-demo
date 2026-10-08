"""
Route for span-discussion chat; the workflow lives in ``span_chat.py``.

``POST /api/ai/discuss_span`` streams an assistant reply (NDJSON) reasoning about
whether a single span fits its tag. Each line is a :class:`SpanChatDelta`:

- ``{"delta": "..."}`` — incremental text from the assistant
- ``{"done": true}`` — final marker; close the stream client-side
- ``{"error": "..."}`` — an error after the stream started
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from semant_demo.adapters.llm.responses import ResponsesChat
from semant_demo.config import Config
from semant_demo.features.annotations.schemas import DiscussSpanRequest, SpanChatDelta
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.annotations.span_chat import SpanDiscussion, prepare_discussion
from semant_demo.routes.dependencies import get_annotation_store, get_config, get_span_chat
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

logger = logging.getLogger(__name__)

exp_router = APIRouter()

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


def _ndjson(event: SpanChatDelta) -> bytes:
    return (event.model_dump_json(exclude_none=True) + "\n").encode("utf-8")


async def _stream(discussion: SpanDiscussion) -> AsyncGenerator[bytes, None]:
    try:
        async for delta in discussion.deltas():
            yield _ndjson(SpanChatDelta(delta=delta))
    except Exception as e:
        logger.exception("span discussion stream failed: %s", e)
        yield _ndjson(SpanChatDelta(error=str(e)))
        return
    yield _ndjson(SpanChatDelta(done=True))


@exp_router.post("/api/ai/discuss_span", response_class=StreamingResponse)
async def discuss_span(
    body: DiscussSpanRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    provider: ResponsesChat = Depends(get_span_chat),
    config: Config = Depends(get_config),
    current_user: User = Depends(current_active_user),
):
    """
    Stream an assistant reply discussing whether the given span fits its tag.

    The request body carries the full chat history; the backend resolves
    span / document / tag context and prepends it as a system message before
    forwarding to the configured OpenAI-compatible Chat Completions endpoint.
    """
    discussion = await prepare_discussion(store, current_user, body, provider,
                                          context_chars=config.SPAN_CHAT_CONTEXT_CHARS,
                                          history_limit=config.SPAN_CHAT_HISTORY_LIMIT)
    return StreamingResponse(_stream(discussion), media_type=_NDJSON_MEDIA_TYPE)
