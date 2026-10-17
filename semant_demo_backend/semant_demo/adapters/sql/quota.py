"""Daily LLM allowance ledger: admitted operations, their calls and per-principal day totals.

Amounts are integer micro-USD (USD-equivalent estimates, not bills). ``llm_quota_day``
holds the totals that admission checks; it changes only together with an operation row in
one short transaction, and each change is one conditional ``UPDATE``, so racing
connections or workers cannot admit past the limit. No transaction is held while a
model runs. Rows hold no prompts, answers or secrets.
"""
import datetime
import math
from dataclasses import dataclass
from uuid import uuid4

import sqlalchemy.sql.functions as funcs
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, case, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from semant_demo.adapters.sql.base import Base

MICRO_USD = 1_000_000


def usd_to_micro(usd: float) -> int:
    """Whole micro-USD, rounded up so that a tiny positive cost is not booked as free."""
    return math.ceil(usd * MICRO_USD)


class QuotaDay(Base):
    __tablename__ = "llm_quota_day"
    principal_kind = Column(String(16), primary_key=True)
    principal_id = Column(String(64), primary_key=True)
    day = Column(String(10), primary_key=True)  # UTC calendar day, YYYY-MM-DD
    reserved_micro_usd = Column(BigInteger, nullable=False, default=0)
    """Reservations of the day's operations that are not settled (yet, or ever)."""
    charged_micro_usd = Column(BigInteger, nullable=False, default=0)


class QuotaOperation(Base):
    __tablename__ = "llm_quota_operation"
    id = Column(String(36), primary_key=True)
    principal_kind = Column(String(16), nullable=False)
    principal_id = Column(String(64), nullable=False, index=True)
    day = Column(String(10), nullable=False)  # the operation's UTC start day
    feature = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)  # pending | settled
    reserved_micro_usd = Column(BigInteger, nullable=False)
    charged_micro_usd = Column(BigInteger, nullable=True)
    unknown_cost_calls = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    settled_at = Column(DateTime(timezone=True), nullable=True)


class QuotaCall(Base):
    __tablename__ = "llm_quota_call"
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(String(36), ForeignKey("llm_quota_operation.id"), nullable=False, index=True)
    feature = Column(String(64), nullable=False)
    tier = Column(String(64), nullable=False)
    provider = Column(String(32), nullable=False)
    model = Column(String(200), nullable=False)
    outcome = Column(String(32), nullable=False)
    usage_source = Column(String(16), nullable=False)
    cost_source = Column(String(16), nullable=False)
    cost_micro_usd = Column(BigInteger, nullable=True)  # NULL: unknown, never zero
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=funcs.now())


@dataclass(frozen=True)
class CallRecord:
    """One finished model call of an operation, as the gateway measured it."""
    feature: str
    tier: str
    provider: str
    model: str
    outcome: str
    usage_source: str
    cost_source: str
    cost_usd: float | None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class DayTotals:
    reserved_micro_usd: int = 0
    charged_micro_usd: int = 0

    @property
    def used_micro_usd(self) -> int:
        return self.reserved_micro_usd + self.charged_micro_usd


@dataclass(frozen=True)
class Admission:
    admitted: bool
    totals: DayTotals
    """The day's totals after the admission (unchanged when it was refused)."""
    operation_id: str | None = None


class QuotaLedger:
    """Each method runs one short transaction of its own on ``session_maker``."""

    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker

    async def totals(self, principal_kind: str, principal_id: str, day: str) -> DayTotals:
        async with self.session_maker() as session:
            return await _totals(session, principal_kind, principal_id, day)

    async def admit(self, principal_kind: str, principal_id: str, day: str, *, feature: str,
                    reserve_micro_usd: int, limit_micro_usd: int, now: datetime.datetime) -> Admission:
        """Reserve ``reserve_micro_usd`` of the day's allowance for a new operation when the
        day's reserved and charged amounts leave room for it within ``limit_micro_usd``. An
        exhausted day admits nothing, not even a zero reservation."""
        if reserve_micro_usd < 0:
            raise ValueError("A quota reservation must not be negative")
        async with self.session_maker() as session, session.begin():
            # A write first, so SQLite takes its write lock (waiting for other writers)
            # before anything is read.
            await session.execute(_insert_ignore(session).values(
                principal_kind=principal_kind, principal_id=principal_id, day=day,
                reserved_micro_usd=0, charged_micro_usd=0))
            key = _day_key(principal_kind, principal_id, day)
            used = QuotaDay.reserved_micro_usd + QuotaDay.charged_micro_usd
            reserved = await session.execute(
                update(QuotaDay).where(*key).where(used < limit_micro_usd,
                                                   used + reserve_micro_usd <= limit_micro_usd)
                .values(reserved_micro_usd=QuotaDay.reserved_micro_usd + reserve_micro_usd))
            operation_id = None
            if reserved.rowcount == 1:
                operation_id = str(uuid4())
                session.add(QuotaOperation(
                    id=operation_id, principal_kind=principal_kind, principal_id=principal_id, day=day,
                    feature=feature, status="pending", reserved_micro_usd=reserve_micro_usd, started_at=now))
                await session.flush()
            totals = await _totals(session, principal_kind, principal_id, day)
        return Admission(admitted=operation_id is not None, totals=totals, operation_id=operation_id)

    async def settle(self, operation_id: str, calls: list[CallRecord], *, now: datetime.datetime) -> int | None:
        """Record the operation's calls and replace its reservation with their cost, on the
        operation's start day. The charge is the sum of the known call costs; when a call's
        cost is unknown it is at least the reservation, so unpriced work is never free.

        Returns the charge in micro-USD, or ``None`` when the operation is unknown or was
        already settled (nothing is written then). Raises ``ValueError`` before writing
        when a known cost is negative or not finite.
        """
        for c in calls:
            if c.cost_usd is not None and not 0 <= c.cost_usd < math.inf:
                raise ValueError(f"A call cost must be a finite non-negative amount, not {c.cost_usd!r}")
        known = sum(usd_to_micro(c.cost_usd) for c in calls if c.cost_usd is not None)
        unknown = sum(1 for c in calls if c.cost_usd is None)
        charge = known
        if unknown:
            charge = case((QuotaOperation.reserved_micro_usd > known, QuotaOperation.reserved_micro_usd), else_=known)
        async with self.session_maker() as session, session.begin():
            # The write comes first (see ``admit``); it settles a pending operation only once.
            settled = await session.execute(
                update(QuotaOperation).where(QuotaOperation.id == operation_id, QuotaOperation.status == "pending")
                .values(status="settled", charged_micro_usd=charge, unknown_cost_calls=unknown, settled_at=now))
            if settled.rowcount != 1:
                return None
            operation = (await session.execute(
                select(QuotaOperation).where(QuotaOperation.id == operation_id))).scalar_one()
            charge = operation.charged_micro_usd
            await session.execute(
                update(QuotaDay).where(*_day_key(operation.principal_kind, operation.principal_id, operation.day))
                .values(reserved_micro_usd=QuotaDay.reserved_micro_usd - operation.reserved_micro_usd,
                        charged_micro_usd=QuotaDay.charged_micro_usd + charge))
            session.add_all(QuotaCall(
                operation_id=operation_id, feature=c.feature, tier=c.tier, provider=c.provider, model=c.model,
                outcome=c.outcome, usage_source=c.usage_source, cost_source=c.cost_source,
                cost_micro_usd=None if c.cost_usd is None else usd_to_micro(c.cost_usd),
                input_tokens=c.input_tokens, output_tokens=c.output_tokens) for c in calls)
        return charge


def _day_key(principal_kind: str, principal_id: str, day: str) -> tuple:
    return QuotaDay.principal_kind == principal_kind, QuotaDay.principal_id == principal_id, QuotaDay.day == day


def _insert_ignore(session: AsyncSession):
    dialect = session.bind.dialect.name
    insert = {"sqlite": sqlite_insert, "postgresql": postgresql_insert}.get(dialect)
    if insert is None:
        raise RuntimeError(f"The LLM quota ledger does not support the {dialect!r} SQL dialect")
    return insert(QuotaDay).on_conflict_do_nothing()


async def _totals(session: AsyncSession, principal_kind: str, principal_id: str, day: str) -> DayTotals:
    row = (await session.execute(select(QuotaDay.reserved_micro_usd, QuotaDay.charged_micro_usd)
                                 .where(*_day_key(principal_kind, principal_id, day)))).one_or_none()
    return DayTotals() if row is None else DayTotals(reserved_micro_usd=row[0], charged_micro_usd=row[1])
