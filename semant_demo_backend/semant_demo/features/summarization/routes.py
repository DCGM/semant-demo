"""Summarization HTTP routes; the workflows live in ``service.py``."""
from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.features.quota.principal import get_allowance_budget
from semant_demo.features.quota.schemas import QUOTA_EXHAUSTED_RESPONSES
from semant_demo.features.quota.service import AllowanceBudget
from semant_demo.features.search.schemas import SearchResponse
from semant_demo.features.summarization import service
from semant_demo.features.summarization.document import TemplatedDocumentSummarizer
from semant_demo.features.summarization.schemas import DocumentSummaryResponse, QuestionRequest, SummaryResponse
from semant_demo.features.summarization.templated import TemplatedSearchResultsSummarizer
from semant_demo.routes.dependencies import get_document_summarizer, get_documents, get_llm, get_summarizer, \
    get_user_collections
from semant_demo.users.auth import current_active_optional_user, current_active_user
from semant_demo.users.models import User

exp_router = APIRouter()


@exp_router.post("/api/summarize/{summary_type}", response_model=SummaryResponse,
                 responses=QUOTA_EXHAUSTED_RESPONSES)
async def summarize(search_response: SearchResponse, summary_type: str,
                    summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                    current_user: User | None = Depends(current_active_optional_user),
                    budget: AllowanceBudget = Depends(get_allowance_budget)) -> SummaryResponse:
    return await service.summarize(summarizer, summary_type, search_response, budget)


@exp_router.post(
    "/api/user_collections/{collection_id}/documents/{document_id}/summary",
    response_model=DocumentSummaryResponse,
    responses=QUOTA_EXHAUSTED_RESPONSES,
)
async def summarize_document(collection_id: str, document_id: str,
                             documents: DocumentRepository = Depends(get_documents),
                             collections: UserCollectionRepository = Depends(get_user_collections),
                             document_summarizer: TemplatedDocumentSummarizer = Depends(get_document_summarizer),
                             current_user: User = Depends(current_active_user),
                             budget: AllowanceBudget = Depends(get_allowance_budget)) -> DocumentSummaryResponse:
    """
    Summarizes the current document of a collection (#249), with citations to the chunks the
    summary was built from. Collection-scoped (needs read access, as the matching
    ``GET /api/user_collections/{collection_id}/documents/{document_id}`` route does); the
    document must belong to the collection. A generation failure answers 502 (413 for an
    input above the feature's limit), the same convention ``POST /api/question`` uses,
    rather than a 200 whose ``summary`` is quietly the configured fallback text.
    """
    try:
        return await service.summarize_document(documents, collections, document_summarizer, current_user,
                                                 document_id, collection_id, budget)
    except service.DocumentSummaryFailed as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@exp_router.post("/api/question", response_model=SummaryResponse, responses=QUOTA_EXHAUSTED_RESPONSES)
async def question(request: QuestionRequest,
                   current_user: User | None = Depends(current_active_optional_user),
                   llm: LlmGateway = Depends(get_llm),
                   budget: AllowanceBudget = Depends(get_allowance_budget)) -> SummaryResponse:
    try:
        return await service.answer_question(llm, request.question_text, request.search_response, budget)
    except service.QuestionFailed as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
