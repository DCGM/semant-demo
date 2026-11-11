"""The chunks' classification status in Weaviate (#590): ``Chunks.classification_provenance``.

One ``text`` property (``field`` tokenization, filterable, not searchable) per chunk:
``UNPROCESSED`` while the chunk awaits classification (set by ``chunk_ingest`` on every chunk
it inserts), the classifier's model/version identifier once it is classified, absent on chunks
stored before the property was declared (never selected for classification).

Never creates, drops or alters a collection; ``add_property`` only adds the property, on
explicit request (``maintenance/classification_provenance_schema.py``).
"""
from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property, Tokenization

from semant_demo.adapters.weaviate.chunk_summaries import DeclaredProperty

PROPERTY = "classification_provenance"
UNPROCESSED = "UNPROCESSED"
"""The value of a chunk that awaits classification."""
EXPECTED = DeclaredProperty("text", "field", True)
"""The declaration ``add_property`` makes."""


def status(declared: dict[str, DeclaredProperty]) -> str:
    """``present``, ``missing`` or ``different`` (declared otherwise than ``EXPECTED``)."""
    found = declared.get(PROPERTY)
    return "missing" if found is None else "present" if found == EXPECTED else "different"


async def add_property(client: WeaviateAsyncClient, collection: str) -> None:
    """Declare the property on ``collection`` (a real collection name, not an alias: Weaviate
    adds properties only by the collection's name). Existing chunks have no value."""
    await client.collections.get(collection).config.add_property(Property(
        name=PROPERTY, data_type=DataType.TEXT, tokenization=Tokenization.FIELD,
        index_filterable=True, index_searchable=False))
