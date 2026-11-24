"""Read-only access to the semANT store the corpus is sampled from (#726).

``SourceReader`` is what sampling needs; ``WeaviateSource`` implements it over the application's
``Chunks`` and ``Documents`` collections with reads only (a scan of ids and languages, fetches by
id and one aggregate), so a production store can be sampled without being changed. Properties a
store lacks (an older schema) are simply not read.

**Visibility** (#883 review). By default only chunks of public documents are read: a chunk is used
only when its ``documentPublic`` (#793, the application's eligibility index of a document's
visibility) is ``true``; false or missing withholds it (fail closed), and a store that does not
declare ``documentPublic`` is refused. The scan reads the flag with the language and drops other
chunks before any text is read; ``read`` and ``neighbours`` filter on it in Weaviate, so imported
and neighbouring chunks follow the same rule. ``include_restricted=True`` (an explicit opt-in of
the config) reads every chunk.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import Metrics
from weaviate.classes.query import Filter, QueryReference

from semant_demo.adapters.weaviate.names import CollectionNames

MIXED, UNKNOWN = "(mixed)", "(unknown)"
READ_BATCH = 100
VISIBILITY = "documentPublic"
"""The chunk's copy of its document's visibility (``semant_demo.adapters.weaviate.chunk_visibility``)."""


class SourceError(Exception):
    """The source store cannot be sampled under the configured visibility policy."""


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

    def scan(self, page: int) -> AsyncIterator[tuple[UUID, str]]:
        """Every chunk's id and language key, in id order (a stable order for a given store),
        read ``page`` at a time; nothing else is read."""
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

    def __init__(self, client: WeaviateAsyncClient, names: CollectionNames, description: dict[str, Any],
                 include_restricted: bool = False):
        self.client, self.names, self.description = client, names, description
        self.include_restricted = include_restricted
        self.chunks = client.collections.get(names.chunks_collection_name)
        self._properties: tuple[list[str], list[str]] | None = None
        self.withheld: Counter[str] = Counter()
        """Chunks the scan skipped by visibility: ``restricted`` (false) and ``unknown`` (no value)."""

    async def _declared(self) -> tuple[list[str], list[str]]:
        if self._properties is None:
            chunk = await self.chunks.config.get()
            document = await self.client.collections.get(self.names.document_collection_name).config.get()
            have_chunk = {p.name for p in chunk.properties}
            have_document = {p.name for p in document.properties}
            if not self.include_restricted and VISIBILITY not in have_chunk:
                raise SourceError(f"the source's {self.names.chunks_collection_name} does not declare {VISIBILITY} "
                                  "(#793), so public documents cannot be told apart; sample it only with "
                                  "source.include_restricted_documents: true")
            self._properties = ([p for p in self.CHUNK_PROPERTIES if p in have_chunk],
                                [p for p in self.DOCUMENT_PROPERTIES if p in have_document])
        return self._properties

    def _visible(self, filters: Any) -> Any:
        """``filters`` narrowed to chunks of public documents, unless restricted ones are included."""
        return filters if self.include_restricted else filters & Filter.by_property(VISIBILITY).equal(True)

    async def _fetch(self, **query: Any) -> list[SourceChunk]:
        chunk_properties, document_properties = await self._declared()
        query["filters"] = self._visible(query["filters"])
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

    async def scan(self, page: int) -> AsyncIterator[tuple[UUID, str]]:
        # The cursor iterator walks the whole collection by id; a filter could not (Weaviate
        # refuses a cursor with a filter, and filtered reads stop at QUERY_MAXIMUM_RESULTS).
        # The visibility flag is read with the language, and other chunks are dropped here, before
        # any of their text is read.
        await self._declared()
        properties = ["language"] if self.include_restricted else ["language", VISIBILITY]
        async for obj in self.chunks.iterator(return_properties=properties, cache_size=page):
            if not self.include_restricted:
                public = obj.properties.get(VISIBILITY)
                if public is not True:
                    self.withheld["restricted" if public is False else "unknown"] += 1
                    continue
            yield obj.uuid, language_key(obj.properties.get("language"))

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
                "documents_collection": self.names.document_collection_name,
                "documents": "all, including restricted" if self.include_restricted else "public only",
                **({} if self.include_restricted else {"withheld_by_visibility": dict(sorted(self.withheld.items()))})}
