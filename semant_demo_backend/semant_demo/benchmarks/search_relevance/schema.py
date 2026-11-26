"""The collections of the benchmark store (#726, #727) and their description for the manifests.

The application's collections as the passage search reads them (``features/search/service``,
``adapters/weaviate/search``), in the shape of the automated-test schema (production's exact
schema is #128): ``Chunks`` with the properties the search returns and filters on and a
reference to its ``Documents``, ``Documents`` with the bibliographic properties of a hit, and
``UserCollection`` (the target of the chunks' collection reference; never written). Tags, spans
and annotations are not needed by an anonymous passage search and are left out.

BM25 searches every text property of ``Chunks`` unless a configuration names its properties, so
these properties and their tokenization are part of what a run measures; ``describe`` reports
them. Chunk vectors are named vectors added per model by ``store.ensure_vector``; ``default`` is
declared but never filled (Weaviate 1.40 gives a collection without vectors one anyway).

Plus the benchmark's own ``MARKER`` collection: the ownership marker and the store's records
(the loaded dataset, the vectors), never read by the application.
"""
from __future__ import annotations

from typing import Any

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty, Tokenization

from semant_demo.adapters.weaviate.chunk_visibility import PROPERTY as DOCUMENT_PUBLIC_FLAG
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.features.search.filters import TASK_CLASSES

SCHEMA_VERSION = "search-benchmark-store/2"
"""2: ``start_page_id`` searchable, ``documentPublic`` (#793)."""
"""Changes when the collections below change; recorded in ``describe``."""
MARKER = "SemantSearchBenchmarkStore"
"""The benchmark's ownership marker and records (not the tests' ``SemantTestStoreMarker``)."""


def app_collections(names: CollectionNames) -> list[str]:
    """The application collections the store creates, referenced ones first."""
    return [names.user_collection_name, names.document_collection_name, names.chunks_collection_name]


async def create_marker(client: WeaviateAsyncClient) -> None:
    text = DataType.TEXT
    await client.collections.create(
        MARKER,
        vector_config=Configure.Vectors.self_provided(),
        properties=[
            Property(name="kind", data_type=text, tokenization=Tokenization.FIELD),
            Property(name="name", data_type=text, tokenization=Tokenization.FIELD),
            Property(name="purpose", data_type=text, tokenization=Tokenization.FIELD),
            Property(name="token_sha256", data_type=text, tokenization=Tokenization.FIELD),
            Property(name="state", data_type=text, tokenization=Tokenization.FIELD),
            Property(name="info", data_type=text, index_searchable=False, index_filterable=False),
            Property(name="updated", data_type=DataType.DATE),
        ],
    )


async def create_app_collections(client: WeaviateAsyncClient, names: CollectionNames) -> list[str]:
    """Create the application collections that are missing; the names created."""
    existing = set((await client.collections.list_all(simple=True)).keys())
    creators = {
        names.user_collection_name: _user_collections,
        names.document_collection_name: _documents,
        names.chunks_collection_name: _chunks,
    }
    created = []
    for name in app_collections(names):
        if name not in existing:
            await creators[name](client, names)
            created.append(name)
    return created


async def _user_collections(client: WeaviateAsyncClient, names: CollectionNames) -> None:
    text = DataType.TEXT
    await client.collections.create(
        names.user_collection_name,
        vector_config=Configure.Vectors.self_provided(),
        properties=[
            Property(name="name", data_type=text),
            Property(name="user_id", data_type=text),
            Property(name="description", data_type=text),
            Property(name="color", data_type=text),
            Property(name="created_at", data_type=DataType.DATE),
            Property(name="updated_at", data_type=DataType.DATE),
            Property(name="owner", data_type=text),
            Property(name="shared_with", data_type=DataType.UUID_ARRAY),
        ],
    )


async def _documents(client: WeaviateAsyncClient, names: CollectionNames) -> None:
    text, text_array = DataType.TEXT, DataType.TEXT_ARRAY
    await client.collections.create(
        names.document_collection_name,
        vector_config=Configure.Vectors.self_provided(),
        properties=[
            Property(name="title", data_type=text, tokenization=Tokenization.WORD),
            Property(name="subtitle", data_type=text),
            Property(name="public", data_type=DataType.BOOL),
            Property(name="library", data_type=text, tokenization=Tokenization.FIELD),
            Property(name="documentType", data_type=text),
            Property(name="partNumber", data_type=text),
            Property(name="partName", data_type=text),
            Property(name="dateIssued", data_type=DataType.DATE),
            Property(name="yearIssued", data_type=DataType.INT, index_range_filters=True),
            Property(name="language", data_type=text, tokenization=Tokenization.WORD),
            Property(name="publisher", data_type=text),
            Property(name="placeOfPublication", data_type=text),
            Property(name="author", data_type=text_array),
        ],
        references=[ReferenceProperty(name="collection", target_collection=names.user_collection_name)],
    )


async def _chunks(client: WeaviateAsyncClient, names: CollectionNames) -> None:
    text, integer = DataType.TEXT, DataType.INT
    await client.collections.create(
        names.chunks_collection_name,
        vector_config=[Configure.Vectors.self_provided(name="default")],
        properties=[
            Property(name="text", data_type=text),
            Property(name="title", data_type=text),
            Property(name="order", data_type=integer),
            Property(name="language", data_type=text),
            # A page id the dataset does not have (``store.PAGE``, a UUID like the real ones);
            # searchable as in the application's schema, so BM25 searches the same properties.
            Property(name="start_page_id", data_type=text),
            Property(name="from_page", data_type=integer),
            Property(name="to_page", data_type=integer),
            Property(name="end_paragraph", data_type=DataType.BOOL),
            # Anonymous search selects documentPublic == true (#793); declared as the application's.
            Property(name=DOCUMENT_PUBLIC_FLAG, data_type=DataType.BOOL, index_filterable=True),
            # The document's year, as the application's year filters read it (#153).
            Property(name="yearIssued", data_type=integer, index_range_filters=True),
            Property(name="startChar", data_type=integer),
            Property(name="startWord", data_type=integer),
            Property(name="wordOpenAtStart", data_type=DataType.BOOL),
            *(Property(name=name, data_type=DataType.TEXT_ARRAY) for name in TASK_CLASSES),
            Property(name="classification_provenance", data_type=text, tokenization=Tokenization.FIELD,
                     index_filterable=True, index_searchable=False),
        ],
        references=[
            ReferenceProperty(name="document", target_collection=names.document_collection_name),
            ReferenceProperty(name=names.user_collection_link_name, target_collection=names.user_collection_name),
        ],
    )


def _value(value: Any) -> Any:
    """An enum's value, anything else as is (for JSON)."""
    return getattr(value, "value", value)


async def describe_collections(client: WeaviateAsyncClient, names: CollectionNames) -> dict[str, Any]:
    """Collection name -> properties (type, tokenization, indexes), references, named vectors
    (index type and distance) and the BM25 parameters and stopwords: what decides a ranking."""
    configs = await client.collections.list_all(simple=False)
    found: dict[str, Any] = {}
    for name in app_collections(names):
        config = configs.get(name)
        if config is None:
            continue
        inverted = config.inverted_index_config
        found[name] = {
            "properties": [{
                "name": p.name, "data_type": _value(p.data_type), "tokenization": _value(p.tokenization),
                "index_searchable": p.index_searchable, "index_filterable": p.index_filterable,
                "index_range_filters": p.index_range_filters,
            } for p in config.properties],
            "references": [{"name": r.name, "target": list(r.target_collections)} for r in config.references],
            "vectors": {vector_name: _vector(vector) for vector_name, vector in (config.vector_config or {}).items()},
            "bm25": {"b": inverted.bm25.b, "k1": inverted.bm25.k1} if inverted else None,
            "stopwords": {"preset": _value(inverted.stopwords.preset),
                          "additions": inverted.stopwords.additions,
                          "removals": inverted.stopwords.removals} if inverted else None,
        }
    return found


def _vector(vector: Any) -> dict[str, Any]:
    index = vector.vector_index_config
    return {
        "vectorizer": _value(vector.vectorizer.vectorizer),
        "index": _value(index.vector_index_type()) if index is not None else None,
        "distance": _value(getattr(index, "distance_metric", None)),
        "ef_construction": getattr(index, "ef_construction", None),
        "max_connections": getattr(index, "max_connections", None),
        "quantizer": type(index.quantizer).__name__ if getattr(index, "quantizer", None) else None,
    }
