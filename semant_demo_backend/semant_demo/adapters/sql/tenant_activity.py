"""When each annotation tenant was last used (#327), shared by all workers and commands.

The idle-tenant deactivation (``maintenance.annotation_tenants``) deactivates only tenants
whose ``last_used_at`` is older than its idle time, so every use of a tenant records
itself here: requests with ``touch`` (at most once per ``touch_seconds`` per tenant and
process), long operations (AI suggestion runs, maintenance) with ``in_use``, which
records the start, every ``touch_seconds`` while running, and the end. The idle time must
be much longer than ``touch_seconds``.

The record is advisory: a failed write is logged and never fails the annotation request
that made it. Rows hold only the tenant name (a collection UUID) and a time.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from typing import AsyncIterator, Callable, Iterable
from uuid import UUID

from sqlalchemy import Column, DateTime, String, delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from semant_demo.adapters.sql.base import Base

logger = logging.getLogger(__name__)


class AnnotationTenantActivity(Base):
    __tablename__ = "annotation_tenant_activity"
    tenant = Column(String(64), primary_key=True)
    last_used_at = Column(DateTime(timezone=True), nullable=False)


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; they are stored in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _upsert(session: AsyncSession, *, overwrite: bool):
    dialect = session.bind.dialect.name
    insert = {"sqlite": sqlite_insert, "postgresql": postgresql_insert}.get(dialect)
    if insert is None:
        raise RuntimeError(f"Tenant activity does not support the {dialect!r} SQL dialect")
    statement = insert(AnnotationTenantActivity)
    if overwrite:
        return lambda values: statement.values(values).on_conflict_do_update(
            index_elements=["tenant"], set_={"last_used_at": statement.excluded.last_used_at})
    return lambda values: statement.values(values).on_conflict_do_nothing()


class TenantActivity:
    def __init__(self, session_maker: async_sessionmaker, touch_seconds: float,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        if touch_seconds <= 0:
            raise ValueError("ANNOTATION_TENANT_TOUCH_SECONDS must be positive")
        self.session_maker = session_maker
        self.touch_seconds = touch_seconds
        self.now = now
        """The clock of the records (UTC); idle times are measured with it too."""
        # tenant -> time.monotonic() of this process's last recorded use
        self._recorded: dict[str, float] = {}

    async def touch(self, collection_id: UUID | str, *, force: bool = False) -> None:
        """Record a use of the collection's tenant now (skipped when this process recorded
        one less than ``touch_seconds`` ago, unless ``force``)."""
        tenant = str(UUID(str(collection_id)))
        last = self._recorded.get(tenant)
        if not force and last is not None and time.monotonic() - last < self.touch_seconds:
            return
        try:
            async with self.session_maker() as session, session.begin():
                await session.execute(_upsert(session, overwrite=True)(
                    {"tenant": tenant, "last_used_at": self.now()}))
            self._recorded[tenant] = time.monotonic()
        except Exception as e:
            logger.warning("Recording the use of annotation tenant %s failed: %s", tenant, type(e).__name__)

    @asynccontextmanager
    async def in_use(self, collection_id: UUID | str) -> AsyncIterator[None]:
        """Keep the tenant recorded as in use for the duration of a long operation."""
        await self.touch(collection_id, force=True)

        async def heartbeat():
            while True:
                await asyncio.sleep(self.touch_seconds)
                await self.touch(collection_id, force=True)

        task = asyncio.create_task(heartbeat())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await self.touch(collection_id, force=True)

    async def last_used(self, tenants: Iterable[str] | None = None) -> dict[str, datetime]:
        """``last_used_at`` of the given tenants (all when ``None``) that have a record."""
        query = select(AnnotationTenantActivity.tenant, AnnotationTenantActivity.last_used_at)
        if tenants is not None:
            query = query.where(AnnotationTenantActivity.tenant.in_(list(tenants)))
        async with self.session_maker() as session:
            return {t: _utc(at) for t, at in (await session.execute(query)).all()}

    async def record_unseen(self, tenants: Iterable[str]) -> None:
        """Give tenants without a record one with the current time, so a tenant that was
        never recorded (created before tracking, or by the migration) only becomes idle
        after a full idle time from now."""
        rows = [{"tenant": t, "last_used_at": self.now()} for t in tenants]
        if not rows:
            return
        async with self.session_maker() as session, session.begin():
            insert = _upsert(session, overwrite=False)
            for row in rows:
                await session.execute(insert(row))

    async def forget(self, tenants: Iterable[str]) -> None:
        """Drop the records of tenants that no longer exist."""
        names = list(tenants)
        if not names:
            return
        async with self.session_maker() as session, session.begin():
            await session.execute(delete(AnnotationTenantActivity).where(AnnotationTenantActivity.tenant.in_(names)))


class NoTenantActivity:
    """Records nothing (tests and tools without the application database)."""

    async def touch(self, collection_id, *, force: bool = False) -> None:
        return None

    @asynccontextmanager
    async def in_use(self, collection_id) -> AsyncIterator[None]:
        yield
