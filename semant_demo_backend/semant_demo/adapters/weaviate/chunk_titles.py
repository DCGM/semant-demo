"""Chunk titles (#575): the reads that select and prepare chunks for title generation, and
the title-only write.

Reads return a chunk's id, stored title, language and document reference; the text only for
the chunks whose title is generated, never vectors. The write is a merge of ``title`` alone:
text, order, positions, references, vectors and other properties are kept. Collection names
are resolved through aliases by the caller. Never creates, drops or alters a collection or a
property.
"""
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference

from semant_demo.adapters.weaviate.paging import fetch_all

TITLE = "title"
LANGUAGE = "language"
TEXT = "text"
DOCUMENT_LINK = "document"


@dataclass(frozen=True)
class ChunkState:
    """A chunk's id, stored title and language (None when absent) and the documents it references."""
    id: UUID
    title: Any
    language: Any
    document_ids: tuple[UUID, ...]


async def declared_types(client: WeaviateAsyncClient, collection: str) -> dict[str, str]:
    """Property name -> declared data type of the collection."""
    config = await client.collections.get(collection).config.get()
    return {prop.name: prop.data_type.value for prop in config.properties}


def _state(obj, with_language: bool) -> ChunkState:
    refs = (obj.references or {}).get(DOCUMENT_LINK)
    return ChunkState(obj.uuid, obj.properties.get(TITLE), obj.properties.get(LANGUAGE) if with_language else None,
                      tuple(sorted({o.uuid for o in refs.objects})) if refs else ())


def _returned(with_language: bool) -> dict[str, Any]:
    # A store without a declared ``language`` refuses a query naming it (Weaviate 1.40).
    return dict(return_properties=[TITLE, LANGUAGE] if with_language else [TITLE],
                return_references=QueryReference(link_on=DOCUMENT_LINK, return_properties=[]))


async def read_chunk_page(client: WeaviateAsyncClient, collection: str, after: UUID | None, limit: int,
                          with_language: bool = True) -> list[ChunkState]:
    """Up to ``limit`` chunks following ``after`` in id order (cursor paging, every chunk)."""
    response = await client.collections.get(collection).query.fetch_objects(
        limit=limit, after=after, **_returned(with_language))
    return [_state(obj, with_language) for obj in response.objects]


async def read_chunks(client: WeaviateAsyncClient, collection: str, ids: list[UUID],
                      with_language: bool = True) -> dict[UUID, ChunkState]:
    """The chunks with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), **_returned(with_language))
    return {obj.uuid: _state(obj, with_language) for obj in response.objects}


async def read_texts(client: WeaviateAsyncClient, collection: str, ids: list[UUID]) -> dict[UUID, Any]:
    """Chunk id -> stored text, for the chunks with these ids that exist."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=[TEXT])
    return {obj.uuid: obj.properties.get(TEXT) for obj in response.objects}


async def document_chunk_ids(client: WeaviateAsyncClient, collection: str, document_id: UUID) -> list[UUID]:
    """The ids of the chunks referencing the document. More chunks than Weaviate's
    ``QUERY_MAXIMUM_RESULTS`` fail instead of being truncated (``paging.fetch_all``)."""
    objects = await fetch_all(client.collections.get(collection), page_size=1000,
                              filters=Filter.by_ref(DOCUMENT_LINK).by_id().equal(document_id), return_properties=[])
    return [obj.uuid for obj in objects]


async def read_document_titles(client: WeaviateAsyncClient, collection: str, ids: list[UUID],
                               with_title: bool = True) -> dict[UUID, Any]:
    """Document id -> stored ``title`` (None when absent), for the documents with these ids that
    exist. Without ``with_title`` (the collection does not declare it) every title is None."""
    if not ids:
        return {}
    response = await client.collections.get(collection).query.fetch_objects(
        filters=Filter.by_id().contains_any(ids), limit=len(ids), return_properties=[TITLE] if with_title else [])
    return {obj.uuid: obj.properties.get(TITLE) if with_title else None for obj in response.objects}


async def set_chunk_title(client: WeaviateAsyncClient, collection: str, chunk_id: UUID, title: str) -> None:
    """Set the chunk's ``title``; other properties, references and vectors are kept (a merge)."""
    await client.collections.get(collection).data.update(uuid=chunk_id, properties={TITLE: title})
