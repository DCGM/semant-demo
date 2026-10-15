"""Summarization HTTP models. The summary options of a search are part of its request
(``SummaryRequestBase`` in ``features/search/schemas.py``)."""
from uuid import UUID

from pydantic import BaseModel, Field

from semant_demo.features.search.schemas import SearchResponse, SummaryRequestBase


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
    """
    document_id: UUID
    summary: str
    citations: list[DocumentSummaryCitation]
    time_spent: float
