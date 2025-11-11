from fastapi import APIRouter
from .tag_routes import exp_router as tag_router
from .user_collection_routes import exp_router as usr_collection_router

export_router = APIRouter()
export_router.include_router(tag_router)
export_router.include_router(usr_collection_router)

__all__ = ["export_router"]