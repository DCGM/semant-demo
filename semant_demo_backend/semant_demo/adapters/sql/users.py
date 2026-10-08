"""User lookups in the SQL user database."""
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.users.models import User
from semant_demo.users.schemas import UserSearchResult


class UserLookup:
    """Reads users through one request's SQL session; returns ``UserSearchResult``, not ORM objects."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user(self, user_id: UUID) -> UserSearchResult | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return UserSearchResult.model_validate(user) if user is not None else None

    async def get_users(self, user_ids: Iterable[UUID]) -> list[UserSearchResult]:
        """Existing users among ``user_ids``; unknown ids are left out."""
        ids = list(user_ids)
        if not ids:
            return []
        result = await self.session.execute(select(User).where(User.id.in_(ids)))
        return [UserSearchResult.model_validate(user) for user in result.scalars().all()]
