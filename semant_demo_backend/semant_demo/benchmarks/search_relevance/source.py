"""Read-only access to the semANT store the corpus is sampled from (#726).

``SourceReader`` is what sampling needs; ``WeaviateSource`` implements it over the application's
``Chunks`` and ``Documents`` collections with reads only (fetches and one aggregate), so a
production store can be sampled without being changed. Properties a store lacks (an older
schema) are simply not read.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import Metrics
from weaviate.classes.query import Filter, QueryReference

from semant_demo.adapters.weaviate.names import CollectionNames

MIXED, UNKNOWN = "(mixed)", "(unknown)"
MAX_WINDOW = 10_000
"""Weaviate's default QUERY_MAXIMUM_RESULTS: a filtered read reaches no further."""
READ_BATCH = 100


@dataclass(frozen=True)
class SourceChunk:
    id: UUID
    document_id: UUID | None
    order: int
    language: str
    """The stored language as one key: the code, ``(mixed)`` or ``(unknown)``."""
    text: str
    title: str | None = None
    document_title: str | None = None
    year: int | None = None
    document_type: str | None = None


class SourceReader(Protocol):
    async def languages(self) -> dict[str, int]:
        """Chunk count by stored language value."""
        ...

    async def after(self, cursor: UUID | None, limit: int) -> list[SourceChunk]:
        """Up to ``limit`` chunks with ids after ``cursor`` (from the first when None), in id order."""
        ...

    async def window(self, language: str, offset: int, limit: int) -> list[SourceChunk]:
        """Chunks of a stored language value, ``offset`` into the filtered list."""
        ...

    async def neighbours(self, document_id: UUID, orders: Sequence[int]) -> list[SourceChunk]:
        """The chunks of a document at the given orders."""
        ...

    async def read(self, ids: Sequence[UUID]) -> list[SourceChunk]:
        """The chunks of ``ids`` that exist."""
        ...

    def describe(self) -> dict[str, Any]:
        """Where the corpus comes from (never a credential)."""
        ...


def language_key(value: Any) -> str:
    items = [value] if isinstance(value, str) else value if isinstance(value, (list, tuple)) else []
    values = sorted({item.strip() for item in items if isinstance(item, str) and item.strip()})
    return values[0] if len(values) == 1 else MIXED if values else UNKNOWN


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class WeaviateSource:
    """``SourceReader`` over a semANT Weaviate; never writes."""

    CHUNK_PROPERTIES = ("text", "title", "language", "order", "yearIssued")
    DOCUMENT_PROPERTIES = ("title", "yearIssued", "documentType")

    def __init__(self, client: WeaviateAsyncClient, names: CollectionNames, description: dict[str, Any]):
        self.client, self.names, self.description = client, names, description
        self.chunks = client.collections.get(names.chunks_collection_name)
        self._properties: tuple[list[str], list[str]] | None = None

    async def _declared(self) -> tuple[list[str], list[str]]:
        if self._properties is None:
            chunk = await self.chunks.config.get()
            document = await self.client.collections.get(self.names.document_collection_name).config.get()
            have_chunk = {p.name for p in chunk.properties}
            have_document = {p.name for p in document.properties}
            self._properties = ([p for p in self.CHUNK_PROPERTIES if p in have_chunk],
                                [p for p in self.DOCUMENT_PROPERTIES if p in have_document])
        return self._properties

    async def _fetch(self, **query: Any) -> list[SourceChunk]:
        chunk_properties, document_properties = await self._declared()
        result = await self.chunks.query.fetch_objects(
            return_properties=chunk_properties,
            return_references=[QueryReference(link_on="document", return_properties=document_properties)], **query)
        return [self._chunk(obj) for obj in result.objects]

    @staticmethod
    def _chunk(obj: Any) -> SourceChunk:
        props = obj.properties
        refs = (obj.references or {}).get("document")
        document = refs.objects[0] if refs and refs.objects else None
        doc_props = document.properties if document else {}
        return SourceChunk(id=obj.uuid, document_id=document.uuid if document else None,
                           order=_int(props.get("order")) or 0, language=language_key(props.get("language")),
                           text=_text(props.get("text")) or "", title=_text(props.get("title")),
                           document_title=_text(doc_props.get("title")),
                           year=_int(props.get("yearIssued")) or _int(doc_props.get("yearIssued")),
                           document_type=_text(doc_props.get("documentType")))

    async def languages(self) -> dict[str, int]:
        result = await self.chunks.aggregate.over_all(return_metrics=[
            Metrics("language").text(top_occurrences_count=True, top_occurrences_value=True, limit=1000)])
        metric = result.properties.get("language")
        occurrences = metric.top_occurrences if metric is not None and metric.top_occurrences else []
        total = result.total_count or 0
        found = {o.value: o.count for o in occurrences if o.value}
        if total > sum(found.values()):
            # Chunks without a language (or language arrays, counted per value) are not in the
            # top occurrences; what remains is reported as unknown.
            found[UNKNOWN] = total - sum(found.values())
        return found

    async def after(self, cursor: UUID | None, limit: int) -> list[SourceChunk]:
        return await self._fetch(limit=limit, after=cursor) if cursor else await self._fetch(limit=limit)

    async def window(self, language: str, offset: int, limit: int) -> list[SourceChunk]:
        return await self._fetch(filters=Filter.by_property("language").equal(language), offset=offset, limit=limit)

    async def neighbours(self, document_id: UUID, orders: Sequence[int]) -> list[SourceChunk]:
        if not orders:
            return []
        filters = (Filter.by_ref("document").by_id().equal(document_id)
                   & Filter.by_property("order").contains_any(list(orders)))
        return await self._fetch(filters=filters, limit=len(orders) * 4)

    async def read(self, ids: Sequence[UUID]) -> list[SourceChunk]:
        found = []
        for start in range(0, len(ids), READ_BATCH):
            batch = list(ids[start:start + READ_BATCH])
            found += await self._fetch(filters=Filter.by_id().contains_any(batch), limit=len(batch))
        return found

    def describe(self) -> dict[str, Any]:
        return {**self.description, "chunks_collection": self.names.chunks_collection_name,
                "documents_collection": self.names.document_collection_name}
