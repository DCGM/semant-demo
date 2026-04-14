from fastapi import APIRouter
from .tag_routes import exp_router as tag_router
from .user_collection_routes import exp_router as usr_collection_router
from .rag_routes import exp_router as rag_router
from .feedback_routes import exp_router as feedback_router
from .summarizer_routes import exp_router as summarizer_router
from .document_routes import exp_router as documents_router
from .user_routes import exp_router as user_router

export_router = APIRouter()
export_router.include_router(user_router)
export_router.include_router(tag_router)
export_router.include_router(usr_collection_router)
export_router.include_router(rag_router)
export_router.include_router(feedback_router)
export_router.include_router(summarizer_router)
export_router.include_router(documents_router)

__all__ = ["export_router"]