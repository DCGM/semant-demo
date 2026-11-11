"""Contextual chat routes (ADR 0012); the workflow lives in ``service.py``.

``POST /api/user_collections/{collection_id}/documents/{document_id}/chat`` streams an
answer about a document of the collection, ``POST /api/search/chat`` one about search
results, as NDJSON (``schemas.ChatEvent``). Access is
checked and the input fitted before the stream starts, then the answer is admitted as
one AI operation against the caller's daily allowance: a denial is 401/404, an input that
cannot fit 413 and a refusal 429, all before the stream. The operation is settled when the
stream ends, also when the client disconnects during it; a client that leaves before the
stream starts leaves the reservation charged (#563).
"""
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.llm.usage import LlmInputTooLarge
from semant_demo.adapters.weaviate.criteria import UnavailableFilter
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.features.chat import service
from semant_demo.features.chat.schemas import ChatEvent, ContextChatRequest, SearchChatRequest
from semant_demo.features.quota.principal import get_allowance_budget
from semant_demo.features.quota.schemas import QUOTA_EXHAUSTED_RESPONSES
from semant_demo.features.quota.service import AllowanceBudget
from semant_demo.features.search.schemas import SearchFiltersResponse
from semant_demo.features.search.service import SearchBackends
from semant_demo.routes.dependencies import get_documents, get_llm, get_search_backends, get_search_filters, \
    get_user_collections
from semant_demo.users.auth import current_active_optional_user, current_active_user
from semant_demo.users.models import User

exp_router = APIRouter()

_NDJSON_MEDIA_TYPE = "application/x-ndjson"


async def _ndjson(events: AsyncIterator[ChatEvent]) -> AsyncIterator[bytes]:
    async for event in events:
        yield (event.model_dump_json() + "\n").encode("utf-8")


@exp_router.post(
    "/api/user_collections/{collection_id}/documents/{document_id}/chat",
    response_class=StreamingResponse,
    responses={**QUOTA_EXHAUSTED_RESPONSES, 413: {"description": "The question and the document's first passage "
                                                                 "do not fit the input limit."}},
)
async def chat_about_document(collection_id: str, document_id: str, body: ContextChatRequest,
                              documents: DocumentRepository = Depends(get_documents),
                              collections: UserCollectionRepository = Depends(get_user_collections),
                              llm: LlmGateway = Depends(get_llm),
                              current_user: User = Depends(current_active_user),
                              budget: AllowanceBudget = Depends(get_allowance_budget)):
    """
    Streams an answer to ``question`` about the document, from its chunks in the collection
    only (#248). The client sends the earlier turns (``history``) and never source text.
    """
    try:
        chat = await service.prepare_document_chat(documents, collections, llm, current_user, collection_id,
                                                   document_id, body)
    except LlmInputTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    operation = llm.operation(service.FEATURE, budget)
    await operation.admit()
    return StreamingResponse(_ndjson(chat.events(llm, operation)), media_type=_NDJSON_MEDIA_TYPE)


@exp_router.post(
    "/api/search/chat",
    response_class=StreamingResponse,
    responses={**QUOTA_EXHAUSTED_RESPONSES,
               404: {"description": "None of the search results can be read any more."},
               413: {"description": "The question and the first search result do not fit the input limit."}},
)
async def chat_about_search_results(body: SearchChatRequest,
                                    backends: SearchBackends = Depends(get_search_backends),
                                    available_filters: SearchFiltersResponse = Depends(get_search_filters),
                                    llm: LlmGateway = Depends(get_llm),
                                    current_user: User | None = Depends(current_active_optional_user),
                                    budget: AllowanceBudget = Depends(get_allowance_budget)):
    """
    Streams an answer to ``question`` about the search results ``chunk_ids`` only (#245):
    they are read again under the search's ``criteria`` and collection, and those the search
    could not have returned are left out. Signed-out users may ask about public results
    under the daily AI allowance. The client sends the earlier turns and never source text.
    """
    try:
        chat = await service.prepare_search_chat(backends, llm, current_user, body, available_filters)
    except UnavailableFilter as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except LlmInputTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    operation = llm.operation(service.FEATURE, budget)
    await operation.admit()
    return StreamingResponse(_ndjson(chat.events(llm, operation)), media_type=_NDJSON_MEDIA_TYPE)
