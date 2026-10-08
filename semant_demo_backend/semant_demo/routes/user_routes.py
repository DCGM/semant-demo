from fastapi import APIRouter, Depends, Query

from semant_demo.adapters.sql.users import UserLookup
from semant_demo.routes.dependencies import get_user_lookup
from semant_demo.users.auth import current_active_user
from semant_demo.users.models import User
from semant_demo.users.schemas import UserSearchResult

exp_router = APIRouter()


@exp_router.get("/api/users/search", response_model=list[UserSearchResult])
async def search_users(
    q: str = Query(..., min_length=3, description="Username substring to search (min 3 characters)"),
    users: UserLookup = Depends(get_user_lookup),
    current_user: User = Depends(current_active_user),
) -> list[UserSearchResult]:
    """
    Search users by username substring. Returns at most 4 matches.
    Requires authentication.
    """
    return await users.search_by_username(q, limit=4)
