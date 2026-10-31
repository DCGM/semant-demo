"""All SQL tables of the application and their creation at startup.

``create_tables`` only creates tables that do not exist yet; it never drops or alters
existing tables or rows (user accounts, feedback, the LLM quota ledger, the annotation
tenant activity and the collection attributes of #331 are kept). A column added to an
existing table therefore needs an explicit step before the backend starts: startup refuses a
database that lacks one (``annotation_attribute.all_tags``, #522) instead of failing on
every attribute request.
"""
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from semant_demo.adapters.sql.base import Base
from semant_demo.adapters.sql.attributes import AttributeChangeRow, AttributeRow, AttributeValueRow
from semant_demo.adapters.sql.feedback import RagUserFeedback
from semant_demo.adapters.sql.quota import QuotaCall, QuotaDay, QuotaOperation
from semant_demo.adapters.sql.tenant_activity import AnnotationTenantActivity
from semant_demo.users.models import User

__all__ = ["AnnotationTenantActivity", "AttributeChangeRow", "AttributeRow", "AttributeValueRow", "Base",
           "QuotaCall", "QuotaDay", "QuotaOperation", "RagUserFeedback", "User", "create_tables"]


class OutdatedSchemaError(RuntimeError):
    """An existing table lacks a column the application needs."""


def _check_columns(conn) -> None:
    columns = {c["name"] for c in inspect(conn).get_columns(AttributeRow.__tablename__)}
    if "all_tags" not in columns:
        raise OutdatedSchemaError(
            "annotation_attribute has no all_tags column; stop the backend and run "
            "`python -m semant_demo.maintenance.attribute_scope_schema` against this database (#522)")


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_check_columns)
