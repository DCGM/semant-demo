"""Topicer suggestions charged to the account's daily AI allowance (#408).

Each thorough chunk, optimized tag stream and selection is one operation on a SQLite
ledger: admitted before Topicer is contacted (the first one before the stream starts, a
refusal is ``QuotaExhausted``), settled with Topicer's reported usage. A refusal later in
a run starts no further unit and the end event says why; unknown usage (errors,
cancellation, a stream without its summary) charges at least the reservation.
"""
import asyncio

import pytest

from semant_demo.adapters.topicer.client import TopicerCall, TopicerError, TopicerStreamSummary, TopicerUsage
from semant_demo.features.annotations import suggestions
from semant_demo.features.quota import service
from semant_demo.features.quota.service import AllowanceBudget, QuotaExhausted, QuotaPolicy
from tests.test_quota.test_ledger import ACCOUNT, NOON, call, ledgers  # noqa: F401
from tests.test_quota.test_operations import rows
from tests.test_suggestions import (
    OWNER, PERSON, PLACE, FakeProvider, World, proposal, request, run_all, selection,
)

DAY = "2026-10-17"


@pytest.fixture
async def ledger(ledgers, tmp_path):
    opened = await ledgers.open()
    opened.db = tmp_path / "quota.db"  # the ledgers' database file
    return opened


def budget(ledger, reserve_usd: float = 0.1) -> AllowanceBudget:
    policy = QuotaPolicy(guest_daily_micro_usd=250_000, account_daily_micro_usd=1_000_000, near_limit_ratio=0.8,
                         guest_cookie_max_age_seconds=60, guest_cookie_secure=False,
                         topicer_reserve_usd_per_chunk=reserve_usd)
    return AllowanceBudget(ledger, policy, ACCOUNT, lambda: NOON)


async def spend(ledger, usd: float) -> None:
    operation = await service.admit(ledger, budget(ledger).policy, ACCOUNT, "test", 0, now=NOON)
    await service.settle(ledger, operation, [call(usd)], now=NOON)


async def used(ledger) -> tuple[int, int]:
    totals = await ledger.totals(ACCOUNT.kind, ACCOUNT.id, DAY)
    return totals.charged_micro_usd, totals.reserved_micro_usd


def usage(*costs: float | None, source: str = "reported") -> TopicerUsage:
    calls = [TopicerCall(provider="openrouter", model="m", outcome="success", usage_source="reported",
                         cost_source=source if cost is not None else "unknown", cost_usd=cost,
                         input_tokens=1000, output_tokens=100) for cost in costs]
    return TopicerUsage(calls=calls, attempted_calls=len(calls))


def summary(*costs: float, processed: int | None = None, limit_reached=False, truncated=False,
            status="complete") -> TopicerStreamSummary:
    return TopicerStreamSummary(status=status, max_chunks=40, processed_chunks=len(costs) if processed is None
                                else processed, limit_reached=limit_reached, candidates_truncated=truncated,
                                usage=usage(*costs))


async def thorough(world, provider, ledger, reserve_usd=0.1):
    return await suggestions.prepare_document_run(world.store(), provider, OWNER, request(), "thorough",
                                                  budget(ledger, reserve_usd))


async def optimized(world, provider, ledger, reserve_usd=0.01, tags=(PERSON, PLACE)):
    return await suggestions.prepare_document_run(world.store(), provider, OWNER, request(tags), "optimized",
                                                  budget(ledger, reserve_usd))


def operations(db) -> list[tuple]:
    return rows(db, "SELECT feature, status, reserved_micro_usd, charged_micro_usd FROM llm_quota_operation "
                    "WHERE feature != 'test' ORDER BY started_at")


# ── Thorough: one operation per chunk ──────────────────────────────────────


async def test_an_exhausted_account_is_refused_before_any_topicer_call(ledger):
    world = World("Jan Novák", "Brno")
    provider = FakeProvider(world)
    await spend(ledger, 1.0)

    with pytest.raises(QuotaExhausted):
        await thorough(world, provider, ledger)

    assert provider.calls == [] and world.log == []
    assert operations(ledger.db) == []


async def test_each_chunk_is_settled_with_its_reported_cost(ledger):
    world = World("Jan Novák", "Brno")
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3)]},
                            usage={"Jan Novák": usage(0.002, 0.001), "Brno": usage(0.003, source="estimated")})

    _, end = await run_all(await thorough(world, provider, ledger))

    assert (end.outcome.value, end.unit, end.units_total, end.units_processed, end.stop_reason) == \
        ("complete", "chunk", 2, 2, None)
    assert sorted(operations(ledger.db)) == [("topicer_thorough", "settled", 100_000, 3_000)] * 2
    assert await used(ledger) == (6_000, 0)
    assert sorted(rows(ledger.db, "SELECT provider, cost_source, cost_micro_usd, input_tokens FROM llm_quota_call")) \
        == [("openrouter", "price", 3_000, 1000), ("openrouter", "provider", 1_000, 1000),
            ("openrouter", "provider", 2_000, 1000)]


async def test_missing_or_failed_usage_charges_the_reservation_and_a_refused_connection_nothing(ledger):
    world = World("no usage", "server error", "unreachable", "no proposals")
    provider = FakeProvider(world, {"server error": TopicerError("HTTP 500"),
                                    "unreachable": TopicerError("ConnectError", no_work=True)},
                            usage={"no proposals": usage(0.001)})

    _, end = await run_all(await thorough(world, provider, ledger))

    assert end.provider_failures == 2
    # No usage and an HTTP 500 are unknown work (the reservation); an empty answer is still charged.
    assert sorted(charged for *_, charged in operations(ledger.db)) == [0, 1_000, 100_000, 100_000]


async def test_a_thorough_run_stops_scheduling_when_the_allowance_runs_out(ledger):
    world = World(*(f"chunk {i}" for i in range(25)))
    provider = FakeProvider(world, {f"chunk {i}": [proposal(PERSON, 0, 5)] for i in range(25)})
    await spend(ledger, 0.75)

    results, end = await run_all(await thorough(world, provider, ledger))  # unknown usage: 0.1 per chunk

    assert len(provider.calls) == 2 and len(results) == 2 and end.saved == 2
    assert (end.outcome.value, end.units_processed, end.units_total, end.stop_reason) == \
        ("partial", 2, 25, "quota_exhausted")
    assert end.quota_exhausted.code == "llm_quota_exhausted" and end.quota_exhausted.principal == "account"
    assert await used(ledger) == (950_000, 0)


async def test_a_refusal_caused_by_running_chunks_waits_for_their_settlement(ledger):
    # Ten 0.1 reservations fill the allowance; settled at 0.001 each, the rest of the
    # chunks fit after all.
    world = World(*(f"chunk {i}" for i in range(25)))
    provider = FakeProvider(world, usage={f"chunk {i}": usage(0.001) for i in range(25)})
    await spend(ledger, 0.05)

    results, end = await run_all(await thorough(world, provider, ledger))

    assert len(results) == 25 and end.outcome.value == "complete" and end.stop_reason is None
    assert provider.max_running <= suggestions.PROVIDER_CONCURRENCY
    assert await used(ledger) == (50_000 + 25 * 1_000, 0)


async def test_simultaneous_runs_of_one_account_cannot_overspend(ledger):
    worlds = [World(*(f"{run} chunk {i}" for i in range(12))) for run in "ab"]
    providers = [FakeProvider(w) for w in worlds]  # unknown usage: each chunk costs its 0.1 reservation
    runs = [await thorough(w, p, ledger) for w, p in zip(worlds, providers)]

    ends = [end for _, end in await asyncio.gather(*(run_all(r) for r in runs))]

    assert sum(len(p.calls) for p in providers) == 10
    assert all(end.stop_reason == "quota_exhausted" for end in ends)
    assert await used(ledger) == (1_000_000, 0)


async def test_cancelled_chunks_keep_their_reservation_charged(ledger):
    world = World("done", "slow 1", "slow 2")
    never = asyncio.Event()
    provider = FakeProvider(world, {"slow 1": (never, []), "slow 2": (never, [])}, usage={"done": usage(0.001)})
    run = await thorough(world, provider, ledger)
    events = run.events()

    await anext(events)
    await events.aclose()

    assert sorted(provider.cancelled) == ["slow 1", "slow 2"]
    assert sorted(charged for _, status, _, charged in operations(ledger.db) if status == "settled") \
        == [1_000, 100_000, 100_000]
    assert await used(ledger) == (201_000, 0)
    assert rows(ledger.db, "SELECT count(*) FROM llm_quota_call WHERE outcome = 'unfinished'") == [(2,)]


# ── Optimized: one operation per tag stream ────────────────────────────────


async def test_each_tag_is_admitted_for_its_chunk_limit_and_settled_with_the_stream_usage(ledger):
    world = World("Jan Novák")
    chunk_id = str(world.chunks[0].id)
    provider = FakeProvider(world, stream={
        "person": [{"id": chunk_id, "tag_span_proposals": [proposal(PERSON, 0, 3)]}, summary(0.002, 0.001)],
        "place": [summary(0.001)],  # no proposals, still charged
    })

    _, end = await run_all(await optimized(world, provider, ledger))

    assert (end.outcome.value, end.unit, end.units_processed, end.max_chunks_per_tag) == ("complete", "tag", 2, 40)
    assert operations(ledger.db) == [("topicer_optimized", "settled", 400_000, 3_000),
                                     ("topicer_optimized", "settled", 400_000, 1_000)]


async def test_an_optimized_run_stops_before_the_next_tag_when_refused(ledger):
    world = World("Jan Novák")
    provider = FakeProvider(world, stream={"person": [summary(0.2)], "place": [summary(0.2)]})
    await spend(ledger, 0.5)

    results, end = await run_all(await optimized(world, provider, ledger))

    # person: 0.5 + 0.4 reserved fits, settles at 0.2; place: 0.7 + 0.4 does not.
    assert provider.calls == ["person"] and results == []
    assert (end.outcome.value, end.units_processed, end.units_total, end.stop_reason) == \
        ("partial", 1, 2, "quota_exhausted")


async def test_a_stream_without_its_summary_or_with_an_error_charges_the_reservation(ledger):
    world = World("Jan Novák")
    chunk_id = str(world.chunks[0].id)
    provider = FakeProvider(world, stream={
        "person": [{"id": chunk_id, "tag_span_proposals": [proposal(PERSON, 0, 3)]}],  # older Topicer
        "place": [{"id": chunk_id, "tag_span_proposals": []}, TopicerError("RemoteProtocolError")],
    })

    _, end = await run_all(await optimized(world, provider, ledger))

    assert (end.saved, end.provider_failures) == (1, 1)
    assert [charged for *_, charged in operations(ledger.db)] == [400_000, 400_000]


async def test_a_rejected_chunk_limit_is_a_free_reported_failure(ledger):
    world = World("Jan Novák")
    provider = FakeProvider(world, stream={"person": [TopicerError("HTTP 422", no_work=True)], "place": [summary()]})

    results, end = await run_all(await optimized(world, provider, ledger))

    assert "HTTP 422" in results[0].error and "per-tag limit of 40 chunks" in results[0].error
    assert (end.outcome.value, end.provider_failures) == ("partial", 1)
    assert [charged for *_, charged in operations(ledger.db)] == [0, 0]


async def test_tags_that_reached_the_chunk_limit_are_reported_with_truncation(ledger):
    world = World("Jan Novák")
    provider = FakeProvider(world, stream={
        "person": [summary(processed=40, limit_reached=True, truncated=True)],
        "place": [summary(processed=40, limit_reached=True, truncated=False)],
    })

    _, end = await run_all(await optimized(world, provider, ledger, tags=(PERSON, PLACE)))

    assert [(t.tag_name, t.max_chunks, t.processed_chunks, t.candidates_truncated) for t in end.tag_limits] == [
        ("person", 40, 40, True), ("place", 40, 40, False)]
    assert end.outcome.value == "complete"


async def test_a_partly_failed_stream_is_a_provider_failure(ledger):
    world = World("Jan Novák")
    provider = FakeProvider(world, stream={"person": [summary(0.001, status="partial")]})

    results, end = await run_all(await optimized(world, provider, ledger, tags=(PERSON,)))

    assert results[0].error == "topicer (tag=person): some chunks failed"
    assert end.outcome.value == "failed" and [c for *_, c in operations(ledger.db)] == [1_000]


async def test_the_tag_reservation_follows_a_non_default_chunk_limit(ledger):
    world = World("Jan Novák")
    provider = FakeProvider(world, stream={"person": [summary()]})
    provider.max_chunks_per_tag = 20

    _, end = await run_all(await optimized(world, provider, ledger, tags=(PERSON,)))

    assert end.max_chunks_per_tag == 20
    assert [reserved for _, _, reserved, _ in operations(ledger.db)] == [200_000]


# ── Selection: one operation ───────────────────────────────────────────────


async def test_a_selection_is_one_operation_admitted_before_the_call(ledger):
    world = World("Jan Novák")
    provider = FakeProvider(world, {"Jan": [proposal(PERSON, 0, 3)]}, usage={"Jan": usage(0.002)})
    req = selection(world, world.chunks, 0, 3)

    _, end = await run_all(await suggestions.prepare_selection_run(world.store(), provider, OWNER, req,
                                                                   budget(ledger)))
    await spend(ledger, 1.0)
    with pytest.raises(QuotaExhausted):
        await suggestions.prepare_selection_run(world.store(), provider, OWNER, req, budget(ledger))

    assert (end.saved, end.unit, end.units_processed) == (1, "selection", 1)
    assert operations(ledger.db) == [("topicer_selection", "settled", 100_000, 2_000)]
    assert provider.calls == ["Jan"]
