"""Summarization HTTP models. The summary options of a search are part of its request
(``SummaryRequestBase`` in ``features/search/schemas.py``)."""
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from semant_demo.features.search.schemas import SearchResponse, SummaryRequestBase


class SummaryLength(str, Enum):
    """Length level of a generated summary (#360). What each level means (the target number
    of words given to the prompt and the token limit) is set in the summarizer configuration."""
    short = "short"
    detailed = "detailed"


class SummaryRequest(SummaryRequestBase):
    search_response: SearchResponse


class QuestionRequest(BaseModel):
    """A question answered from the snippets of ``search_response``. The question travels in
    the body, not the URL, so proxies and access logs never see it (#304)."""
    question_text: str = Field(min_length=1)
    search_response: SearchResponse


class SummaryResponse(BaseModel):
    summary: str
    time_spent: float


class DocumentSummaryCitation(BaseModel):
    """A chunk the document summary cites as ``[docN]``, N being this citation's 1-based
    position in :attr:`DocumentSummaryResponse.citations`."""
    chunk_id: UUID
    order: int | None = None
    from_page: int
    to_page: int


class DocumentSummaryResponse(BaseModel):
    """
    A summary of one document (#249). Self-contained (text, citations and the document id)
    rather than nested inside a search-specific type, so it stays reusable as Document Chat
    context once #243 defines a shared transcript, without a second incompatible summary shape.

    ``summarized_chunks``/``total_chunks``/``truncated`` (#358 review) let the client show a
    "partial summary" notice rather than silently presenting a summary of only the first
    ``chunk_limit`` chunks of a long document as if it covered the whole thing.
    """
    document_id: UUID
    summary: str
    citations: list[DocumentSummaryCitation]
    time_spent: float
    total_chunks: int
    """Total chunks in the document, before truncation to the configured ``chunk_limit``."""
    summarized_chunks: int
    """Chunks actually sent to the model (``len(citations)``, kept separately for clarity)."""
    truncated: bool
    """Whether ``total_chunks`` exceeded ``chunk_limit``, so the summary covers only the
    document's first ``summarized_chunks`` chunks rather than all of it."""
