"""
Route for span-discussion chat; the workflow lives in ``span_chat.py``.

``POST /api/ai/discuss_span`` streams an assistant reply (NDJSON) reasoning about
whether a single span fits its tag. Each line is a :class:`SpanChatDelta`:

- ``{"delta": "..."}`` — incremental text from the assistant
- ``{"done": true}`` — final marker; close the stream client-side
- ``{"error": "..."}`` — an error after the stream started

The reply is one AI operation, admitted against the caller's daily allowance before the
stream starts (a refusal is a 429) and settled when the stream ends, also when the client
disconnects.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from semant_demo.adapters.llm.gateway import FeatureChat, OperationScope
from semant_demo.adapters.llm.usage import LlmRequestRefused
from semant_demo.config import Config
from semant_demo.features.annotations.schemas import DiscussSpanRequest, SpanChatDelta
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.annotations.span_chat import SpanDiscussion, prepare_discussion
from semant_demo.features.quota.principal import get_allowance_budget
from semant_demo.features.quota.schemas import QUOTA_EXHAUSTED_RESPONSES
from semant_demo.features.quota.service import AllowanceBudget
from semant_demo.routes.dependencies import get_annotation_store, get_config, get_span_chat
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

logger = logging.getLogger(__name__)

exp_router = APIRouter()

_NDJSON_MEDIA_TYPE = "application/x-ndjson"
STREAM_FAILED_MESSAGE = "The assistant reply failed."


def _ndjson(event: SpanChatDelta) -> bytes:
    return (event.model_dump_json(exclude_none=True) + "\n").encode("utf-8")


async def _stream(discussion: SpanDiscussion, operation: OperationScope) -> AsyncGenerator[bytes, None]:
    async with operation:
        try:
            async for delta in discussion.deltas():
                yield _ndjson(SpanChatDelta(delta=delta))
        except Exception as e:
            # Provider and storage errors may echo the conversation or credentials; a server
            # refusal (e.g. a conversation above the input limit) has a safe message.
            logger.error("Span discussion stream failed: %s", type(e).__name__)
            message = str(e) if isinstance(e, LlmRequestRefused) else STREAM_FAILED_MESSAGE
            yield _ndjson(SpanChatDelta(error=message))
            return
    yield _ndjson(SpanChatDelta(done=True))


@exp_router.post("/api/ai/discuss_span", response_class=StreamingResponse, responses=QUOTA_EXHAUSTED_RESPONSES)
async def discuss_span(
    body: DiscussSpanRequest,
    store: AnnotationStore = Depends(get_annotation_store),
    provider: FeatureChat = Depends(get_span_chat),
    config: Config = Depends(get_config),
    current_user: User = Depends(current_active_user),
    budget: AllowanceBudget = Depends(get_allowance_budget),
):
    """
    Stream an assistant reply discussing whether the given span fits its tag.

    The request body carries the full chat history; the backend resolves
    span / document / tag context and prepends it as a system message before
    streaming the reply from the span_chat feature's model tier.
    """
    discussion = await prepare_discussion(store, current_user, body, provider,
                                          context_chars=config.SPAN_CHAT_CONTEXT_CHARS,
                                          history_limit=config.SPAN_CHAT_HISTORY_LIMIT)
    operation = provider.operation(budget)
    await operation.admit()
    return StreamingResponse(_stream(discussion, operation), media_type=_NDJSON_MEDIA_TYPE)
