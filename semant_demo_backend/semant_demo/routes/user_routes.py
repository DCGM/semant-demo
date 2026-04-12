import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.routes.dependencies import get_async_session
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.users.schemas import UserSearchResult

logging.basicConfig(level=logging.INFO)

exp_router = APIRouter()


@exp_router.get("/api/users/search", response_model=list[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=3, description="Username substring to search (min 3 characters)"),
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user),
) -> list[UserSearchResult]:
    """
    Search users by username substring. Returns at most 4 matches.
    Requires authentication.
    """
    result = await session.execute(
        select(User)
        .where(func.lower(User.username).like(f"%{q.lower()}%"))
        .limit(4)
    )
    return result.scalars().all()
