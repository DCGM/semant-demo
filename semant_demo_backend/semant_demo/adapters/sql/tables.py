"""All SQL tables of the application and their creation at startup.

``create_tables`` only creates tables that do not exist yet; it never drops or alters
existing tables or rows (user accounts, feedback and the LLM quota ledger are kept).
"""
from sqlalchemy.ext.asyncio import AsyncEngine

from semant_demo.adapters.sql.base import Base
from semant_demo.adapters.sql.feedback import RagUserFeedback
from semant_demo.adapters.sql.quota import QuotaCall, QuotaDay, QuotaOperation
from semant_demo.users.models import User

__all__ = ["Base", "QuotaCall", "QuotaDay", "QuotaOperation", "RagUserFeedback", "User", "create_tables"]


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
