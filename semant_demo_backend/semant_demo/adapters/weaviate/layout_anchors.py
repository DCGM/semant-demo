"""The ``Chunks.layoutStart`` property: its declaration on existing stores (#541).

``layoutStart`` is one optional object property ``{pageId, lineId, offset, match}``
(``features/documents/schemas.LayoutStart``), written and cleared as a whole by the corpus
import (#542). Nothing filters on its parts, so none of them is indexed. Stores without it
work unchanged: chunk reads then simply have no anchor. Like the chunk positions (#463), the
property is declared additively by the writing maintenance command, on explicit request;
nothing here creates, drops or alters a collection otherwise. Collection names are resolved
through aliases by the caller.

The reads for the import return ids, order, text, the page fields and the anchor, never
vectors; a write is a merge of ``layoutStart`` alone (text, other properties, references and
vectors are kept), and null clears it.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate.documents import LAYOUT_START
from semant_demo.adapters.weaviate.paging import fetch_all

NESTED_TYPES = {"pageId": DataType.TEXT, "lineId": DataType.TEXT, "offset": DataType.INT, "match": DataType.TEXT}
"""The declared type of each field of ``layoutStart``."""


def layout_start_property() -> Property:
    """The declaration of ``Chunks.layoutStart``."""
    return Property(
        name=LAYOUT_START, data_type=DataType.OBJECT, index_filterable=False, index_searchable=False,
        nested_properties=[Property(name=name, data_type=data_type, index_filterable=False,
                                    index_searchable=False if data_type == DataType.TEXT else None)
                           for name, data_type in NESTED_TYPES.items()])


async def layout_start_state(client: WeaviateAsyncClient, collection: str) -> Literal["missing", "declared", "conflict"]:
    """Whether the chunk collection declares ``layoutStart`` as expected (``declared``), not at
    all (``missing``) or differently (``conflict``, which needs a separate, reviewed migration)."""
    config = await client.collections.get(collection).config.get()
    declared = next((p for p in config.properties if p.name == LAYOUT_START), None)
    if declared is None:
        return "missing"
    if declared.data_type != DataType.OBJECT:
        return "conflict"
    nested = {p.name: p.data_type for p in declared.nested_properties or []}
    return "declared" if nested == NESTED_TYPES else "conflict"


async def declare_layout_start(client: WeaviateAsyncClient, collection: str) -> None:
    """Add ``layoutStart`` to the chunk collection when it is missing (existing chunks have no
    value). Raises ``ValueError`` when it is declared differently."""
    state = await layout_start_state(client, collection)
    if state == "conflict":
        raise ValueError(f"{collection}.{LAYOUT_START} is declared differently; it needs a reviewed migration")
    if state == "missing":
        await client.collections.get(collection).config.add_property(layout_start_property())


@dataclass(frozen=True)
class AnchoredChunk:
    """A stored chunk as the import sees it; ``layout_start`` is the stored value as is."""
    id: UUID
    order: int | None
    text: str
    from_page: int | None
    to_page: int | None
    start_page_id: str | None
    layout_start: dict[str, Any] | None


CHUNK_PROPERTIES = ["order", "text", "from_page", "to_page", "start_page_id"]


def _chunk(obj) -> AnchoredChunk:
    props = obj.properties
    return AnchoredChunk(id=obj.uuid, order=props.get("order"), text=props.get("text") or "",
                         from_page=props.get("from_page"), to_page=props.get("to_page"),
                         start_page_id=props.get("start_page_id"), layout_start=props.get(LAYOUT_START))


async def read_document_chunks(client: WeaviateAsyncClient, collection: str, document_id: UUID,
                               with_anchor: bool) -> list[AnchoredChunk]:
    """Every chunk of the document (any order). ``with_anchor``: the collection declares
    ``layoutStart`` (an undeclared property cannot be read)."""
    objects = await fetch_all(client.collections.get(collection),
                              filters=Filter.by_ref("document").by_id().equal(document_id),
                              return_properties=CHUNK_PROPERTIES + ([LAYOUT_START] if with_anchor else []))
    return [_chunk(o) for o in objects]


async def read_layout_starts(client: WeaviateAsyncClient, collection: str,
                             ids: Sequence[UUID]) -> dict[UUID, dict[str, Any] | None]:
    """The stored ``layoutStart`` of each existing chunk of ``ids`` (at most 100 at a time)."""
    found: dict[UUID, dict[str, Any] | None] = {}
    for start in range(0, len(ids), 100):
        batch = list(ids[start:start + 100])
        response = await client.collections.get(collection).query.fetch_objects(
            filters=Filter.by_id().contains_any(batch), limit=len(batch), return_properties=[LAYOUT_START])
        found.update({o.uuid: o.properties.get(LAYOUT_START) for o in response.objects})
    return found


async def write_layout_start(client: WeaviateAsyncClient, collection: str, chunk_id: UUID,
                             value: dict[str, Any] | None) -> None:
    """Store (or, with None, clear) the chunk's ``layoutStart``; everything else is kept."""
    await client.collections.get(collection).data.update(uuid=chunk_id, properties={LAYOUT_START: value})
