"""Corpus document models: the document metadata and the document view."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from semant_demo.schema.chunks import TextChunk


class Document(BaseModel):
    """
    Bibliographic metadata of a corpus document, as stored on the ``Documents`` object.

    The one document model of every read (document, browse, collection documents,
    document view, search hits). Properties that a store does not hold are absent
    (``None``); the type unions accept the variants found in existing stores.
    """
    id: UUID
    library: str | None = None
    """Source digital library. Document view and search answers fill in ``"mzk"`` when the
    store has none; other reads leave it absent."""
    title: str | None = None
    subtitle: str | None = None
    # A string in the stored schema, a number in some older data.
    partNumber: int | str | None = None
    partName: str | None = None
    yearIssued: int | None = None
    dateIssued: datetime | None = None
    author: list[str] | None = None
    """Author names (stored as ``text[]``)."""
    publisher: str | None = None
    language: str | None = None
    description: str | None = None
    url: str | UUID | None = None
    public: bool | None = None
    documentType: str | None = None
    keywords: list[str] | None = None
    genre: str | None = None
    placeTerm: str | None = None
    placeOfPublication: str | None = None
    editors: list[str] | None = None
    seriesName: str | None = None
    edition: str | None = None
    illustrators: list[str] | None = None
    translators: list[str] | None = None
    redaktors: list[str] | None = None
    seriesNumber: str | None = None


class DocumentBrowse(BaseModel):
    items: list[Document]
    next_offset: int | None = None
    has_more: bool
    total_count: int


class DocumentStats(BaseModel):
    document_id: str
    collection_id: str
    chunks_in_collection: int
    total_chunks: int
    annotations_count: int
    distinct_tags_count: int


class DocumentDetailTextChunkWithUserCollectionInfo(TextChunk):
    """A chunk of the document view. ``text`` is the canonical stored text that span
    offsets refer to (never display-normalized)."""
    in_user_collection: bool


class DocumentDetail(BaseModel):
    """A document with all its chunks, each marked with membership in one collection."""
    document: Document
    chunks: list[DocumentDetailTextChunkWithUserCollectionInfo]
