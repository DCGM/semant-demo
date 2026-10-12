"""Summarization HTTP models. The summary options of a search are part of its request
(``SummaryRequestBase`` in ``features/search/schemas.py``)."""
from pydantic import BaseModel

from semant_demo.features.search.schemas import SearchResponse, SummaryRequestBase


class SummaryRequest(SummaryRequestBase):
    search_response: SearchResponse


class SummaryResponse(BaseModel):
    summary: str
    time_spent: float
