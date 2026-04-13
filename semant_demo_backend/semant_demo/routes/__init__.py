from fastapi import APIRouter
from .tag_routes import exp_router as tag_router
from .user_collection_routes import exp_router as usr_collection_router
from .rag_routes import exp_router as rag_router
from .feedback_routes import exp_router as feedback_router
from .summarizer_routes import exp_router as summarizer_router
from .collections_routes import router as collections_router
from .documents_routes import router as documents_router
from .tags_routes import router as tags_router
from .span_routes import exp_router as span_router

export_router = APIRouter()
export_router.include_router(tag_router)
export_router.include_router(usr_collection_router)
export_router.include_router(rag_router)
export_router.include_router(feedback_router)
export_router.include_router(summarizer_router)
export_router.include_router(collections_router)
export_router.include_router(documents_router)
export_router.include_router(tags_router)
export_router.include_router(span_router)

__all__ = ["export_router"]