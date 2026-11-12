"""HTTP routes of the collection export (#656); the rules live in ``service.py``."""
import asyncio
import contextlib
import logging
from typing import AsyncIterator, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.requests import HTTPConnection
from starlette.types import Receive, Scope, Send

from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.exports import service
from semant_demo.features.exports.schemas import CollectionExportRequest, CollectionExportTicket
from semant_demo.features.exports.service import ExportRegistry, ExportSources, RunningExport
from semant_demo.routes.dependencies import get_annotation_store, get_attribute_definitions, get_resources
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User

logger = logging.getLogger(__name__)

exp_router = APIRouter()

_ZIP = "application/zip"


def get_export_registry(connection: HTTPConnection) -> ExportRegistry:
    """The application's tickets and running exports (created with the first export)."""
    state = connection.app.state
    if getattr(state, "exports", None) is None:
        state.exports = ExportRegistry()
    return state.exports


async def get_export_sources(connection: HTTPConnection) -> ExportSources:
    return ExportSources(store=await get_annotation_store(connection),
                         attributes=get_attribute_definitions(connection),
                         session_maker=get_resources(connection).session_maker)


class _ExportResponse(StreamingResponse):
    """The ZIP stream of one running export. It runs in its own task, which a newer export of
    the same user cancels (``RunningExport.cancel``); however the response ends (done, failed,
    client gone, cancelled), the stream is closed and the export released."""

    def __init__(self, stream: AsyncIterator[bytes], filename: str, run: RunningExport,
                 release: Callable[[RunningExport], None]):
        self._stream = stream
        self._run = run
        self._release = release
        super().__init__(self._logged(), media_type=_ZIP,
                         headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                  "Cache-Control": "no-store"})

    async def _logged(self) -> AsyncIterator[bytes]:
        try:
            async for data in self._stream:
                yield data
        except Exception:
            # The status line is sent already: the download ends unfinished (an invalid ZIP).
            logger.exception("Collection export failed part way")
            raise

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = asyncio.ensure_future(super().__call__(scope, receive, send))
        self._run.cancel = response.cancel
        try:
            await response
        except asyncio.CancelledError:
            if not response.cancelled() or _cancelling():
                raise
            # Ended for a newer export of the user: the unfinished download fails.
        finally:
            if not response.done():
                # The request itself was cancelled: stop the response task before closing its stream.
                response.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await response
            try:
                await self._stream.aclose()
            finally:
                self._release(self._run)


def _cancelling() -> bool:
    """Whether the request's own task is being cancelled (not only the response task)."""
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


@exp_router.post("/api/exports/collections", response_model=CollectionExportTicket)
async def request_collection_export(request: CollectionExportRequest,
                                    store: AnnotationStore = Depends(get_annotation_store),
                                    registry: ExportRegistry = Depends(get_export_registry),
                                    current_user: User = Depends(current_active_user)) -> CollectionExportTicket:
    """
    Starts an export of whole collections (#656, docs/EXPORT_FORMAT.md): checks read access to
    each (404 for a collection the user cannot read) and returns a one-time download path,
    valid for ``expires_in`` seconds. Ends the user's running export, if any (one per user).
    """
    token = await service.request_export(store, registry, current_user, request.collection_ids)
    return CollectionExportTicket(download_path=service.DOWNLOAD_PATH.format(token=token),
                                  expires_in=int(registry.ttl_seconds))


@exp_router.get("/api/exports/collections/{token}", response_class=StreamingResponse,
                responses={200: {"description": "The export as a ZIP of JSON files.", "content": {_ZIP: {}}}})
async def download_collection_export(token: str,
                                     sources: ExportSources = Depends(get_export_sources),
                                     registry: ExportRegistry = Depends(get_export_registry)) -> StreamingResponse:
    """
    Downloads the export a ticket from ``POST /api/exports/collections`` names (no sign-in
    header: the path is the credential, valid once). Access is checked again; 404 for an
    unknown, used or expired path or a collection no longer readable.
    """
    ticket, run = registry.redeem(token)
    try:
        export = await service.open_export(sources, ticket)
    except BaseException:
        registry.release(run)
        raise
    return _ExportResponse(export.stream, export.filename, run, registry.release)
