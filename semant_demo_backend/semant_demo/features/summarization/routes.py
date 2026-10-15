"""Summarization HTTP routes; the workflows live in ``service.py``."""
from fastapi import APIRouter, Depends, HTTPException

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
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


@exp_router.post("/api/summarize/{summary_type}", response_model=SummaryResponse)
async def summarize(search_response: SearchResponse, summary_type: str,
                    summarizer: TemplatedSearchResultsSummarizer = Depends(get_summarizer),
                    current_user: User | None = Depends(current_active_optional_user)) -> SummaryResponse:
    return await service.summarize(summarizer, summary_type, search_response)


@exp_router.post(
    "/api/user_collections/{collection_id}/documents/{document_id}/summary",
    response_model=DocumentSummaryResponse,
)
async def summarize_document(collection_id: str, document_id: str,
                             documents: DocumentRepository = Depends(get_documents),
                             collections: UserCollectionRepository = Depends(get_user_collections),
                             document_summarizer: TemplatedDocumentSummarizer = Depends(get_document_summarizer),
                             current_user: User = Depends(current_active_user)) -> DocumentSummaryResponse:
    """
    Summarizes the current document of a collection (#249), with citations to the chunks the
    summary was built from. Collection-scoped (needs read access, as the matching
    ``GET /api/user_collections/{collection_id}/documents/{document_id}`` route does); the
    document must belong to the collection.
    """
    return await service.summarize_document(documents, collections, document_summarizer, current_user, document_id,
                                             collection_id)


@exp_router.post("/api/question", response_model=SummaryResponse)
async def question(request: QuestionRequest,
                   current_user: User | None = Depends(current_active_optional_user),
                   llm: LlmGateway = Depends(get_llm)) -> SummaryResponse:
    try:
        return await service.answer_question(llm, request.question_text, request.search_response)
    except service.QuestionFailed as e:
        raise HTTPException(status_code=502, detail=str(e))
