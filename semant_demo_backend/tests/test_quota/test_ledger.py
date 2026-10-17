"""Daily LLM allowance ledger (adapters/sql/quota.py) and its service on SQLite files.

Each test has its own database file; concurrency tests use separate engines (separate
SQLite connections, each running in its own aiosqlite thread) on one file.
"""
import asyncio
import datetime
import sqlite3

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from semant_demo.adapters.sql.quota import CallRecord, QuotaLedger, usd_to_micro
from semant_demo.adapters.sql.tables import create_tables
from semant_demo.config import Config
from semant_demo.features.quota import service
from semant_demo.features.quota.service import QuotaExhausted, QuotaPolicy, QuotaPrincipal

UTC = datetime.timezone.utc
NOON = datetime.datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
GUEST = QuotaPrincipal(kind="guest", id="a" * 64)
ACCOUNT = QuotaPrincipal(kind="account", id="7d0f5b5e-3c1a-4f7e-9d2b-1a2b3c4d5e6f")
POLICY = QuotaPolicy.from_config(Config(environ={}))  # $0.25 a guest, $1.00 an account


def call(cost_usd: float | None, cost_source: str = "provider") -> CallRecord:
    return CallRecord(feature="rag", tier="standard", provider="openai", model="m", outcome="success",
                      usage_source="provider", cost_source=cost_source, cost_usd=cost_usd,
                      input_tokens=100, output_tokens=10)


class Ledgers:
    """Ledgers on one database file, each with its own engine."""

    def __init__(self, path):
        self.url = f"sqlite+aiosqlite:///{path}"
        self.engines = []

    async def open(self) -> QuotaLedger:
        engine = create_async_engine(self.url, poolclass=NullPool)
        self.engines.append(engine)
        await create_tables(engine)
        return QuotaLedger(async_sessionmaker(engine, expire_on_commit=False))

    async def close(self) -> None:
        for engine in self.engines:
            await engine.dispose()


@pytest.fixture
async def ledgers(tmp_path):
    opened = Ledgers(tmp_path / "quota.db")
    yield opened
    await opened.close()


@pytest.fixture
async def ledger(ledgers):
    return await ledgers.open()


async def test_admission_reserves_and_settlement_replaces_the_reservation(ledger):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)

    assert (await service.status(ledger, POLICY, GUEST, now=NOON)).reserved_micro_usd == 50_000
    assert await service.settle(ledger, operation_id, [call(0.012), call(0.0000001)], now=NOON) == 12_001

    status = await service.status(ledger, POLICY, GUEST, now=NOON)
    assert (status.reserved_micro_usd, status.charged_micro_usd, status.remaining_micro_usd) == (0, 12_001, 237_999)


async def test_an_operation_that_does_not_fit_is_refused_without_reserving(ledger):
    await service.admit(ledger, POLICY, GUEST, "rag", 0.20, now=NOON)

    with pytest.raises(QuotaExhausted) as refused:
        await service.admit(ledger, POLICY, GUEST, "rag", 0.06, now=NOON)

    assert refused.value.status.used_micro_usd == 200_000 and not refused.value.status.exhausted
    assert str(refused.value) == ("Insufficient remaining daily AI allowance for this operation; "
                                  "it resets at 2026-10-18 00:00 UTC.")
    assert (await service.status(ledger, POLICY, GUEST, now=NOON)).used_micro_usd == 200_000
    # A smaller operation still fits, and the account's allowance is separate.
    await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)
    await service.admit(ledger, POLICY, ACCOUNT, "rag", 0.90, now=NOON)


async def test_an_admitted_operation_may_cross_the_allowance_and_later_ones_are_refused(ledger):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.10, now=NOON)
    await service.settle(ledger, operation_id, [call(0.30)], now=NOON)

    status = await service.status(ledger, POLICY, GUEST, now=NOON)
    assert (status.charged_micro_usd, status.remaining_micro_usd, status.exhausted) == (300_000, 0, True)
    with pytest.raises(QuotaExhausted):
        await service.admit(ledger, POLICY, GUEST, "question", 0, now=NOON)


async def test_a_used_up_allowance_refuses_even_a_zero_reservation(ledger):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)
    await service.settle(ledger, operation_id, [call(0.25)], now=NOON)  # used == limit exactly

    with pytest.raises(QuotaExhausted) as refused:
        await service.admit(ledger, POLICY, GUEST, "rag", 0, now=NOON)

    assert refused.value.status.exhausted
    assert (await service.status(ledger, POLICY, GUEST, now=NOON)).used_micro_usd == 250_000


@pytest.mark.parametrize("cost", [-0.01, float("inf"), float("-inf"), float("nan")])
async def test_an_invalid_call_cost_is_rejected_without_settling(ledger, cost):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)

    with pytest.raises(ValueError):
        await service.settle(ledger, operation_id, [call(0.01), call(cost)], now=NOON)

    # Nothing was written: the reservation stays, and a valid settlement still works.
    status = await service.status(ledger, POLICY, GUEST, now=NOON)
    assert (status.reserved_micro_usd, status.charged_micro_usd) == (50_000, 0)
    assert await service.settle(ledger, operation_id, [call(0.01)], now=NOON) == 10_000


@pytest.mark.parametrize("calls, charge", [
    # An unknown cost is never free: the reservation stays charged at least.
    ([call(0.01), call(None, "unknown")], 50_000),
    ([call(0.08), call(None, "unknown")], 80_000),
    # A self-hosted tier's USD-equivalent rate counts like any other cost.
    ([call(0.003, "local_rate")], 3_000),
    # An operation that made no call (e.g. it failed first) releases its reservation.
    ([], 0),
])
async def test_the_charge_of_an_operation(ledger, calls, charge):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)

    assert await service.settle(ledger, operation_id, calls, now=NOON) == charge

    status = await service.status(ledger, POLICY, GUEST, now=NOON)
    assert (status.reserved_micro_usd, status.charged_micro_usd) == (0, charge)


async def test_calls_are_recorded_without_text_and_unknown_costs_stay_null(ledger, tmp_path):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)
    await service.settle(ledger, operation_id, [call(0.01), call(None, "unknown")], now=NOON)

    with sqlite3.connect(tmp_path / "quota.db") as conn:
        rows = conn.execute("SELECT feature, model, cost_source, cost_micro_usd FROM llm_quota_call "
                            "ORDER BY id").fetchall()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_quota_call)")}
    assert rows == [("rag", "m", "provider", 10_000), ("rag", "m", "unknown", None)]
    assert not columns & {"prompt", "question", "answer", "text", "content"}


async def test_an_operation_is_settled_once(ledger):
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)
    await service.settle(ledger, operation_id, [call(0.01)], now=NOON)

    assert await service.settle(ledger, operation_id, [call(0.02)], now=NOON) is None
    assert await service.settle(ledger, "no-such-operation", [call(0.02)], now=NOON) is None
    assert (await service.status(ledger, POLICY, GUEST, now=NOON)).charged_micro_usd == 10_000


async def test_an_unsettled_operation_keeps_its_reservation_charged(ledger):
    await service.admit(ledger, POLICY, GUEST, "rag", 0.05, now=NOON)

    # No settlement arrives (a crash, a lost callback); nothing expires later that day.
    status = await service.status(ledger, POLICY, GUEST, now=NOON + datetime.timedelta(hours=11, minutes=59))
    assert (status.reserved_micro_usd, status.used_micro_usd) == (50_000, 50_000)


async def test_an_operation_finishing_after_midnight_is_booked_on_its_start_day(ledger):
    before_midnight = datetime.datetime(2026, 10, 17, 23, 59, 59, tzinfo=UTC)
    after_midnight = datetime.datetime(2026, 10, 18, 0, 0, 10, tzinfo=UTC)
    operation_id = await service.admit(ledger, POLICY, GUEST, "rag", 0.20, now=before_midnight)

    # The new day starts with the whole allowance, even while yesterday's operation runs.
    fresh = await service.status(ledger, POLICY, GUEST, now=after_midnight)
    assert (fresh.day, fresh.used_micro_usd) == ("2026-10-18", 0)
    assert fresh.reset_at == datetime.datetime(2026, 10, 19, tzinfo=UTC)

    await service.settle(ledger, operation_id, [call(0.03)], now=after_midnight)

    assert (await service.status(ledger, POLICY, GUEST, now=after_midnight)).used_micro_usd == 0
    assert (await service.status(ledger, POLICY, GUEST, now=before_midnight)).charged_micro_usd == 30_000


def test_days_and_resets_are_utc_calendar_days():
    prague_evening = datetime.datetime(2026, 10, 18, 1, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))

    assert service.utc_day(prague_evening) == "2026-10-17"
    assert service.next_reset(prague_evening) == datetime.datetime(2026, 10, 18, tzinfo=UTC)


async def test_the_ledger_survives_a_restart(ledgers):
    first = await ledgers.open()
    operation_id = await service.admit(first, POLICY, GUEST, "rag", 0.05, now=NOON)
    await service.admit(first, POLICY, GUEST, "rag", 0.02, now=NOON)
    await ledgers.close()

    restarted = await ledgers.open()
    await service.settle(restarted, operation_id, [call(0.01)], now=NOON)
    status = await service.status(restarted, POLICY, GUEST, now=NOON)
    assert (status.reserved_micro_usd, status.charged_micro_usd) == (20_000, 10_000)


async def test_racing_connections_do_not_admit_past_the_allowance(ledgers):
    workers = [await ledgers.open() for _ in range(4)]

    async def attempt(ledger):
        try:
            return await service.admit(ledger, POLICY, GUEST, "rag", 0.10, now=NOON)
        except QuotaExhausted:
            return None

    admitted = [op for op in await asyncio.gather(*(attempt(workers[i % 4]) for i in range(12))) if op]

    assert len(admitted) == 2  # 0.25 holds two reservations of 0.10
    assert (await service.status(workers[0], POLICY, GUEST, now=NOON)).reserved_micro_usd == 200_000


async def test_racing_settlements_and_admissions_keep_the_day_totals_exact(ledgers, tmp_path):
    workers = [await ledgers.open() for _ in range(4)]
    operations = [await service.admit(workers[0], POLICY, ACCOUNT, "rag", 0.01, now=NOON) for _ in range(20)]

    await asyncio.gather(
        *(service.settle(workers[i % 4], op, [call(0.004)], now=NOON) for i, op in enumerate(operations)),
        *(service.admit(workers[i % 4], POLICY, ACCOUNT, "rag", 0.01, now=NOON) for i in range(20)))

    status = await service.status(workers[0], POLICY, ACCOUNT, now=NOON)
    assert (status.reserved_micro_usd, status.charged_micro_usd) == (200_000, 80_000)
    with sqlite3.connect(tmp_path / "quota.db") as conn:
        assert conn.execute("SELECT SUM(COALESCE(charged_micro_usd, reserved_micro_usd)) "
                            "FROM llm_quota_operation").fetchone() == (280_000,)


def test_micro_usd_rounds_up():
    assert [usd_to_micro(v) for v in (0, 0.0000001, 0.25, 1.0)] == [0, 1, 250_000, 1_000_000]


@pytest.mark.parametrize("reserve", [-0.01, float("inf"), float("nan")])
async def test_an_invalid_reservation_is_rejected(ledger, reserve):
    with pytest.raises(ValueError):
        await service.admit(ledger, POLICY, GUEST, "rag", reserve, now=NOON)


async def test_the_ledger_rejects_a_negative_reservation(ledger):
    with pytest.raises(ValueError):
        await ledger.admit("guest", GUEST.id, "2026-10-17", feature="rag", reserve_micro_usd=-1,
                           limit_micro_usd=250_000, now=NOON)
