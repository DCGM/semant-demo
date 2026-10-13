"""The document year copied to text chunks: ``Chunks.yearIssued`` schema, reads, updates (#153).

Year filters of the chunk search apply to ``Chunks.yearIssued`` itself: range predicates
through the ``document`` reference give wrong results (empty intersections) in Weaviate
1.34. Reads return ids, the year and the document reference, never text or vectors.
Collection names are resolved through aliases first (the deployment serves ``Chunks`` as
an alias of ``Chunks_test``). Never creates, drops or alters a collection;
``add_year_property`` only adds the property, on explicit request.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.config import DataType, Property
from weaviate.classes.query import Filter, QueryReference

YEAR = "yearIssued"
DOCUMENT_LINK = "document"


@dataclass(frozen=True)
class ChunkYear:
    """A chunk's id, its stored year (None when absent) and the documents it references."""
    id: UUID
    year: Any
    document_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class YearProperty:
    data_type: str
    range_index: bool
    filterable: bool


async def year_property(client: WeaviateAsyncClient, collection: str, name: str = YEAR) -> YearProperty | None:
    """The declared property ``name`` of the collection, None if it is not declared."""
    config = await client.collections.get(collection).config.get()
    for prop in config.properties:
        if prop.name == name:
            return YearProperty(prop.data_type.value, bool(prop.index_range_filters), bool(prop.index_filterable))
    return None


async def property_names(client: WeaviateAsyncClient, collection: str) -> list[str]:
    config = await client.collections.get(collection).config.get()
    return sorted(prop.name for prop in config.properties)


async def add_year_property(client: WeaviateAsyncClient, collection: str) -> None:
    """Declare ``yearIssued`` (``int``, filterable, range index); existing chunks have no value."""
    await client.collections.get(collection).config.add_property(
        Property(name=YEAR, data_type=DataType.INT, index_filterable=True, index_range_filters=True))


async def read_document_years(client: WeaviateAsyncClient, collection: str, page_size: int) -> dict[UUID, Any]:
    """Document id -> stored ``yearIssued`` (None when absent), for every document."""
    documents = client.collections.get(collection)
    years: dict[UUID, Any] = {}
    after = None
    while True:
        response = await documents.query.fetch_objects(limit=page_size, after=after, return_properties=[YEAR])
        for obj in response.objects:
            years[obj.uuid] = obj.properties.get(YEAR)
        if len(response.objects) < page_size:
            return years
        after = response.objects[-1].uuid


def _chunk(obj) -> ChunkYear:
    refs = (obj.references or {}).get(DOCUMENT_LINK)
    return ChunkYear(obj.uuid, obj.properties.get(YEAR),
                     tuple(sorted({o.uuid for o in refs.objects})) if refs else ())


def _returned(with_year: bool) -> dict[str, Any]:
    return dict(return_properties=[YEAR] if with_year else [],
                return_references=QueryReference(link_on=DOCUMENT_LINK, return_properties=[]))


async def read_chunk_page(client: WeaviateAsyncClient, collection: str, after: UUID | None, limit: int,
                          with_year: bool = True) -> list[ChunkYear]:
    """Up to ``limit`` chunks following ``after`` in id order (cursor paging). Without
    ``with_year`` (the property is not declared yet) every year reads as None."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, **_returned(with_year))
    return [_chunk(obj) for obj in response.objects]


async def read_chunks(client: WeaviateAsyncClient, collection: str, ids: list[UUID],
                      with_year: bool = True) -> dict[UUID, ChunkYear]:
    """The chunks with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), **_returned(with_year))
    return {obj.uuid: _chunk(obj) for obj in response.objects}


async def set_chunk_year(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, year: int | None) -> None:
    """Set (or with None remove) the chunk's ``yearIssued``; other properties, references and
    the vector are kept (a merge)."""
    await client.collections.get(collection).data.update(uuid=chunk_id, properties={YEAR: year})


async def count_in_range(client: WeaviateAsyncClient, collection: str, first: int, last: int) -> int:
    """Chunks with ``first <= yearIssued <= last``: the predicates the search uses."""
    result = await client.collections.get(collection).aggregate.over_all(
        filters=Filter.all_of([Filter.by_property(YEAR).greater_or_equal(first),
                               Filter.by_property(YEAR).less_or_equal(last)]),
        total_count=True)
    return result.total_count or 0

