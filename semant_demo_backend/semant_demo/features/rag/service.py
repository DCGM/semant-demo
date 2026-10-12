"""RAG use cases: the configured pipelines answer and explain over the public corpus, and
users rate the answers.

Pipelines are loaded at startup into a :class:`RagRegistry` (``registry.py``); their model
calls go through the LLM gateway. Logs carry the configuration id, never questions,
answers or retrieved text.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.adapters.sql import feedback as feedback_store
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.rag.registry import BaseRag, RagRegistry
from semant_demo.features.rag.schemas import ExplainRequest, FeedbackRequest, RagRequestMain, RagResponse, RagRouteConfig
from semant_demo.features.search import service as search_service
from semant_demo.features.search.service import SearchBackends

logger = logging.getLogger(__name__)


def configurations(registry: RagRegistry) -> list[RagRouteConfig]:
    return registry.get_all_configurations()


def _pipeline(registry: RagRegistry, rag_id: str, purpose: str = "") -> BaseRag:
    if rag_id not in registry.instances:
        raise InvalidRequestError(f"Unknown RAG configuration: {rag_id}{purpose}.")
    return registry.instances[rag_id]


async def answer(registry: RagRegistry, backends: SearchBackends, request: RagRequestMain) -> RagResponse:
    """The answer of the chosen configuration, with its sources.

    RAG requests carry no collection or tags: retrieval covers the public corpus.
    """
    pipeline = _pipeline(registry, request.rag_id)
    logger.info("RAG request", extra={"rag.id": request.rag_id,
                                      "rag.history_messages": len(request.rag_request.history or [])})
    return await pipeline.rag_request(request=request.rag_request,
                                      retrieve=search_service.public_retriever(backends))


async def explain(registry: RagRegistry, request: ExplainRequest):
    """An explanation of a selected part of an answer, by the configuration that gave it."""
    pipeline = _pipeline(registry, request.rag_id, " used for explaining")
    logger.info("RAG explain request", extra={"rag.id": request.rag_id})
    return await pipeline.explain_selection(request=request)


async def save_feedback(session: AsyncSession, request: FeedbackRequest) -> None:
    """Store a like/dislike of an answer; rating the same response again replaces it."""
    await feedback_store.save_rag_feedback(
        session, response_id=request.response_id, rag_id=request.rag_id, question=request.question,
        answer=request.answer, rating=request.rating,
        error_types=",".join(request.error_types) if request.rating == -1 else None,
        comment=request.comment,
        sources=[doc.model_dump(mode="json") for doc in request.sources] if request.sources else [])
