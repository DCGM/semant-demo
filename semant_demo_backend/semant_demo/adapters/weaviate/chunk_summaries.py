"""The documents' chunk-value summaries in Weaviate (#529): schema, chunk reads, document reads and writes.

For each chunk dimension (``language`` and the configured classifications) a ``Documents``
property ``chunk_<dimension>`` (``text[]``, ``field`` tokenization, filterable, not
searchable) holds the distinct values of the document's chunks, and
``chunk_summaries_computed_at`` (``date``) when they were last recomputed
(``features/documents/criteria.py``, ``maintenance/chunk_summaries.py``).

Chunk reads return ids, the dimension values and the document reference, never text or
vectors. Collection names are resolved through aliases first. Never creates, drops or alters a
collection; ``add_summary_properties`` only adds the missing properties, on explicit request.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property, Tokenization
from weaviate.classes.query import Filter, QueryReference

from semant_demo.features.documents.criteria import SUMMARIES_COMPUTED_AT, summary_property

DOCUMENT_LINK = "document"
SUMMARY_TYPE = "text[]"
SUMMARY_TOKENIZATION = "field"
COMPUTED_AT_TYPE = "date"


@dataclass(frozen=True)
class DeclaredProperty:
    data_type: str
    tokenization: str | None
    filterable: bool


@dataclass(frozen=True)
class ChunkValues:
    """A chunk's id, the documents it references and its values per dimension (declared ones)."""
    id: UUID
    document_ids: tuple[UUID, ...]
    values: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class DocumentSummaries:
    """A document's stored summaries: values per dimension (empty when absent) and when computed."""
    id: UUID
    values: dict[str, tuple[str, ...]]
    computed_at: datetime | None


async def declared_properties(client: WeaviateAsyncClient, collection: str) -> dict[str, DeclaredProperty]:
    config = await client.collections.get(collection).config.get()
    return {p.name: DeclaredProperty(p.data_type.value, p.tokenization.value if p.tokenization else None,
                                     bool(p.index_filterable))
            for p in config.properties}


def expected_properties(dimensions: Sequence[str]) -> dict[str, DeclaredProperty]:
    """The summary properties as ``add_summary_properties`` declares them."""
    return {**{summary_property(d): DeclaredProperty(SUMMARY_TYPE, SUMMARY_TOKENIZATION, True) for d in dimensions},
            SUMMARIES_COMPUTED_AT: DeclaredProperty(COMPUTED_AT_TYPE, None, True)}


async def add_summary_properties(client: WeaviateAsyncClient, collection: str, names: Sequence[str]) -> None:
    """Declare the named summary properties (from ``expected_properties``); existing documents
    have no value."""
    config = client.collections.get(collection).config
    for name in names:
        if name == SUMMARIES_COMPUTED_AT:
            prop = Property(name=name, data_type=DataType.DATE, index_filterable=True)
        else:
            prop = Property(name=name, data_type=DataType.TEXT_ARRAY, tokenization=Tokenization.FIELD,
                            index_filterable=True, index_searchable=False)
        await config.add_property(prop)


def _values(value) -> tuple[str, ...]:
    """The non-blank text values of a stored ``text`` or ``text[]`` value."""
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else value
    return tuple(item for item in items if isinstance(item, str) and item.strip())


def _chunk(obj, dimensions: Sequence[str]) -> ChunkValues:
    refs = (obj.references or {}).get(DOCUMENT_LINK)
    return ChunkValues(obj.uuid, tuple(sorted({o.uuid for o in refs.objects})) if refs else (),
                       {d: _values(obj.properties.get(d)) for d in dimensions})


async def read_chunk_page(client: WeaviateAsyncClient, collection: str, after: UUID | None, limit: int,
                          dimensions: Sequence[str]) -> list[ChunkValues]:
    """Up to ``limit`` chunks following ``after`` in id order (cursor paging), with the values
    of ``dimensions`` (properties the chunks declare) and the document reference."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, return_properties=list(dimensions),
        return_references=QueryReference(link_on=DOCUMENT_LINK, return_properties=[]))
    return [_chunk(obj, dimensions) for obj in response.objects]


def _summaries(obj, dimensions: Sequence[str], declared: bool) -> DocumentSummaries:
    if not declared:
        return DocumentSummaries(obj.uuid, {d: () for d in dimensions}, None)
    return DocumentSummaries(obj.uuid, {d: tuple(sorted(_values(obj.properties.get(summary_property(d)))))
                                        for d in dimensions},
                             obj.properties.get(SUMMARIES_COMPUTED_AT))


def _summary_names(dimensions: Sequence[str], declared: bool) -> list[str]:
    return [*(summary_property(d) for d in dimensions), SUMMARIES_COMPUTED_AT] if declared else []


async def read_document_page(client: WeaviateAsyncClient, collection: str, after: UUID | None, limit: int,
                             dimensions: Sequence[str], declared: bool) -> list[DocumentSummaries]:
    """Up to ``limit`` documents following ``after`` in id order with their stored summaries
    (none without ``declared``, when the properties are not declared yet)."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, return_properties=_summary_names(dimensions, declared))
    return [_summaries(obj, dimensions, declared) for obj in response.objects]


async def read_documents(client: WeaviateAsyncClient, collection: str, ids: Sequence[UUID],
                         dimensions: Sequence[str]) -> dict[UUID, DocumentSummaries]:
    """The stored summaries of the documents with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(list(ids)), limit=len(ids),
        return_properties=_summary_names(dimensions, True))
    return {obj.uuid: _summaries(obj, dimensions, True) for obj in response.objects}


async def write_summaries(client: WeaviateAsyncClient, collection: str, document_id: UUID,
                          values: dict[str, Sequence[str]], computed_at: datetime) -> None:
    """Replace the document's summaries (an empty list removes a dimension's values) and set
    the recomputation time; other properties, references and vectors are kept (a merge)."""
    await client.collections.get(collection).data.update(
        uuid=document_id,
        properties={**{summary_property(d): list(v) for d, v in values.items()}, SUMMARIES_COMPUTED_AT: computed_at})
