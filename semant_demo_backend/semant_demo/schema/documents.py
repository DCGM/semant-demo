from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class Document(BaseModel):
    id: UUID

    title: str | None = None
    public: bool | None = None
    documentType: str | None = None
    partNumber: str | None = None
    dateIssued: datetime | None = None
    yearIssued: int | None = None
    language: str | None = None
    publisher: str | None = None
    placeOfPublication: str | None = None
    subtitle: str | None = None
    editors: list[str] | None = None
    partName: str | None = None
    seriesName: str | None = None
    edition: str | None = None
    author: list[str] | None = None
    illustrators: list[str] | None = None
    translators: list[str] | None = None
    redaktors: list[str] | None = None
    seriesNumber: str | None = None
    keywords: list[str] | None = None
    
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
