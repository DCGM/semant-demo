"""User lookups in the SQL user database."""
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.users.models import User


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_users(session: AsyncSession, user_ids: Iterable[UUID]) -> list[User]:
    """Existing users among ``user_ids``; unknown ids are left out."""
    ids = list(user_ids)
    if not ids:
        return []
    result = await session.execute(select(User).where(User.id.in_(ids)))
    return list(result.scalars().all())
