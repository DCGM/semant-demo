from enum import Enum
from pydantic import BaseModel
from typing import Literal, TypedDict, Any
from datetime import datetime
import uuid
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, JSON, Integer, DateTime, Text
import sqlalchemy.sql.functions as funcs


class SearchType(str, Enum):
    text = "text"
    vector = "vector"
    hybrid = "hybrid"


class APIType(str, Enum):
    ollama = "OLLAMA"
    openai = "OPENAI"
    google = "GOOGLE"
    metacentrum = "METACENTRUM"


class FilterType(str, Enum):
    nominal = "nominal"
    interval = "interval"


class NominalFilterValue(BaseModel):
    user_form: str
    backend_form: str


class SearchFilter(BaseModel):
    id: str
    name: str
    type: FilterType
    description: str
    target_property: str
    values: list[NominalFilterValue] | None = None
    min_value: int | float | None = None
    max_value: int | float | None = None


class SearchFilterInput(BaseModel):
    id: str
    values: list[str | int | float] | str | int | float | None = None
    min_value: int | float | datetime | None = None
    max_value: int | float | datetime | None = None


class SearchFiltersResponse(BaseModel):
    filters: list[SearchFilter]


class SummaryRequestBase(BaseModel):
    search_title_generate: bool = True
    search_title_prompt: str | None = None
    search_title_model: str | None = None
    # upper bound on number of words in the title
    search_title_brevity: int | None = None

    search_summary_generate: bool = True
    search_summary_prompt: str | None = None
    search_summary_model: str | None = None
    # upper bound on number of words in the summary
    search_summary_brevity: int | None = None

    search_results_summary_generate: bool = True
    search_results_summary_prompt: str | None = None
    search_results_summary_model: str | None = None
    # upper bound on number of words in the summary
    search_results_summary_brevity: int | None = None


class SearchRequest(SummaryRequestBase):
    query: str
    limit: int = 10
    user_collection_id: str | None = None
    type: SearchType = SearchType.hybrid
    hybrid_search_alpha: float = 0.5
    search_llm_filter: bool = False

    filters: list[SearchFilterInput] | None = None

    min_year: int | None = None
    max_year: int | None = None
    min_date: datetime | None = None
    max_date: datetime | None = None
    language: str | None = None

    tag_uuids: list[str]
    positive: bool
    automatic: bool

    is_hyde: bool = False  # variable which indicates if query is document


class Document(BaseModel):
    id: uuid.UUID
    library: str
    title: str | None = None
    subtitle: str | None = None
    # string is here because partNumber is sometimes string in testing DB
    partNumber: int | str | None = None
    partName: str | None = None
    yearIssued: int | None = None
    dateIssued: datetime | None = None
    author: str | None = None
    publisher: str | None = None
    language: str | None = None
    description: str | None = None
    url: str | uuid.UUID | None = None
    public: bool | None = None
    documentType: str | None = None
    keywords: str | list[str] | None = None
    genre: str | None = None
    placeTerm: str | None = None


class TextChunk(BaseModel):
    id: uuid.UUID
    text: str
    start_page_id: uuid.UUID
    from_page: int
    to_page: int
    document: uuid.UUID
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


class TextChunkWithDocument(TextChunk):
    query_title: str | None = None
    query_summary: str | None = None
    summary: str | None = None
    document_object: Document


class DocumentDetailTextChunkWithUserCollectionInfo(TextChunk):
    in_user_collection: bool


class DocumentDetail(BaseModel):
    document: Document
    chunks: list[DocumentDetailTextChunkWithUserCollectionInfo]

class SearchResponse(BaseModel):
    results: list[TextChunkWithDocument]
    # Optional overall query-based summary of the results
    results_summary: str | None = None
    search_request: SearchRequest
    time_spent: float
    search_log: list[str]

class SummaryRequest(SummaryRequestBase):
    search_response: SearchResponse

class SummaryResponse(BaseModel):
    summary: str
    time_spent: float

class RagRouteConfig(BaseModel):
    id: str
    name: str
    description: str

# rag message format for purpose of history

class RagChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RagSearch(BaseModel):
    search_type: SearchType = SearchType.hybrid
    alpha: float = 0.5
    limit: int = 10
    search_query: str | None = None
    min_year: int | None = None
    max_year: int | None = None
    min_date: datetime | None = None
    max_date: datetime | None = None
    language: str | None = None

# main request used by rag


class RagRequest(BaseModel):
    # rag parameters
    question: str
    # chat history, to keep context
    history: list[RagChatMessage] | None = None
    # search parameters
    rag_search: RagSearch
    previous_documents: list[TextChunkWithDocument] = []

# rag request from frontend to backend


class RagRequestMain(BaseModel):
    rag_id: str
    rag_request: RagRequest

# rag response return by rag backend


class RagResponse(BaseModel):
    rag_answer: str
    time_spent: float
    response_id: str
    sources: list[TextChunkWithDocument]


class ExtractedMeradata(BaseModel):
    min_year: int | None = None
    max_year: int | None = None
    min_date: datetime | None = None
    min_date: datetime | None = None
    language: int | None = None

# class defining state of the adaptive rag


class AdaptiveRagState(TypedDict):
    language: str | None  # ces, des, eng, ...
    question: str
    original_question: str
    queries: list[str]
    context_sufficient: bool
    history: list[Any]
    documents: list[Any]
    generation: str
    metadata: ExtractedMeradata
    metadata_extraction_allowed: bool
    retrieval_iteration_counter: int
    generation_iteration_counter: int
    feedback: str
    web_search_performed: bool


class AvailableRagConfigurationsResponse(BaseModel):
    available_models: list[str]
    used_models: list[str]
    default_temperature: float
    temperature_range: dict[str, float]
    available_api_keys: list[str]


class ExplainRequest(BaseModel):
    rag_id: str
    selected_text: str
    # full text of an answer from which selected_text came from
    full_answer: str
    # chat history, to keep context
    history: list[RagChatMessage] | None = None
    # sources / chunks of the id question
    sources: list[TextChunkWithDocument]


class FeedbackRequest(BaseModel):
    rag_id: str
    response_id: str
    question: str
    sources: list[TextChunkWithDocument]
    answer: str
    rating: int                                     # should be: 1 - like / -1 - dislike
    error_types: list[str] | None = None
    comment: str | None = None


class AppFeedbackRequest(BaseModel):
    type: str
    subject: str | None = None
    message: str
    email: str | None = None


class CreateResponse(BaseModel):
    created: bool
    message: str

# Weaviate collections
class CollectionNames(BaseModel):
    chunks_collection_name: str
    tag_collection_name: str
    user_collection_name: str
    document_collection_name: str
    span_collection_name: str
    user_collection_link_name: str
    tag_to_user_collection_link_name: str
class TagData(BaseModel):
    tag_name: str  # name of the tag
    tag_shorthand: str  # shorthand for the name
    tag_color: str  # color assigned to the tag
    tag_pictogram: str  # image
    tag_definition: str  # description of the tag
    tag_examples: list[str]  # list of examples what should be tagged
    collection_name: str
    tag_uuid: uuid.UUID | None

# TagSpans

class SpanType(str, Enum):
    pos = "pos"
    neg = "neg"
    auto = "auto"


class TagSpan(BaseModel):
    id: str | None = None
    chunkId: str
    tagId: str
    start: int
    end: int
    type: SpanType | None = None
    # Optional metadata produced by AI/automatic taggers. Always None for
    # manual spans; populated when an LLM proposes a span via the Topicer
    # service. Stored alongside the span itself in the database.
    reason: str | None = None
    confidence: float | None = None

# Task Model
TasksBase = declarative_base()
class RagUserFeedback(TasksBase):
    __tablename__ = "rag_user_feedback"
    id = Column(Integer, primary_key=True, autoincrement=True)
    response_id = Column(String(36), index=True, unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=funcs.now())
    rag_id = Column(String(255), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)  # 1 - like, -1 - dislike
    # list of error types, if rating is -1
    error_types = Column(JSON, nullable=True)
    comment = Column(Text, nullable=True)
    sources = Column(JSON, nullable=True)
