import uuid
import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from semant_demo.users.models import User
from semant_demo.routes.dependencies import get_async_session
from semant_demo.config import config

logger = logging.getLogger(__name__)


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = config.JWT_SECRET
    verification_token_secret = config.JWT_SECRET

    async def _get_by_username(self, username: str) -> Optional[User]:
        session = self.user_db.session
        result = await session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def authenticate(self, credentials) -> Optional[User]:
        """Authenticate using email or username."""
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            user = await self._get_by_username(credentials.username)
            if user is None:
                self.password_helper.hash(credentials.password)  # prevent timing attack
                return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            return None
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})
        return user

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        logger.info(f"User {user.id} registered.")

    async def on_after_forgot_password(self, user: User, token: str, request: Optional[Request] = None):
        logger.info(f"User {user.id} requested password reset.")

    async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
        logger.info(f"Verification requested for user {user.id}.")


async def get_user_manager(user_db=Depends(get_user_db)):
    yield UserManager(user_db)
