"""Corpus document models: the document metadata, its chunks and the document view.

Chunk projections are owned by the feature whose read they serve and are not
interchangeable: :class:`DocumentChunk` and :class:`DocumentViewChunk` here,
``features/search/schemas.SearchResultChunk`` (display text),
``features/user_collections/schemas.CollectionChunk`` and the internal
``features/annotations/schemas.AnnotationChunk``.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class Document(BaseModel):
    """
    Bibliographic metadata of a corpus document, as stored on the ``Documents`` object.

    The one document model of every read (document, browse, collection documents,
    document view, search hits). Properties that a store does not hold are absent
    (``None``); the type unions accept the variants found in existing stores.
    """
    id: UUID
    library: str | None = None
    """Source digital library code (e.g. ``"mzk"``), absent when the store has none. Never
    guessed: links to the original digitized document are built from it (#255)."""
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


class DocumentChunk(BaseModel):
    """A chunk with its stored properties. ``text`` is the canonical stored text that span
    offsets refer to; the search hit (``SearchResultChunk``) extends it with display text."""
    id: UUID
    text: str
    start_page_id: UUID
    from_page: int
    to_page: int
    document: UUID
    title: str | None = None
    end_paragraph: bool = True
    language: str | None = None
    order: int | None

    ner_P: list[str] | None = None  # Person entities
    ner_T: list[str] | None = None  # Temporal entities
    ner_A: list[str] | None = None  # Address entities
    ner_G: list[str] | None = None  # Geographical entities
    ner_I: list[str] | None = None  # Institution entities
    ner_M: list[str] | None = None  # Media entities
    ner_O: list[str] | None = None  # Cultural artifacts


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
    ai_max_chunks_per_tag: int | None = None
    """The most chunks one tag of optimized AI suggestions evaluates (``TOPICER_MAX_CHUNKS_PER_TAG``),
    for workload warnings; thorough suggestions evaluate ``chunks_in_collection``."""


class DocumentViewChunk(DocumentChunk):
    """A chunk of the document view. ``text`` is the canonical stored text that span
    offsets refer to (never display-normalized)."""
    in_user_collection: bool


class DocumentDetail(BaseModel):
    """A document with all its chunks, each marked with membership in one collection."""
    document: Document
    chunks: list[DocumentViewChunk]


class DocumentChunkWindow(BaseModel):
    """
    A bounded passage of a corpus document around one of its chunks (public): up to the
    requested number of chunks before and after the anchor chunk, in document order, with
    the anchor included. ``text`` is the canonical stored text. ``has_before``/``has_after``
    tell whether the document continues beyond the returned chunks.
    """
    document: Document
    chunks: list[DocumentChunk]
    anchor_chunk_id: UUID
    has_before: bool
    has_after: bool
    total_chunks: int


class AdjacentChunks(BaseModel):
    """
    Chunks directly before or after a chunk of a corpus document, in document order, without
    the chunk itself (public). Extends a :class:`DocumentChunkWindow` without reading the
    document metadata or chunk count again. ``has_more`` tells whether the document
    continues beyond them in that direction.
    """
    chunks: list[DocumentChunk]
    has_more: bool
