"""HTTP routes of the collection export (#656); the rules live in ``service.py``."""
import logging
from typing import AsyncIterator, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.requests import HTTPConnection
from starlette.types import Receive, Scope, Send

from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.exports import service
from semant_demo.features.exports.schemas import CollectionExportRequest, CollectionExportTicket
from semant_demo.features.exports.service import ExportRegistry, ExportSources
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
    """The ZIP stream; however the response ends (done, failed, client gone), the stream is
    closed and the user's export no longer counts as running."""

    def __init__(self, stream: AsyncIterator[bytes], filename: str, release: Callable[[], None]):
        self._stream = stream
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
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self._stream.aclose()
            finally:
                self._release()


@exp_router.post("/api/exports/collections", response_model=CollectionExportTicket)
async def request_collection_export(request: CollectionExportRequest,
                                    store: AnnotationStore = Depends(get_annotation_store),
                                    registry: ExportRegistry = Depends(get_export_registry),
                                    current_user: User = Depends(current_active_user)) -> CollectionExportTicket:
    """
    Starts an export of whole collections (#656, docs/EXPORT_FORMAT.md): checks read access to
    each (404 for a collection the user cannot read) and returns a one-time download path,
    valid for ``expires_in`` seconds. 409 while another export of the user is running.
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
    unknown, used or expired path or a collection no longer readable, 409 while another export
    of the user is running.
    """
    ticket = registry.redeem(token)
    try:
        export = await service.open_export(sources, ticket)
    except BaseException:
        registry.release(ticket.user_id)
        raise
    return _ExportResponse(export.stream, export.filename, lambda: registry.release(ticket.user_id))
