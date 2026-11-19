from typing import Literal

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

from semant_demo.features.documents.schemas import LayoutStart


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


class CollectionPerson(BaseModel):
    """Someone who can use a collection now: its owner or a user it is shared with, by id,
    to name the actors of its annotations (#460)."""
    id: UUID
    name: str | None = None
    username: str | None = None
    role: Literal["owner", "member"]


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
    suggestions_count: int = 0
    """Unresolved AI suggestions (``auto`` spans) whose chunk belongs to the collection,
    counted like ``annotations_count`` (#770)."""



class CollectionChunk(BaseModel):
    """A chunk listed for a collection (``in_collection``), without its document or entities."""
    id: UUID
    text: str
    start_page_id: UUID | None = None
    from_page: int | None = None
    to_page: int | None = None
    """Absent for a text-only document (#785)."""
    end_paragraph: bool = True
    title: str | None = None
    language: str | None = None
    order: int
    in_collection: bool = False
    layoutStart: LayoutStart | None = None
    """The chunk's start on the page scans (``documents.schemas.LayoutStart``), when imported."""


class CreateResponse(BaseModel):
    created: bool
    message: str


TextUploadStatus = Literal["completed", "invalid", "not_written", "failed", "uncertain"]


class TextUploadFileResult(BaseModel):
    """What happened to one uploaded text file (#785).

    * ``completed``: the document, all its chunks with their vectors and its collection link
      are saved and read back.
    * ``invalid``: the file or its metadata row is invalid (``error``); nothing of the upload
      was saved.
    * ``not_written``: valid, but not saved because another file or the CSV is invalid.
    * ``failed``: saving stopped (``error``). The document is not in any collection and
      nobody can read it; uploading the file again creates a new document.
    * ``uncertain``: everything was saved but adding the document to the collection could
      not be confirmed; reload the collection before uploading again.
    """
    filename: str
    status: TextUploadStatus
    document_id: UUID | None = None
    """The created document (``completed``, ``failed`` and ``uncertain`` once it was created)."""
    title: str | None = None
    chunks: int = 0
    error: str | None = None


class TextUploadAvailability(BaseModel):
    """Whether this server takes text uploads (#785); ``message`` says why not, without the
    store's details (those are logged)."""
    available: bool
    message: str | None = None


class TextUploadResponse(BaseModel):
    """The result of every file of a text upload, in request order, and the problems of the
    upload as a whole (the metadata CSV, the number of files); any problem means nothing was saved."""
    files: list[TextUploadFileResult]
    errors: list[str] = []
