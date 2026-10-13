"""Summarization HTTP models. The summary options of a search are part of its request
(``SummaryRequestBase`` in ``features/search/schemas.py``)."""
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
