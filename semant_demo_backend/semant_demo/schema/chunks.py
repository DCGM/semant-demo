"""Chunk projections. Each one serves a different read; they are not interchangeable.

- :class:`TextChunk`: a chunk with its stored properties, base of the search hit
  (``features/search/schemas.TextChunkWithDocument``) and of the document view chunk
  (``schema/documents.DocumentDetailTextChunkWithUserCollectionInfo``).
- :class:`Chunk`: a chunk listed for a collection (``in_collection``), without its
  document or entities.
- :class:`ChunkText`: internal, the canonical text and position of a chunk for offset
  checks; not an HTTP model.
"""
from uuid import UUID

from pydantic import BaseModel


class TextChunk(BaseModel):
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


class Chunk(BaseModel):
    id: UUID
    text: str
    start_page_id: UUID
    from_page: int
    to_page: int
    end_paragraph: bool = True
    title: str | None = None
    language: str | None = None
    order: int
    in_collection: bool = False


class ChunkText(BaseModel):
    """A chunk's position in its document and its canonical text (for offset checks)."""
    id: UUID
    document_id: UUID | None
    order: int
    text: str
