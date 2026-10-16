"""RAG HTTP models. The internal state of the adaptive RAG lives with its implementation
(``pipelines/incremental_rag.py``)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from semant_demo.features.search.schemas import SearchResultChunk, SearchType


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
    previous_documents: list[SearchResultChunk] = []

# rag request from frontend to backend


class RagRequestMain(BaseModel):
    rag_id: str
    rag_request: RagRequest
    # Search vector of every retrieval of this answer (GET /api/search/vectors); None: the default.
    vector: str | None = None

# rag response return by rag backend


class RagResponse(BaseModel):
    rag_answer: str
    time_spent: float
    response_id: str
    sources: list[SearchResultChunk]


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
    sources: list[SearchResultChunk]


class FeedbackRequest(BaseModel):
    rag_id: str
    response_id: str
    question: str
    sources: list[SearchResultChunk]
    answer: str
    rating: int                                     # should be: 1 - like / -1 - dislike
    error_types: list[str] | None = None
    comment: str | None = None
