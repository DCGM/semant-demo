"""Models shared outside the features: RAG and feedback HTTP models and the configured
Weaviate collection names. Feature models live in each feature's ``schemas.py``; shared
corpus models in ``schema/``; SQL tables in ``adapters/sql/``.
"""
from pydantic import BaseModel
from typing import Literal, TypedDict, Any
from datetime import datetime

from semant_demo.features.search.schemas import SearchType, TextChunkWithDocument


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
    max_date: datetime | None = None
    language: str | None = None

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
