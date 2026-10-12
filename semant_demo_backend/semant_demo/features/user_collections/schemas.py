from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class Collection(BaseModel):
    id: UUID
    name: str
    owner: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    color: str
    shared_with_count: int = 0
    is_shared_with_me: bool = False


class PostCollection(BaseModel):
    name: str
    description: str | None = None
    color: str


class PatchCollection(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class PatchCollectionOwner(BaseModel):
    user_id: UUID


class ShareCollectionRequest(BaseModel):
    user_id: UUID


class CollectionStats(BaseModel):
    collection_id: UUID
    documents_count: int
    chunks_count: int
    annotations_count: int
    tags_count: int



class CollectionChunk(BaseModel):
    """A chunk listed for a collection (``in_collection``), without its document or entities."""
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


class CreateResponse(BaseModel):
    created: bool
    message: str
