from enum import Enum
from pydantic import BaseModel
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON, Integer

class SearchType(str, Enum):
    text = "text"
    vector = "vector"
    hybrid = "hybrid"


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    type: SearchType = SearchType.hybrid
    search_title_generate: bool = True
    search_title_prompt: str | None = None
    search_title_model: str | None = None
    search_summary_generate: bool = True
    search_summary_prompt: str | None = None
    search_summary_model: str | None = None
    search_llm_filter: bool = False

    min_year: int | None = None
    max_year: int | None = None
    min_date: datetime | None = None
    max_date: datetime | None = None
    language: str | None = None


class Document(BaseModel):
    id: uuid.UUID
    library: str
    title: str
    subtitle: str | None = None
    partNumber: int | None = None
    partName: str | None = None
    yearIssued: int | None = None
    dateIssued: datetime | None = None
    author: str | None = None
    publisher: str | None = None
    language: str | None = None
    description: str | None = None
    url: str | None = None
    public: str | None = None
    documentType: str | None = None
    keywords: str | list[str] | None = None
    genre: str | None = None
    placeTerm: str | None = None

"""
    start_page_id: uuid.UUID #Optional[uuid.UUID] = None
    from_page: int #Optional[int] = None
    to_page: int #Optional[int] = None

    start_page_id: Optional[uuid.UUID] = None
    from_page: Optional[int] = None
    to_page: Optional[int] = None
"""

from typing import Optional
class TextChunk(BaseModel):
    id: uuid.UUID
    title: str = "<N/A>"
    text: str
    start_page_id: uuid.UUID #Optional[uuid.UUID] = None
    from_page: int #Optional[int] = None
    to_page: int #Optional[int] = None
    end_paragraph: bool = True
    language: str | None = None
    document: uuid.UUID

    ner_P: list[str] | None = None  # Person entities
    ner_T: list[str] | None = None  # Temporal entities
    ner_A: list[str] | None = None  # Address entities
    ner_G: list[str] | None = None  # Geographical entities
    ner_I: list[str] | None = None  # Institution entities
    ner_M: list[str] | None = None  # Media entities
    ner_O: list[str] | None = None  # Cultural artifacts


class TextChunkWithDocument(TextChunk):
    query_title: str | None = None
    query_summary: str | None = None
    summary: str | None = None
    document_object: Document


class SearchResponse(BaseModel):
    results: list[TextChunkWithDocument]
    search_request: SearchRequest
    time_spent: float
    search_log: list[str]

class SummaryResponse(BaseModel):
    summary: str
    time_spent: float

class TagStartResponse(BaseModel):
    job_started: bool
    task_id: str
    message: str

class TagReqTemplate(BaseModel):
    tag_name: str           # name of the tag
    tag_shorthand: str          # shorthand for the name
    tag_color: str              # color assigned to the tag
    tag_pictogram: str          # image
    tag_definition: str     # description of the tag
    tag_examples: list[str] # list of examples what should be tagged
    collection_name: str

class TagResponse(BaseModel):
    texts: list[str]
    tags: list[str]

class TagData(BaseModel):
    tag_name: str           # name of the tag
    tag_shorthand: str          # shorthand for the name
    tag_color: str              # color assigned to the tag
    tag_pictogram: str          # image
    tag_definition: str     # description of the tag
    tag_examples: list[str] # list of examples what should be tagged
    collection_name: str
    tag_uuid: uuid.UUID

class GetTagsResponse(BaseModel):
    tags_lst: list[TagData]

class GetTaggedChunksReq(BaseModel):
    tag_uuids: list[uuid.UUID]

class TaggedChunks(BaseModel):
    tag_uuids : list[uuid.UUID] # uuids of all tags selected in UI and belonging to the text chunk
    text_chunk: str # actual text chunk
    chunk_id: str # to apply changes later

class GetTaggedChunksResponse(BaseModel):
    chunks_with_tags : list[TaggedChunks] # list of pairs text chunk and id belonging to it

# Task Model
TasksBase = declarative_base()
class Task(TasksBase):
    __tablename__ = "tasks"
    taskId = Column(String(36), primary_key=True)
    status = Column(String(20), default="PENDING")  # PENDING|RUNNING|COMPLETED|FAILED
    result = Column(JSON, nullable=True)
    all_texts_count = Column(Integer, nullable=True)
    processed_count = Column(Integer, nullable=True)
    collection_name = Column(String, nullable=True)

tag_class = {
    "class": "Tag",
    "properties": [
        {"name": "tag_name", "dataType": ["string"]},
        {"name": "tag_shorthand", "dataType": ["string"]},
        {"name": "tag_color", "dataType": ["string"]},
        {"name": "tag_pictogram", "dataType": ["string"]},
        {"name": "tag_definition", "dataType": ["text"]},
        {"name": "tag_examples", "dataType": ["text[]"]},
        {"name": "collection_name", "dataType": ["string"]}
    ]
}
