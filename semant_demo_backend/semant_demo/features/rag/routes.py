"""RAG HTTP routes; the workflows live in ``service.py``."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.features.rag import service
from semant_demo.features.rag.registry import RagRegistry
from semant_demo.features.rag.schemas import ExplainRequest, FeedbackRequest, RagRequestMain, RagResponse, RagRouteConfig
from semant_demo.features.search.service import SearchBackends
from semant_demo.routes.dependencies import get_async_session, get_rag_registry, get_search_backends
from semant_demo.users.auth import current_active_optional_user
from semant_demo.users.models import User

logger = logging.getLogger(__name__)

exp_router = APIRouter()


@exp_router.get("/api/rag/configurations", response_model=list[RagRouteConfig])
async def get_avalaible_rag_configurations(current_user: User | None = Depends(current_active_optional_user),
                                           rag_registry: RagRegistry = Depends(get_rag_registry)):
    return service.configurations(rag_registry)


@exp_router.post("/api/rag", response_model=RagResponse)
async def rag(request: RagRequestMain, search_backends: SearchBackends = Depends(get_search_backends),
              current_user: User | None = Depends(current_active_optional_user),
              rag_registry: RagRegistry = Depends(get_rag_registry)) -> RagResponse:
    return await service.answer(rag_registry, search_backends, request)


@exp_router.post("/api/rag/explain")
async def explain_selection(request: ExplainRequest,
                            current_user: User | None = Depends(current_active_optional_user),
                            rag_registry: RagRegistry = Depends(get_rag_registry)):
    return await service.explain(rag_registry, request)


# endpoint of feedback - like/dislike
@exp_router.post("/api/rag/feedback")
async def save_feedback(request: FeedbackRequest, db: AsyncSession = Depends(get_async_session),
                        current_user: User | None = Depends(current_active_optional_user)):
    try:
        await service.save_feedback(db, request)
    except Exception as e:
        # Content-free: database errors quote the statement parameters (question, answer).
        logger.error("RAG feedback was not saved: %s", type(e).__name__)
        raise HTTPException(status_code=500, detail="Database error.")
    return {"status": "success"}
