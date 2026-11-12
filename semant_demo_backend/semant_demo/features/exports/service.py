"""Collection export (#656): every annotation of the chosen collections with the source text it
refers to, streamed as one ZIP of JSON files (format: ``docs/EXPORT_FORMAT.md``).

The browser cannot attach the sign-in token to a download it hands to its download manager,
so an export is requested in two steps: ``request_export`` checks read access to every
collection and issues a one-time ticket (a random token, valid for ``TICKET_SECONDS``);
``open_export`` redeems it, checks access again and returns the stream. Tickets and running
exports live in this process (``ExportRegistry``; the backend runs as one process). A user has
at most one running export; requesting a new ticket replaces the user's unused one.

Memory stays flat whatever the size: annotations are read through the tenant's cursor and
chunks per document, both written to the ZIP in batches. The export is not a snapshot:
annotations changed while it runs may appear in either state. ``manifest.json`` is written last,
so an interrupted download is an invalid ZIP rather than a plausible partial dataset.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import AsyncIterator, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from semant_demo.adapters.sql.attributes import AttributeRepository
from semant_demo.adapters.sql.users import UserLookup
from semant_demo.core.errors import BusyError, NotFoundError
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.documents.positions import text_length
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.user_collections.schemas import Collection

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
TICKET_SECONDS = 60
DOWNLOAD_PATH = "/api/exports/collections/{token}"
_BATCH = 500
"""Annotations or chunks written to the ZIP at a time."""
_LOOKAHEAD = 8
"""Following chunk orders read at once when an annotation continues past the collection's chunks."""
NOTES = ("Not a snapshot: annotations changed while the export ran may appear in either state; "
         "exported_at is when it started. Offsets are UTF-16 code units from the start of the "
         "annotation's chunk; an annotation may continue into the following chunks of its document "
         "(by order), which are included with in_collection false. See docs/EXPORT_FORMAT.md.")


##################################
# Tickets and one export per user #
##################################

@dataclass(frozen=True)
class ExportTicket:
    user_id: UUID
    collection_ids: tuple[UUID, ...]
    expires_at: float


class ExportRegistry:
    """One-time download tickets and the users whose export is running (this process only)."""

    def __init__(self, ttl_seconds: float = TICKET_SECONDS, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._tickets: dict[str, ExportTicket] = {}
        self._running: set[UUID] = set()

    def _purge(self) -> None:
        now = self.clock()
        for token in [t for t, ticket in self._tickets.items() if ticket.expires_at <= now]:
            del self._tickets[token]

    def _refuse_if_running(self, user_id: UUID) -> None:
        if user_id in self._running:
            raise BusyError("An export of yours is still running. Wait until its download finishes.")

    def issue(self, user_id: UUID, collection_ids: list[UUID]) -> str:
        """A new ticket; replaces the user's unused one. ``BusyError`` while an export runs."""
        self._refuse_if_running(user_id)
        self._purge()
        for token in [t for t, ticket in self._tickets.items() if ticket.user_id == user_id]:
            del self._tickets[token]
        token = secrets.token_urlsafe(32)
        self._tickets[token] = ExportTicket(user_id, tuple(collection_ids), self.clock() + self.ttl_seconds)
        return token

    def redeem(self, token: str) -> ExportTicket:
        """Use the ticket up and mark its user's export running (``release`` ends it)."""
        self._purge()
        ticket = self._tickets.pop(token, None)
        if ticket is None:
            raise NotFoundError("This export link is unknown, used or expired. Start the export again.")
        self._refuse_if_running(ticket.user_id)
        self._running.add(ticket.user_id)
        return ticket

    def release(self, user_id: UUID) -> None:
        self._running.discard(user_id)

    def running(self, user_id: UUID) -> bool:
        return user_id in self._running


async def request_export(store: AnnotationStore, registry: ExportRegistry, user: Principal | None,
                         collection_ids: list[UUID]) -> str:
    """Check read access to every collection (401 / 404 like other collection reads) and issue a
    ticket for them."""
    for collection_id in collection_ids:
        await access.require_collection_read(store.collections, user, collection_id)
    return registry.issue(user.id, collection_ids)


##########
# Export #
##########

@dataclass
class ExportSources:
    store: AnnotationStore
    attributes: AttributeRepository
    session_maker: async_sessionmaker
    """For user names; the stream outlives the request's own database session."""


@dataclass
class _Summary:
    collection: Collection
    file: str
    annotations: int = 0
    chunks: int = 0
    missing_chunks: int = 0
    """Chunks annotations refer to that no longer exist (their annotations cannot be cut)."""
    people: set[UUID] = field(default_factory=set)


@dataclass
class CollectionExport:
    filename: str
    stream: AsyncIterator[bytes]


async def open_export(sources: ExportSources, ticket: ExportTicket) -> CollectionExport:
    """Check access again for the ticket's user and prepare the stream of the ZIP."""
    user = SimpleNamespace(id=ticket.user_id)
    collections: list[Collection] = []
    for collection_id in ticket.collection_ids:
        grant = await access.require_collection_read(sources.store.collections, user, collection_id)
        collection = await sources.store.collections.read(grant.collection_id)
        if collection is None:
            raise NotFoundError("Collection not found")
        collections.append(collection)
    started = datetime.now(timezone.utc)
    return CollectionExport(filename=f"semant-export-{started:%Y-%m-%d}.zip",
                            stream=_zip(sources, ticket.user_id, collections, started))


class _Sink:
    """The non-seekable file ``zipfile`` writes to; ``take`` hands over what was written."""

    def __init__(self):
        self._parts: list[bytes] = []

    def write(self, data) -> int:
        self._parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def take(self) -> bytes:
        data = b"".join(self._parts)
        self._parts.clear()
        return data


def _slug(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40].strip("-") or "collection"


def _file_names(collections: list[Collection]) -> list[str]:
    names = [f"{_slug(c.name)}-{str(c.id)[:8]}.json" for c in collections]
    if len(set(names)) < len(names):
        names = [f"{_slug(c.name)}-{c.id}.json" for c in collections]
    return names


def _json_default(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Not exportable: {type(value).__name__}")


def _json(value, **kwargs) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default, **({"separators": (",", ":")} | kwargs))


async def _zip(sources: ExportSources, user_id: UUID, collections: list[Collection],
               started: datetime) -> AsyncIterator[bytes]:
    sink = _Sink()
    archive = zipfile.ZipFile(sink, "w", compression=zipfile.ZIP_DEFLATED)
    summaries: list[_Summary] = []
    for collection, name in zip(collections, _file_names(collections)):
        summary = _Summary(collection, name)
        summaries.append(summary)
        with archive.open(name, "w", force_zip64=True) as entry:
            async for fragment in _collection_json(sources, summary):
                await asyncio.to_thread(entry.write, fragment.encode("utf-8"))
                if data := sink.take():
                    yield data
        if data := sink.take():
            yield data
    archive.writestr("manifest.json", _json(await _manifest(sources, user_id, summaries, started), indent=2))
    archive.close()
    yield sink.take()


async def _manifest(sources: ExportSources, user_id: UUID, summaries: list[_Summary], started: datetime) -> dict:
    async with sources.session_maker() as session:
        user = await UserLookup(session).get_user(user_id)
    return {
        "format_version": FORMAT_VERSION,
        "exported_at": started,
        "exported_by": {"id": user_id, "name": user.name if user else None,
                        "username": user.username if user else None},
        "collections": [{"id": s.collection.id, "name": s.collection.name, "file": s.file,
                         "annotations": s.annotations, "chunks": s.chunks,
                         "missing_chunks": s.missing_chunks} for s in summaries],
        "notes": NOTES,
    }


def _annotation(stored: dict) -> dict:
    return {
        "id": stored["id"],
        "chunk_id": stored.get("chunkId"),
        "tag_id": stored.get("tagId"),
        "start": stored.get("start"),
        "end": stored.get("end"),
        "type": stored.get("type"),
        "origin": stored.get("origin") or "unknown",
        "created_by": stored.get("createdBy"),
        "created_at": stored.get("createdAt"),
        "reviewed_by": stored.get("reviewedBy"),
        "reviewed_at": stored.get("reviewedAt"),
        "last_edited_by": stored.get("lastEditedBy"),
        "last_edited_at": stored.get("lastEditedAt"),
        "ai_run_id": stored.get("aiRunId"),
        "reason": stored.get("reason"),
        "confidence": stored.get("confidence"),
        "edit_version": stored.get("editVersion") or 0,
        "revision": stored.get("revision"),
        "attributes": {str(a): [str(v) for v in values]
                       for a, values in codec.group(stored.get("attributeValues")).items()},
    }


def _uuid(value) -> UUID | None:
    return UUID(str(value)) if value is not None else None


async def _collection_json(sources: ExportSources, summary: _Summary) -> AsyncIterator[str]:
    """The collection's JSON object in fragments: small parts first, then the annotations and
    chunks in batches, then the people named in it."""
    store, collection_id = sources.store, summary.collection.id
    metadata = summary.collection.model_dump(
        mode="json", include={"id", "name", "description", "owner", "created_at", "updated_at", "color"})
    yield '{"metadata":' + _json(metadata)
    tags = await store.tags.read_by_collection(collection_id)
    yield ',"tags":' + _json([t.model_dump(mode="json") for t in tags])
    attributes = await sources.attributes.read_all(collection_id)
    yield ',"attributes":' + _json([a.model_dump(mode="json") for a in attributes])

    # chunk id -> (document id, the furthest end of an annotation anchored on it)
    anchors: dict[UUID, tuple[UUID | None, int]] = {}
    yield ',"annotations":['
    batch: list[str] = []
    async with store.activity.in_use(collection_id):
        async for stored in store.spans.iterate_stored(collection_id):
            record = _annotation(stored)
            summary.people.update(_uuid(record[k]) for k in ("created_by", "reviewed_by", "last_edited_by")
                                  if record[k] is not None)
            chunk_id = _uuid(record["chunk_id"])
            if chunk_id is not None:
                document_id, end = anchors.get(chunk_id, (_uuid(stored.get("documentId")), 0))
                anchors[chunk_id] = (document_id, max(end, record["end"] or 0))
            batch.append(_json(record))
            if len(batch) >= _BATCH:
                yield ("," if summary.annotations else "") + ",".join(batch)
                summary.annotations += len(batch)
                batch = []
    if batch:
        yield ("," if summary.annotations else "") + ",".join(batch)
        summary.annotations += len(batch)

    yield '],"chunks":['
    async for chunks in _chunks(sources, collection_id, anchors, summary):
        for start in range(0, len(chunks), _BATCH):
            part = chunks[start:start + _BATCH]
            yield ("," if summary.chunks else "") + ",".join(_json(c) for c in part)
            summary.chunks += len(part)

    yield '],"people":' + _json(await _people(sources, collection_id, summary.people)) + "}"


@dataclass(frozen=True)
class _Chunk:
    id: UUID
    order: int
    text: str


async def _chunks(sources: ExportSources, collection_id: UUID, anchors: dict[UUID, tuple[UUID | None, int]],
                  summary: _Summary) -> AsyncIterator[list[dict]]:
    """Per document (in a list, in order): the collection's chunks, then the anchor chunks of
    annotations that are not in the collection and the following chunks annotations continue
    into, ``in_collection`` false."""
    store = sources.store
    by_document: dict[UUID, dict[UUID, int]] = {}
    for chunk_id, (document_id, end) in anchors.items():
        if document_id is None:  # stored before spans named their document
            chunk = await store.documents.read_chunk_text(chunk_id)
            if chunk is None or chunk.document_id is None:
                summary.missing_chunks += 1
                continue
            document_id = chunk.document_id
        by_document.setdefault(document_id, {})[chunk_id] = end

    documents = [d.id for d in await store.collections.read_all_documents(collection_id)]
    linked = set(documents)
    for document_id in documents + [d for d in by_document if d not in linked]:
        in_collection = (await store.collections.read_all_chunks_by_document(document_id, collection_id)
                         if document_id in linked else [])
        out: dict[UUID, tuple[_Chunk, bool]] = {c.id: (_Chunk(c.id, c.order, c.text), True) for c in in_collection}
        by_order = {chunk.order: chunk for chunk, _ in out.values()}

        async def at_order(order: int) -> _Chunk | None:
            if order not in by_order:
                for c in await store.documents.read_chunk_texts_in_range(document_id, order, order + _LOOKAHEAD):
                    by_order.setdefault(c.order, _Chunk(c.id, c.order, c.text))
            return by_order.get(order)

        for chunk_id, end in by_document.get(document_id, {}).items():
            if chunk_id in out:
                anchor = out[chunk_id][0]
            else:
                read = await store.documents.read_chunk_text(chunk_id)
                if read is None:
                    summary.missing_chunks += 1
                    continue
                anchor = _Chunk(read.id, read.order, read.text)
                out[anchor.id] = (anchor, False)
                by_order.setdefault(anchor.order, anchor)
            covered, order = text_length(anchor.text), anchor.order
            while covered < end:
                order += 1
                following = await at_order(order)
                if following is None:
                    break
                out.setdefault(following.id, (following, False))
                covered += text_length(following.text)

        yield [{"id": chunk.id, "document_id": document_id, "order": chunk.order, "text": chunk.text,
                "in_collection": member}
               for chunk, member in sorted(out.values(), key=lambda item: item[0].order)]


async def _people(sources: ExportSources, collection_id: UUID, named: set[UUID]) -> list[dict]:
    """The owner and members, then everyone else named in the annotations (former members),
    with their names; ids of deleted accounts are listed without names."""
    record = await sources.store.collections.read_access_record(collection_id)
    owner, members = record if record is not None else (None, set())
    ids = ([owner] if owner is not None else []) + sorted(members - {owner}, key=str)
    ids += sorted(named - set(ids), key=str)
    async with sources.session_maker() as session:
        users = {u.id: u for u in await UserLookup(session).get_users(ids)}

    def role(user_id: UUID) -> str:
        return "owner" if user_id == owner else "member" if user_id in members else "former"
    return [{"id": i, "name": users[i].name if i in users else None,
             "username": users[i].username if i in users else None, "role": role(i)} for i in ids]
