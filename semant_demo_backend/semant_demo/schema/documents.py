from pydantic import BaseModel, ConfigDict
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

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )
    
class DocumentBrowse(BaseModel):
    items: list[Document]
    nextOffset: int | None = None
    hasMore: bool
    totalCount: int

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )
