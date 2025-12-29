from enum import Enum
from pydantic import BaseModel
from typing import Literal, TypedDict, Any
from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON, Integer, DateTime
import sqlalchemy.sql.functions as funcs

class SearchType(str, Enum):
    text = "text"
    vector = "vector"
    hybrid = "hybrid"


class SummaryRequestBase(BaseModel):
    search_title_generate: bool = True
    search_title_prompt: str | None = None
    search_title_model: str | None = None
    search_title_brevity: int | None = None  # upper bound on number of words in the title

    search_summary_generate: bool = True
    search_summary_prompt: str | None = None
    search_summary_model: str | None = None
    search_summary_brevity: int | None = None  # upper bound on number of words in the summary

    search_results_summary_generate: bool = True
    search_results_summary_prompt: str | None = None
    search_results_summary_model: str | None = None
    search_results_summary_brevity: int | None = None  # upper bound on number of words in the summary


class SearchRequest(SummaryRequestBase):
    query: str
    limit: int = 10
    type: SearchType = SearchType.hybrid
    hybrid_search_alpha: float = 0.5
    search_llm_filter: bool = False

    min_year: int | None = None
    max_year: int | None = None
    min_date: datetime | None = None
    max_date: datetime | None = None
    language: str | None = None

    tag_uuids: list[str]
    positive: bool
    automatic: bool

class Document(BaseModel):
    id: uuid.UUID
    library: str
    title: str | None = None
    subtitle: str | None = None
    partNumber: int | str | None = None
    partName: str | None = None
    yearIssued: int | None = None
    dateIssued: datetime | None = None
    author: str | None = None
    publisher: str | None = None
    language: str | None = None
    description: str | None = None
    url: str | None = None
    public: bool | None = None
    documentType: str | None = None
    keywords: str | list[str] | None = None
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

class FilteredChunksByTags(BaseModel):
    chunk_id: str
    positive_tags_ids: list[str]
    automatic_tags_ids: list[str]

class FilterChunksByTagsResponse(BaseModel):
    chunkTags: list[FilteredChunksByTags]

class FilterChunksByTagsRequest(BaseModel):
    chunkIds: list[str]
    tagIds: list[str]
    positive: bool
    automatic: bool

class SearchResponse(BaseModel):
    results: list[TextChunkWithDocument]
    results_summary: str | None = None  # Optional overall query-based summary of the results
    search_request: SearchRequest
    time_spent: float
    search_log: list[str]
    tags_result: list[FilteredChunksByTags]   # TODO: Should it be here or in Chunks? (xtomas36)


class SummaryRequest(SummaryRequestBase):
    search_response: SearchResponse


class SummaryResponse(BaseModel):
    summary: str
    time_spent: float

class RagRouteConfig(BaseModel):
    id: str
    name: str
    description: str

#rag message format for purpose of history
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

#main request used by rag 
class RagRequest(BaseModel):
    # rag parameters
    question: str
    history: list[RagChatMessage] | None = None    # chat history, to keep context
    # search parameters
    rag_search: RagSearch

#rag request from frontend to backend
class RagRequestMain(BaseModel):
    rag_id : str
    rag_request: RagRequest
    
#rag response return by rag backend
class RagResponse(BaseModel):
    rag_answer: str
    time_spent: float
    sources: list[TextChunkWithDocument]

# class defining state of the adaptive rag
class AdaptiveRagState(TypedDict):
    question: str
    queries: list[str]
    history: list[Any]
    documents: list[Any]
    generation: str
    metadata: dict[str, Any]
    iteration_counter: int


class AvailableRagConfigurationsResponse(BaseModel):
    available_models: list[str]
    used_models: list[str]
    default_temperature: float
    temperature_range: dict[str, float]
    available_api_keys: list[str]

class CreateResponse(BaseModel):
    created: bool
    message: str


class TagStartResponse(BaseModel):
    job_started: bool
    task_id: str
    message: str


class TagReqTemplate(BaseModel):
    tag_name: str  # name of the tag
    tag_shorthand: str  # shorthand for the name
    tag_color: str  # color assigned to the tag
    tag_pictogram: str  # image
    tag_definition: str  # description of the tag
    tag_examples: list[str]  # list of examples what should be tagged
    collection_name: str


class TagResponse(BaseModel):
    texts: list[str]
    tags: list[str]


class TagType(str, Enum):
    positive = "positive"
    negative = "negative"
    automatic = "automatic"


class TagData(BaseModel):
    tag_name: str  # name of the tag
    tag_shorthand: str  # shorthand for the name
    tag_color: str  # color assigned to the tag
    tag_pictogram: str  # image
    tag_definition: str  # description of the tag
    tag_examples: list[str]  # list of examples what should be tagged
    collection_name: str
    tag_uuid: uuid.UUID


class TagTasksResponse(BaseModel):
    taskIDs: list[uuid.UUID]


class CancelTaskResponse(BaseModel):
    message: str
    taskCanceled: bool


class GetTagsResponse(BaseModel):
    tags_lst: list[TagData]


class GetTaggedChunksReq(BaseModel):
    tag_uuids: list[uuid.UUID]
    tag_type: TagType


class RemoveTagReq(BaseModel):
    tag_uuids: list[uuid.UUID]


class TaggedChunks(BaseModel):
    tag_uuid: uuid.UUID  # uuid of a tag selected in UI and belonging to the text chunk
    text_chunk: str  # actual text chunk
    chunk_id: str  # to apply changes later
    chunk_collection_name: str  # send collection name of the chunk for faster manipulation later


class GetTaggedChunksResponse(BaseModel):
    chunks_with_tags: list[TaggedChunks]  # list of pairs text chunk and id belonging to it


class ApproveTagReq(BaseModel):
    approved: bool
    chunkID: str
    tagID: str
    chunk_collection_name: str


class ApproveTagResponse(BaseModel):
    successful: bool
    approved: bool


class RemoveTagsResponse(BaseModel):
    successful: bool


# User collection
class UserCollectionReqTemplate(BaseModel):
    collection_name: str  # name of the collection
    user_id: str  # user id


class Collection(BaseModel):
    id: str
    name: str
    user_id: str


class GetCollectionsResponse(BaseModel):
    collections: list[Collection]
    userId: str


class Chunk2CollectionReq(BaseModel):
    collectionId: str  # id of the collection
    chunkId: str  # chunk id


class CollectionChunks(BaseModel):
    text_chunk: str  # actual text chunk
    chunk_id: str  # to apply changes later


class GetCollectionChunksResponse(BaseModel):
    chunks_of_collection: list[CollectionChunks]  # list of pairs text chunk and id belonging to it


# Task Model
TasksBase = declarative_base()


class Task(TasksBase):
    __tablename__ = "tasks"
    taskId = Column(String(36), primary_key=True)  # 36 is max number of chars in uuid
    status = Column(String(20), default="PENDING")  # PENDING|RUNNING|COMPLETED|FAILED
    result = Column(JSON, nullable=True)
    all_texts_count = Column(Integer, nullable=True)
    processed_count = Column(Integer, nullable=True)
    collection_name = Column(String, nullable=True)
    tag_id = Column(String(36))  # 36 is max number of chars in uuid
    tag_processing_data = Column(JSON, nullable=True)
    time_updated = Column(DateTime(timezone=True),
                          onupdate=funcs.now())  # store updated time for loading tasks sorted by time updated
    task_name = Column(String, nullable=True)


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
