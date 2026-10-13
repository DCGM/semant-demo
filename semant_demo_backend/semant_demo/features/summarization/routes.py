"""Summarization HTTP routes; the workflows live in ``service.py``."""
from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.features.search.schemas import SearchResponse
from semant_demo.features.summarization import service
from semant_demo.features.summarization.schemas import QuestionRequest, SummaryResponse
from semant_demo.features.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.routes.dependencies import get_llm, get_summarizer
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.post("/api/summarize/{summary_type}", response_model=SummaryResponse)
async def summarize(search_response: SearchResponse, summary_type: str,
                    summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                    current_user: User | None = Depends(current_active_optional_user)) -> SummaryResponse:
    return await service.summarize(summarizer, summary_type, search_response)


@exp_router.post("/api/question", response_model=SummaryResponse)
async def question(request: QuestionRequest,
                   current_user: User | None = Depends(current_active_optional_user),
                   llm: LlmGateway = Depends(get_llm)) -> SummaryResponse:
    try:
        return await service.answer_question(llm, request.question_text, request.search_response)
    except service.QuestionFailed as e:
        raise HTTPException(status_code=502, detail=str(e))
