"""The ``Chunks.layoutStart`` property: its declaration on existing stores (#541).

``layoutStart`` is one optional object property ``{pageId, lineId, offset, match}``
(``features/documents/schemas.LayoutStart``), written and cleared as a whole by the corpus
import (#542). Nothing filters on its parts, so none of them is indexed. Stores without it
work unchanged: chunk reads then simply have no anchor. Like the chunk positions (#463), the
property is declared additively by the writing maintenance command, on explicit request;
nothing here creates, drops or alters a collection otherwise. Collection names are resolved
through aliases by the caller.
"""
from typing import Literal

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property

from semant_demo.adapters.weaviate.documents import LAYOUT_START

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
