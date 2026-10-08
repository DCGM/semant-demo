from fastapi import APIRouter
from semant_demo.features.annotations.routes import span_router, tag_router
from semant_demo.features.collections.routes import exp_router as usr_collection_router
from .rag_routes import exp_router as rag_router
from .feedback_routes import exp_router as feedback_router
from .summarizer_routes import exp_router as summarizer_router
from semant_demo.features.documents.routes import exp_router as documents_router
from .user_routes import exp_router as user_router
from semant_demo.features.annotations.suggestion_routes import exp_router as ai_assistance_router
from semant_demo.features.annotations.span_chat_routes import exp_router as span_chat_router
from semant_demo.features.search.routes import exp_router as search_router

export_router = APIRouter()
export_router.include_router(user_router)
export_router.include_router(tag_router)
export_router.include_router(usr_collection_router)
export_router.include_router(rag_router)
export_router.include_router(feedback_router)
export_router.include_router(summarizer_router)
export_router.include_router(documents_router)
export_router.include_router(span_router)
export_router.include_router(ai_assistance_router)
export_router.include_router(span_chat_router)
export_router.include_router(search_router)

__all__ = ["export_router"]