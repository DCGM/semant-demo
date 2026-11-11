"""Request and stream events of the contextual chat routes (ADR 0012).

The response is NDJSON, one :data:`ChatEvent` per line: ``delta`` events with the answer's
text, then ``sources`` and ``end``, or an ``error`` that ends the stream. A stream without
``end`` or ``error`` was interrupted.
"""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from semant_demo.config import MAX_PASSAGES_LIMIT
from semant_demo.features.documents.criteria import SearchCriteria

MAX_HISTORY_TURNS = 40
"""Earlier turns a request may carry (20 questions and answers); older ones are left out
by the client. The server drops more of the oldest when they do not fit the input limit."""
MAX_TURN_CHARS = 20000
MAX_QUESTION_CHARS = 4000


class ChatTurn(BaseModel):
    """An earlier turn of the conversation.

    ``chunk_ids`` (assistant turns): the chunks its citations refer to, ``[docK]`` in
    ``text`` citing ``chunk_ids[K - 1]``. The server renumbers them for the current request
    and removes citations of chunks outside the scope; it never reads text from them.
    """
    role: Literal["user", "assistant"]
    text: str = Field(max_length=MAX_TURN_CHARS)
    chunk_ids: list[UUID] = Field(default_factory=list, max_length=200)


class ContextChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


class SearchChatRequest(ContextChatRequest):
    """A question about search results (#245). ``chunk_ids`` are the results the page chose
    (the selected ones, or all loaded ones), in result order; ``criteria`` and
    ``user_collection_id`` are those of the search. The server reads the passages again
    under them, so an id the search could not have returned is left out (ADR 0006)."""
    model_config = ConfigDict(extra="forbid")

    chunk_ids: list[UUID] = Field(min_length=1, max_length=MAX_PASSAGES_LIMIT)
    criteria: SearchCriteria
    user_collection_id: str | None = None


class ChatSource(BaseModel):
    """A chunk cited as ``[doc{citation}]`` in this answer."""
    citation: int
    chunk_id: UUID
    document_id: UUID
    order: int | None
    from_page: int
    to_page: int


class ChatDeltaEvent(BaseModel):
    event: Literal["delta"] = "delta"
    text: str


class ChatSourcesEvent(BaseModel):
    event: Literal["sources"] = "sources"
    sources: list[ChatSource]


class ChatEndEvent(BaseModel):
    """``coverage`` is ``part`` when only ``used_chunks`` of the scope's ``total_chunks``
    chunks fitted the input limit (the first ones, in document order)."""
    event: Literal["end"] = "end"
    coverage: Literal["all", "part"]
    used_chunks: int
    total_chunks: int


ChatErrorCode = Literal["too_large", "refused", "failed"]


class ChatErrorEvent(BaseModel):
    """An error after the stream started: ``too_large`` (the input went over the limit),
    ``refused`` (the allowance or a call limit refused a model call) or ``failed``.
    ``message`` is server-authored and safe to show."""
    event: Literal["error"] = "error"
    code: ChatErrorCode
    message: str


ChatEvent = ChatDeltaEvent | ChatSourcesEvent | ChatEndEvent | ChatErrorEvent
