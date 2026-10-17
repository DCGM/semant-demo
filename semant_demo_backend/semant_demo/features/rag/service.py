"""RAG use cases: the configured pipelines answer and explain over the public corpus, and
users rate the answers.

Pipelines are loaded at startup into a :class:`RagRegistry` (``registry.py``); their model
calls go through the LLM gateway. One answer or explanation is one LLM operation, admitted
against the caller's daily allowance (``budget``) before the pipeline runs, whose model
calls the ``rag`` feature's ``max_calls`` caps. Logs carry the configuration id,
never questions, answers or retrieved text.
"""
import logging
from contextlib import nullcontext

from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.adapters.llm.usage import OperationBudget
from semant_demo.adapters.sql import feedback as feedback_store
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.rag.registry import BaseRag, RagRegistry
from semant_demo.features.rag.schemas import (
    ExplainRequest, FeedbackRequest, RagChatMessage, RagRequestMain, RagResponse, RagRouteConfig,
)
from semant_demo.features.search import service as search_service
from semant_demo.features.search.service import SearchBackends

logger = logging.getLogger(__name__)


def configurations(registry: RagRegistry) -> list[RagRouteConfig]:
    return registry.get_all_configurations()


def _pipeline(registry: RagRegistry, rag_id: str, purpose: str = "") -> BaseRag:
    if rag_id not in registry.instances:
        raise InvalidRequestError(f"Unknown RAG configuration: {rag_id}{purpose}.")
    return registry.instances[rag_id]


def _operation(pipeline: BaseRag, budget: OperationBudget | None):
    return pipeline.llm.operation("rag", budget) if pipeline.llm is not None else nullcontext()


def _recent(history: list[RagChatMessage] | None, limit: int) -> list[RagChatMessage] | None:
    """The last ``limit`` messages of ``history``; the earlier turns are not sent to the model."""
    return history[-max(1, limit):] if history else history


async def answer(registry: RagRegistry, backends: SearchBackends, request: RagRequestMain,
                 history_limit: int = 20, budget: OperationBudget | None = None) -> RagResponse:
    """The answer of the chosen configuration, with its sources.

    RAG requests carry no collection or tags: retrieval covers the public corpus. Every
    retrieval uses the requested search vector (default: the configured default), the
    same way a direct search does; an unknown vector is refused before the pipeline runs.
    Only the last ``history_limit`` history messages reach the pipeline. A refusal of
    ``budget`` (``QuotaExhausted``) propagates before any retrieval or model call.
    """
    pipeline = _pipeline(registry, request.rag_id)
    vector = backends.vectors.resolve(request.vector)
    rag_request = request.rag_request.model_copy(
        update={"history": _recent(request.rag_request.history, history_limit)})
    logger.info("RAG request", extra={"rag.id": request.rag_id, "rag.vector": vector.id,
                                      "rag.history_messages": len(request.rag_request.history or [])})
    async with _operation(pipeline, budget):
        return await pipeline.rag_request(request=rag_request,
                                          retrieve=search_service.public_retriever(backends, vector.id))


async def explain(registry: RagRegistry, request: ExplainRequest, history_limit: int = 20,
                  budget: OperationBudget | None = None):
    """An explanation of a selected part of an answer, by the configuration that gave it.

    Only the last ``history_limit`` history messages reach the pipeline; ``budget`` as in
    :func:`answer`.
    """
    pipeline = _pipeline(registry, request.rag_id, " used for explaining")
    logger.info("RAG explain request", extra={"rag.id": request.rag_id})
    async with _operation(pipeline, budget):
        return await pipeline.explain_selection(
            request=request.model_copy(update={"history": _recent(request.history, history_limit)}))


async def save_feedback(session: AsyncSession, request: FeedbackRequest) -> None:
    """Store a like/dislike of an answer; rating the same response again replaces it."""
    await feedback_store.save_rag_feedback(
        session, response_id=request.response_id, rag_id=request.rag_id, question=request.question,
        answer=request.answer, rating=request.rating,
        error_types=",".join(request.error_types) if request.rating == -1 else None,
        comment=request.comment,
        sources=[doc.model_dump(mode="json") for doc in request.sources] if request.sources else [])
