"""Streamed replies of AI operations."""
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from semant_demo.adapters.llm.gateway import OperationScope


class OperationStreamingResponse(StreamingResponse):
    """A stream that enters ``operation`` (already admitted), settled however the response ends.

    Starlette neither closes a body it stopped iterating (a client disconnect) nor starts one
    whose client left before the first chunk. Closing the body here exits the operation in
    the first case; in the second, the operation is released, settled with no calls, so its
    reservation is not kept charged (#563).
    """

    def __init__(self, content: AsyncGenerator[bytes, None], operation: OperationScope, media_type: str):
        self._content = content
        self._operation = operation
        super().__init__(content, media_type=media_type)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self._content.aclose()
            finally:
                await self._operation.release()
