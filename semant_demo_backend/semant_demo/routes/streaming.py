"""Streamed replies of AI operations."""
from collections.abc import AsyncGenerator
from typing import Protocol

import anyio
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class Releasable(Protocol):
    async def release(self) -> None:
        """Settle what was admitted before the stream if the stream never used it."""


class OperationStreamingResponse(StreamingResponse):
    """A stream of AI work admitted before the response (an ``OperationScope`` or a
    ``SuggestionRun``), settled however the response ends.

    Starlette neither closes a body it stopped iterating (a client disconnect) nor starts one
    whose client left before the first chunk. The body is closed here in the task that
    iterated it, so the operation it entered is left in the context it was entered in
    (Starlette streams in a task of its own before ASGI spec 2.4); in the second case
    ``work`` is released, settled with no calls, so its reservation is not kept (#563).
    """

    def __init__(self, content: AsyncGenerator[bytes, None], work: Releasable, media_type: str):
        self._content = content
        self._work = work
        super().__init__(content, media_type=media_type)

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            # Shielded: after a disconnect this task is cancelled, but closing settles.
            with anyio.CancelScope(shield=True):
                await self._content.aclose()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._work.release()
