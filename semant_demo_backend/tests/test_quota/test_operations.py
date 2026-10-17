"""LLM operations admitted against the daily allowance (#398): ``LlmGateway.operation`` with
an ``AllowanceBudget`` on a SQLite ledger and the fake HTTP providers.

A refused operation sends nothing; an admitted one runs to its end and settles all its
calls, also when it fails, is cancelled, lacks usage or crosses the allowance; later
operations, and concurrent ones against pending reservations, are refused.
"""
import asyncio
import datetime
import sqlite3

import pytest

from semant_demo.adapters.sql.quota import DayTotals, usd_to_micro
from semant_demo.features.quota import service
from semant_demo.features.quota.service import AllowanceBudget, QuotaExhausted, QuotaPolicy
from tests.test_llm.test_gateway import CATALOG, CountingTransport, gateway, messages, transport  # noqa: F401
from tests.test_quota.test_ledger import ACCOUNT, GUEST, NOON, UTC, call, ledger, ledgers  # noqa: F401


def policy(guest_usd: float = 0.25) -> QuotaPolicy:
    return QuotaPolicy(guest_daily_micro_usd=round(guest_usd * 1e6), account_daily_micro_usd=1_000_000,
                       near_limit_ratio=0.8, guest_cookie_max_age_seconds=60, guest_cookie_secure=False)


def catalog(reserve_usd: float = 0.01, max_calls: int = 5) -> dict:
    features = {**CATALOG["features"],
                "chat": {"default": "medium", "allowed": ["small", "medium"],
                         "limits": {"max_calls": max_calls, "reserve_usd": reserve_usd}}}
    return {**CATALOG, "features": features}


def budget(ledger, guest_usd: float = 0.25, principal=GUEST, clock=lambda: NOON) -> AllowanceBudget:
    return AllowanceBudget(ledger, policy(guest_usd), principal, clock)


async def totals(ledger, principal=GUEST, day="2026-10-17"):
    return await ledger.totals(principal.kind, principal.id, day)


async def spend_all(ledger, now=NOON) -> None:
    operation = await service.admit(ledger, policy(), GUEST, "chat", 0, now=now)
    await service.settle(ledger, operation, [call(0.25)], now=now)


def rows(db, sql: str) -> list[tuple]:
    with sqlite3.connect(db) as connection:
        return connection.execute(sql).fetchall()


async def test_a_refused_operation_sends_no_request(transport, ledger):
    await spend_all(ledger)
    llm = gateway(transport, catalog=catalog())

    with pytest.raises(QuotaExhausted):
        async with llm.operation("chat", budget(ledger)):
            await llm.complete("chat", messages())

    assert transport.paths == []


async def test_the_calls_of_one_operation_are_settled_together(transport, ledger, tmp_path):
    llm = gateway(transport, catalog=catalog())

    async with llm.operation("chat", budget(ledger)) as operation:
        await llm.complete("chat", messages())
        await llm.chat_model("chat").ainvoke("Krátce.")
        # Reserved while the operation runs, not charged yet.
        assert (await totals(ledger)).reserved_micro_usd == 10_000

    day = await totals(ledger)
    assert len(transport.paths) == 2 and day.reserved_micro_usd == 0
    assert day.charged_micro_usd == sum(usd_to_micro(c.cost_usd) for c in operation.calls) > 0
    assert rows(tmp_path / "quota.db", "SELECT outcome, usage_source, cost_source FROM llm_quota_call") \
        == [("success", "provider", "price")] * 2
    assert rows(tmp_path / "quota.db", "SELECT feature, status FROM llm_quota_operation") == [("chat", "settled")]


async def test_an_admitted_operation_finishes_past_the_allowance_and_later_ones_are_refused(transport, ledger):
    # Each call costs more than the whole allowance; the reservation fits.
    llm = gateway(transport, catalog=catalog(reserve_usd=0.00001))
    allowance = budget(ledger, guest_usd=0.00002)

    async with llm.operation("chat", allowance):
        for _ in range(3):
            await llm.complete("chat", messages())

    assert len(transport.paths) == 3
    status = await service.status(ledger, allowance.policy, GUEST, now=NOON)
    assert status.charged_micro_usd > status.limit_micro_usd and status.exhausted
    with pytest.raises(QuotaExhausted):
        async with llm.operation("chat", allowance):
            await llm.complete("chat", messages())
    assert len(transport.paths) == 3


async def test_concurrent_operations_are_admitted_against_pending_reservations(transport, ledger):
    llm = gateway(transport, catalog=catalog(reserve_usd=0.15))
    allowance = budget(ledger)  # $0.25: room for one $0.15 reservation, not two
    started = asyncio.Event()
    release = asyncio.Event()

    async def first():
        async with llm.operation("chat", allowance):
            started.set()
            await release.wait()
            return await llm.complete("chat", messages())

    async def second():
        await started.wait()
        try:
            async with llm.operation("chat", allowance):
                return await llm.complete("chat", messages())
        finally:
            release.set()

    results = await asyncio.gather(first(), second(), return_exceptions=True)

    assert isinstance(results[0], str) and isinstance(results[1], QuotaExhausted)
    assert len(transport.paths) == 1
    # Settled: the reservation was replaced by the call's cost, so there is room again.
    async with llm.operation("chat", allowance):
        await llm.complete("chat", messages())
    assert len(transport.paths) == 2


async def test_a_failed_call_is_settled_with_its_estimated_cost(transport, ledger, tmp_path):
    llm = gateway(transport, catalog=catalog(), openai_base_url="http://fake/unfaked/v1")

    with pytest.raises(Exception):
        async with llm.operation("chat", budget(ledger)):
            await llm.complete("chat", messages())

    day = await totals(ledger)
    assert day.reserved_micro_usd == 0 and day.charged_micro_usd > 0
    assert rows(tmp_path / "quota.db", "SELECT outcome, usage_source, cost_source FROM llm_quota_call") \
        == [("error", "estimated", "price")]


async def test_a_call_without_usage_or_price_is_charged_the_reservation(transport, ledger, tmp_path):
    llm = gateway(transport, catalog=catalog(reserve_usd=0.02))

    async with llm.operation("chat", budget(ledger)):
        # The small tier's fake model reports no usage, and the tier has no prices.
        await llm.complete("chat", messages(), tier="small")

    assert (await totals(ledger)).charged_micro_usd == 20_000
    assert rows(tmp_path / "quota.db", "SELECT usage_source, cost_source, cost_micro_usd FROM llm_quota_call") \
        == [("estimated", "unknown", None)]
    assert rows(tmp_path / "quota.db", "SELECT unknown_cost_calls FROM llm_quota_operation") == [(1,)]


async def test_an_abandoned_stream_is_settled_with_its_partial_estimate(transport, ledger, tmp_path):
    llm = gateway(transport, catalog=catalog())

    async with llm.operation("chat", budget(ledger)):
        stream = llm.stream("chat", messages())
        await anext(stream)
        await stream.aclose()

    assert (await totals(ledger)).charged_micro_usd > 0
    assert rows(tmp_path / "quota.db", "SELECT outcome, usage_source, cost_source FROM llm_quota_call") \
        == [("cancelled", "estimated", "price")]


class HangingTransport(CountingTransport):
    """Records the request, then never answers."""

    async def handle_async_request(self, request):
        self.paths.append(request.url.path)
        await asyncio.Event().wait()


async def test_a_cancelled_operation_is_still_settled(ledger, tmp_path):
    hanging = HangingTransport(None)
    llm = gateway(hanging, catalog=catalog(reserve_usd=0.03))

    async def ask():
        async with llm.operation("chat", budget(ledger)):
            await llm.complete("chat", messages())

    task = asyncio.create_task(ask())
    while not hanging.paths:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await llm.wait_for_settlements()

    # The cancelled call never finished (LangChain reports no end for it): its cost is
    # unknown, so the operation is charged its reservation.
    assert await totals(ledger) == DayTotals(reserved_micro_usd=0, charged_micro_usd=30_000)
    assert rows(tmp_path / "quota.db", "SELECT status FROM llm_quota_operation") == [("settled",)]
    assert rows(tmp_path / "quota.db", "SELECT outcome, cost_source, cost_micro_usd FROM llm_quota_call") \
        == [("unfinished", "unknown", None)]


class SlowSettlement(AllowanceBudget):
    async def settle(self, admission, operation):
        await asyncio.sleep(0.05)
        await super().settle(admission, operation)


async def test_cancelling_a_request_during_its_settlement_does_not_lose_it(transport, ledger):
    llm = gateway(transport, catalog=catalog())
    allowance = SlowSettlement(ledger, policy(), GUEST, lambda: NOON)
    answered = asyncio.Event()

    async def ask():
        async with llm.operation("chat", allowance):
            await llm.complete("chat", messages())
            answered.set()

    task = asyncio.create_task(ask())
    await answered.wait()
    await asyncio.sleep(0.01)  # in the settlement now
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await totals(ledger)).reserved_micro_usd == 10_000

    await llm.wait_for_settlements()
    day = await totals(ledger)
    assert day.reserved_micro_usd == 0 and day.charged_micro_usd > 0


async def test_a_late_settlement_is_charged_to_the_operation_start_day(transport, ledger):
    llm = gateway(transport, catalog=catalog())
    times = iter([datetime.datetime(2026, 10, 17, 23, 59, 59, tzinfo=UTC),
                  datetime.datetime(2026, 10, 18, 0, 0, 1, tzinfo=UTC)])
    allowance = budget(ledger, clock=lambda: next(times))

    async with llm.operation("chat", allowance):
        await llm.complete("chat", messages())

    assert (await totals(ledger, day="2026-10-17")).charged_micro_usd > 0
    assert (await totals(ledger, day="2026-10-18")).used_micro_usd == 0


async def test_the_next_utc_day_has_a_fresh_allowance(transport, ledger):
    llm = gateway(transport, catalog=catalog())
    now = [NOON]
    allowance = budget(ledger, clock=lambda: now[0])
    await spend_all(ledger)

    with pytest.raises(QuotaExhausted):
        async with llm.operation("chat", allowance):
            pass
    now[0] = datetime.datetime(2026, 10, 18, 0, 0, tzinfo=UTC)
    async with llm.operation("chat", allowance):
        await llm.complete("chat", messages())

    assert len(transport.paths) == 1


class FailingSettlement(AllowanceBudget):
    async def settle(self, admission, operation):
        raise RuntimeError("database is locked: Kdo byl Jan Novák?")


async def test_a_failed_settlement_keeps_the_reservation_and_the_answer(transport, ledger, caplog):
    llm = gateway(transport, catalog=catalog())

    async with llm.operation("chat", FailingSettlement(ledger, policy(), GUEST, lambda: NOON)):
        answer = await llm.complete("chat", messages())

    assert answer and (await totals(ledger)).reserved_micro_usd == 10_000
    assert "LLM operation settlement failed: RuntimeError" in caplog.text and "Novák" not in caplog.text


async def test_a_nested_operation_is_admitted_once(transport, ledger, tmp_path):
    llm = gateway(transport, catalog=catalog())

    async with llm.operation("chat", budget(ledger)):
        async with llm.operation("chat", budget(ledger)):
            await llm.complete("chat", messages())

    assert rows(tmp_path / "quota.db", "SELECT count(*) FROM llm_quota_operation") == [(1,)]
    assert rows(tmp_path / "quota.db", "SELECT count(*) FROM llm_quota_call") == [(1,)]


async def test_guests_and_accounts_are_charged_separately(transport, ledger):
    llm = gateway(transport, catalog=catalog())

    for principal in (GUEST, ACCOUNT):
        async with llm.operation("chat", budget(ledger, principal=principal)):
            await llm.complete("chat", messages())

    assert (await totals(ledger, GUEST)).charged_micro_usd == (await totals(ledger, ACCOUNT)).charged_micro_usd > 0

