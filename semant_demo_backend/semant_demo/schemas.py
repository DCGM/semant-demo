from enum import Enum
from pydantic import BaseModel
from typing import Literal
from datetime import datetime
import uuid

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
    title: str | None = None
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
    keywords: str | None = None
    genre: str | None = None
    placeTerm: str | None = None


class TextChunk(BaseModel):
    id: uuid.UUID
    title: str = "<N/A>"
    text: str
    start_page_id: uuid.UUID
    from_page: int
    to_page: int
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

class RagChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class RagQuestionRequest(BaseModel):
    search_response: SearchResponse
    question: str
    history: list[RagChatMessage] | None = None    # chat history, to keep context

class RagResponse(BaseModel):
    rag_answer: str
    time_spent: float


