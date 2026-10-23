"""AI suggestion workflow (features/annotations/suggestions.py) with a deterministic fake provider.

In-memory store fakes record every write, so the tests can check that a span is stored
before its event, that failures are reported and that cancellation stops the remaining
provider calls without cutting a write. The HTTP stream and real Weaviate are covered in
tests/integration/test_suggestions.py.
"""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import anyio
import pytest

from tests.chunk_fakes import in_range, positioned
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.adapters.topicer.client import TopicerError, TopicerProposals
from semant_demo.core.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from semant_demo.features.annotations import suggestions
from semant_demo.features.annotations.schemas import (
    SuggestSpansRequest, SuggestSpansSelectionRequest, Tag,
)
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.annotations.suggestion_routes import _RunResponse
from semant_demo.features.user_collections.access import AuthenticationRequired
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.core.outcomes import StepFailure

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), is_superuser=False) for _ in range(3))
COLLECTION, OTHER_COLLECTION, DOCUMENT = uuid4(), uuid4(), uuid4()
PERSON, PLACE, FOREIGN_TAG = uuid4(), uuid4(), uuid4()


def chunk(order, text, in_collection=True):
    return SimpleNamespace(id=uuid4(), order=order, text=text, in_collection=in_collection)


class World:
    """Fake store of one document; ``chunks`` in document order, some outside the collection."""

    def __init__(self, *texts: str | tuple[str, bool]):
        self.chunks = [chunk(i, *(t if isinstance(t, tuple) else (t,))) for i, t in enumerate(texts)]
        self.log: list = []  # every write and provider call, in order
        self.insert_fail: dict[int, Exception] = {}  # by insert number
        self.sync_failures: list[StepFailure] = []
        self.insert_gate: asyncio.Event | None = None
        self.inserted = 0
        self.stored: dict[UUID, object] = {}
        self.holds: list = []  # tenant activity: (event, collection, spans inserted so far)
        self.chunk_text_reads = 0
        self.chunk_texts_fail = False
        self.provenance = False  # the collection holds provenance (#460)
        self.recorded: dict[UUID, dict] = {}

    def by_id(self, chunk_id):
        return next((c for c in self.chunks if c.id == chunk_id), None)

    # collections
    async def read_access_record(self, cid):
        return {COLLECTION: (OWNER.id, {SHARED.id}), OTHER_COLLECTION: (OTHER.id, set())}.get(cid)

    async def document_in_collection(self, document_id, cid):
        return (document_id, cid) == (DOCUMENT, COLLECTION)

    async def chunk_ids_in_collection(self, ids, cid, document=None):
        return {i for i in ids if (c := self.by_id(i)) and c.in_collection} if cid == COLLECTION else set()

    async def read_all_chunks_by_document(self, document_id, cid):
        return [c for c in self.chunks if c.in_collection]

    # tags
    async def read_collection_ids(self, ids):
        owners = {PERSON: [COLLECTION], PLACE: [COLLECTION], FOREIGN_TAG: [OTHER_COLLECTION]}
        return {t: owners[t] for t in ids if t in owners}

    async def read(self, tag_id):
        name = {PERSON: "person", PLACE: "place"}[tag_id]
        return Tag(id=tag_id, name=name, shorthand=name[0], color="red", pictogram="", definition=name,
                   examples=[])

    # spans
    async def insert(self, cid, span, document_id, derived=None, provenance=None):
        assert (cid, document_id) == (COLLECTION, DOCUMENT)  # the run's tenant and the chunk's document
        self.inserted += 1
        number = self.inserted
        self.log.append(("insert_start", span.chunkId, span.start, span.end))
        if self.insert_gate is not None:
            await self.insert_gate.wait()
        if number in self.insert_fail:
            raise self.insert_fail[number]
        span_id = uuid4()
        self.stored[span_id] = span
        if provenance is not None:
            self.recorded[span_id] = provenance
        self.log.append(("inserted", span_id))
        return span_id

    # chunk tags
    async def sync(self, cid, pairs):
        assert cid == COLLECTION
        self.log.append(("sync", frozenset(pairs)))
        return list(self.sync_failures)

    # documents
    def _texts(self) -> list[AnnotationChunk]:
        return positioned([AnnotationChunk(id=c.id, document_id=DOCUMENT, order=c.order, text=c.text)
                           for c in self.chunks])

    async def read_chunk_text(self, chunk_id):
        return next((c for c in self._texts() if str(c.id) == str(chunk_id)), None)

    async def read_chunk_texts_in_range(self, document_id, first, last):
        self.log.append(("read_range", first, last))
        self.chunk_text_reads += 1
        if self.chunk_texts_fail:
            raise ConnectionError("chunk texts unavailable")
        return in_range(self._texts(), document_id, first, last)

    def store(self) -> AnnotationStore:
        spans = SimpleNamespace(insert=self.insert, provenance=self.provenance)
        tags = SimpleNamespace(read_collection_ids=self.read_collection_ids, read=self.read)
        return AnnotationStore(collections=self, tags=tags, spans=spans,
                               chunk_tags=SimpleNamespace(sync=self.sync), documents=self, activity=self)

    # tenant activity: the run holds its collection's tenant in use
    async def touch(self, cid, *, force=False):
        self.holds.append(("touch", cid, self.inserted))

    @asynccontextmanager
    async def in_use(self, cid):
        self.holds.append(("in_use", cid, self.inserted))
        try:
            yield
        finally:
            self.holds.append(("released", cid, self.inserted))


def proposal(tag, start, end, **extra):
    return {"tag": {"id": str(tag)}, "span_start": start, "span_end": end, **extra}


class FakeProvider:
    """``answers[text]`` is a list of proposals, an exception, or an awaitable gate before the list.
    ``usage[text]`` is the usage reported with the answer (default: none, unknown)."""

    max_chunks_per_tag = 40
    config_name = "fake-config"

    def __init__(self, world: World, answers: dict | None = None, stream: dict | None = None,
                 usage: dict | None = None, configs: list[str] | Exception | None = None):
        self.world = world
        self.configs = ["fake-config", "fake-other"] if configs is None else configs
        self.config_lists = 0
        self.configs_used: list[str] = []
        self.usage = usage or {}
        self.answers = answers or {}
        self.stream = stream or {}
        self.running = 0
        self.max_running = 0
        self.cancelled: list[str] = []
        self.calls: list[str] = []
        self.cancel_delay = 0.0  # time a cancelled call needs to end (closing its connection)

    async def list_configs(self):
        self.config_lists += 1
        if isinstance(self.configs, Exception):
            raise self.configs
        return list(self.configs)

    async def propose_for_text(self, *, chunk_id, text, tags, config_name=None):
        self.calls.append(text)
        self.configs_used.append(config_name or self.config_name)
        self.world.log.append(("provider", text))
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        try:
            answer = self.answers.get(text, [])
            if isinstance(answer, tuple):  # (gate, proposals)
                gate, answer = answer
                await gate.wait()
            await asyncio.sleep(0)
            if isinstance(answer, Exception):
                raise answer
            return TopicerProposals(proposals=answer, usage=self.usage.get(text))
        except asyncio.CancelledError:
            self.cancelled.append(text)
            if self.cancel_delay:
                await asyncio.sleep(self.cancel_delay)
            raise
        finally:
            self.running -= 1

    async def propose_for_db_stream(self, *, tag, collection_id, document_id, config_name=None):
        self.calls.append(tag.name)
        self.configs_used.append(config_name or self.config_name)
        for item in self.stream.get(tag.name, []):
            if isinstance(item, Exception):
                raise item
            yield item


def request(tags=(PERSON,), collection=COLLECTION, config_name=None):
    return SuggestSpansRequest(collection_id=str(collection), document_id=str(DOCUMENT),
                               tag_ids=[str(t) for t in tags], config_name=config_name)


async def run_all(run):
    events = [e async for e in run.events()]
    assert events[-1].event == "end" and all(e.event == "result" for e in events[:-1])
    return events[:-1], events[-1]


async def thorough(world, provider, user=OWNER, req=None):
    return await suggestions.prepare_document_run(world.store(), provider, user, req or request(), "thorough")


# ── Progressive persistence and outcomes ───────────────────────────────────


async def test_a_run_holds_its_collections_tenant_in_use_while_it_runs():
    # The idle deactivation (#327) must not deactivate a tenant a run is writing to.
    world = World("Jan Novák v Brně", "Brno a Jan")
    provider = FakeProvider(world, {"Jan Novák v Brně": [proposal(PERSON, 0, 9)],
                                    "Brno a Jan": [proposal(PERSON, 7, 10)]})
    run = await thorough(world, provider)
    assert world.holds == []  # preparing does not use the tenant yet

    [event async for event in run.events()]

    assert world.holds == [("in_use", COLLECTION, 0), ("released", COLLECTION, 2)]



async def test_each_event_follows_its_stored_span():
    world = World("Jan Novák v Brně", "Brno a Jan")
    gate = asyncio.Event()
    provider = FakeProvider(world, {
        "Jan Novák v Brně": [proposal(PERSON, 0, 9)],
        "Brno a Jan": (gate, [proposal(PERSON, 7, 10)]),
    })
    events = (await thorough(world, provider)).events()

    first = await anext(events)

    # The first chunk's span is stored (and its chunk tag synced) before its event, while
    # the second chunk is still waiting for the provider.
    [span] = first.spans
    assert ("inserted", UUID(span.id)) in world.log and world.log[-1][0] == "sync"
    assert (span.chunkId, span.start, span.end, span.type.value) == (str(world.chunks[0].id), 0, 9, "auto")
    gate.set()
    second, end = await anext(events), await anext(events)
    assert second.chunk_id == str(world.chunks[1].id) and len(second.spans) == 1
    assert (end.outcome.value, end.saved, end.rejected) == ("complete", 2, 0)


async def test_spans_of_a_run_record_ai_origin_its_run_and_its_user():
    world = World("Jan Novák v Brně", "Brno a Jan")
    world.provenance = True
    provider = FakeProvider(world, {"Jan Novák v Brně": [proposal(PERSON, 0, 9)],
                                    "Brno a Jan": [proposal(PERSON, 7, 10)]})
    await run_all(await thorough(world, provider, user=SHARED))
    await run_all(await thorough(world, provider, user=SHARED))

    recorded = list(world.recorded.values())
    assert {(r["origin"], r["createdBy"], r["editVersion"]) for r in recorded} == {("ai", SHARED.id, 0)}
    # One id per run, shared by its spans.
    assert [r["aiRunId"] for r in recorded].count(recorded[0]["aiRunId"]) == 2
    assert len({r["aiRunId"] for r in recorded}) == 2


async def test_provider_failure_after_partial_success_keeps_saved_spans():
    world = World("Jan Novák", "Brno")
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3)], "Brno": TopicerError("timeout")})

    results, end = await run_all(await thorough(world, provider))

    by_chunk = {e.chunk_id: e for e in results}
    assert len(by_chunk[str(world.chunks[0].id)].spans) == 1
    assert by_chunk[str(world.chunks[1].id)].error == "topicer: timeout"
    assert (end.outcome.value, end.saved, end.provider_failures) == ("partial", 1, 1)
    assert len(world.stored) == 1


async def test_failure_of_every_provider_call_is_a_failed_run():
    world = World("a", "b")
    provider = FakeProvider(world, {"a": TopicerError("down"), "b": TopicerError("down")})

    _, end = await run_all(await thorough(world, provider))

    assert (end.outcome.value, end.provider_failures, end.saved) == ("failed", 2, 0)


async def test_no_proposals_is_a_complete_run():
    world = World("a", "b")

    results, end = await run_all(await thorough(world, FakeProvider(world)))

    assert [e.spans for e in results] == [[], []]
    assert (end.outcome.value, end.saved) == ("complete", 0)


async def test_storage_failures_are_reported_and_timeouts_marked_uncertain():
    world = World("Jan Novák")
    world.insert_fail = {1: RuntimeError("down"), 2: WeaviateTimeoutError("slow")}
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3), proposal(PERSON, 4, 9),
                                                  proposal(PLACE, 0, 9)]})

    [event], end = await run_all(await thorough(world, provider, req=request((PERSON, PLACE))))

    assert (len(event.spans), event.unsaved) == (1, 2)
    assert "storage failure" in event.error and "storage failure, may have been saved" in event.error
    assert (end.outcome.value, end.saved, end.save_failures) == ("partial", 1, 2)


async def test_saved_span_without_chunk_tag_is_partial():
    world = World("Jan Novák")
    world.sync_failures = [StepFailure(item_id="x", step="update_chunk_tags", message="down")]
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3)]})

    [event], end = await run_all(await thorough(world, provider))

    assert len(event.spans) == 1 and "not yet findable by tag search" in event.error
    assert (end.outcome.value, end.search_tag_failures) == ("partial", 1)


def with_derived_data(world: World) -> World:
    store = world.store()
    store.enrichment = Enrichment(derived=True)
    world.store = lambda: store
    return world


async def test_a_run_reads_the_chunks_around_its_spans_once_for_their_derived_data():
    world = with_derived_data(World("Jan Novák", "Karel Čapek"))
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3), proposal(PERSON, 4, 9)],
                                    "Karel Čapek": [proposal(PERSON, 0, 5)]})

    events, end = await run_all(await thorough(world, provider))

    assert (end.outcome.value, end.saved, end.enrichment_failures) == ("complete", 3, 0)
    # After the first chunk, after the second and before it (#463, the chunks' saves run
    # concurrently); the second span of the first chunk reads nothing again.
    assert sorted(e for e in world.log if e[0] == "read_range") == [
        ("read_range", -3, 0), ("read_range", 1, 4), ("read_range", 2, 5)]


async def test_saved_span_without_derived_text_counts_as_an_enrichment_failure():
    world = with_derived_data(World("Jan Novák"))
    world.chunk_texts_fail = True
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3)]})

    [event], end = await run_all(await thorough(world, provider))

    assert len(event.spans) == 1 and "without current search text or vector" in event.error
    assert (end.outcome.value, end.enrichment_failures, end.search_tag_failures) == ("partial", 1, 0)


# ── Validation of provider output ──────────────────────────────────────────


async def test_invalid_proposals_are_rejected_without_writes():
    world = World("Jan Novák")  # 9 characters
    provider = FakeProvider(world, {"Jan Novák": [
        proposal(FOREIGN_TAG, 0, 3),          # another collection's tag
        proposal(uuid4(), 0, 3),              # unknown tag
        {"tag": {"id": "not-a-uuid"}, "span_start": 0, "span_end": 3},
        {"span_start": 0, "span_end": 3},     # no tag
        proposal(PERSON, None, 3),
        proposal(PERSON, -1, 3),
        proposal(PERSON, 3, 3),
        proposal(PERSON, 5, 2),
        proposal(PERSON, 0, 10),              # past the end: rejected, not clamped
        proposal(PERSON, True, 3),
        proposal(PERSON, "0", 3),
        proposal(PERSON, 0.5, 3),
        "not a proposal",
        proposal(PERSON.hex.upper(), 4, 9.0),  # valid: tag id spelling and integral float
    ]})

    [event], end = await run_all(await thorough(world, provider))

    [span] = event.spans
    assert (span.tagId, span.start, span.end) == (str(PERSON), 4, 9)
    assert event.unsaved == 13
    assert "tag outside the request" in event.error and "invalid offsets" in event.error
    assert (end.outcome.value, end.saved, end.rejected) == ("complete", 1, 13)
    assert [entry for entry in world.log if entry[0] == "insert_start"] == [("insert_start", str(world.chunks[0].id), 4, 9)]


async def test_provider_offsets_are_stored_in_utf16_units():
    world = World("😀 Jan Novák")  # the emoji is one code point, two UTF-16 units
    provider = FakeProvider(world, {"😀 Jan Novák": [proposal(PERSON, 2, 11, reason="r", confidence=0.5)]})

    [event], _ = await run_all(await thorough(world, provider))

    [span] = event.spans
    assert (span.start, span.end, span.reason, span.confidence) == (3, 12, "r", 0.5)


# ── Cancellation and concurrency ───────────────────────────────────────────


async def test_closing_the_stream_cancels_and_awaits_remaining_provider_calls():
    world = World("done", "slow 1", "slow 2")
    never = asyncio.Event()
    provider = FakeProvider(world, {"done": [proposal(PERSON, 0, 4)], "slow 1": (never, []),
                                    "slow 2": (never, [])})
    run = await thorough(world, provider)
    events = run.events()

    first = await anext(events)
    await events.aclose()

    assert len(first.spans) == 1 and len(world.stored) == 1  # saved work remains
    assert sorted(provider.cancelled) == ["slow 1", "slow 2"] and provider.running == 0
    assert run.summary.outcome.value == "cancelled" and run.summary.saved == 1


async def test_cancelling_the_consumer_cancels_provider_calls():
    world = World("slow 1", "slow 2")
    never = asyncio.Event()
    provider = FakeProvider(world, {"slow 1": (never, []), "slow 2": (never, [])})
    run = await thorough(world, provider)

    async def consume():
        async for _ in run.events():
            pass

    task = asyncio.create_task(consume())
    while provider.running < 2:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sorted(provider.cancelled) == ["slow 1", "slow 2"] and provider.running == 0
    assert run.summary.outcome.value == "cancelled"


async def test_starlette_style_cancellation_waits_until_provider_calls_ended():
    # anyio re-delivers a cancel scope's cancellation at every await; cleanup must still wait.
    world = World("slow 1", "slow 2")
    never = asyncio.Event()
    provider = FakeProvider(world, {"slow 1": (never, []), "slow 2": (never, [])})
    provider.cancel_delay = 0.05
    run = await thorough(world, provider)

    async def consume():
        with anyio.CancelScope() as scope:
            async def cancel_soon():
                while provider.running < 2:
                    await asyncio.sleep(0)
                scope.cancel()
            canceller = asyncio.create_task(cancel_soon())
            async for _ in run.events():
                pass
        await canceller

    await consume()

    assert sorted(provider.cancelled) == ["slow 1", "slow 2"] and provider.running == 0


async def test_cancellation_during_a_write_finishes_the_write_first():
    # Starlette cancels a disconnected stream through an anyio cancel scope.
    world = World("Jan Novák")
    world.insert_gate = asyncio.Event()
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3), proposal(PERSON, 4, 9)]})
    run = await thorough(world, provider)

    async def consume(scope_holder):
        with anyio.CancelScope() as scope:
            scope_holder.append(scope)
            async for _ in run.events():
                pass

    holder = []
    task = asyncio.create_task(consume(holder))
    while not any(e[0] == "insert_start" for e in world.log):
        await asyncio.sleep(0)
    holder[0].cancel()
    for _ in range(5):
        await asyncio.sleep(0)
    world.insert_gate.set()
    await task

    # The first write finished, including its chunk tag; the second was never started.
    assert [e[0] for e in world.log if e[0] != "provider"] == ["insert_start", "inserted", "sync"]
    assert run.summary.outcome.value == "cancelled"


async def test_provider_calls_are_bounded_and_started_as_others_finish():
    world = World(*(f"chunk {i}" for i in range(25)))
    provider = FakeProvider(world, {f"chunk {i}": [proposal(PERSON, 0, 5)] for i in range(25)})

    results, end = await run_all(await thorough(world, provider))

    assert provider.max_running == suggestions.PROVIDER_CONCURRENCY
    assert len(results) == 25 and end.saved == 25


async def test_unexpected_error_ends_the_run_with_an_error_and_stops_other_calls(caplog):
    world = World("ok", "boom", "slow")
    never, after_ok = asyncio.Event(), asyncio.Event()
    provider = FakeProvider(world, {"ok": [proposal(PERSON, 0, 2)], "boom": (after_ok, ValueError("bug SECRET-MARKER")),
                                    "slow": (never, [])})
    events = (await thorough(world, provider)).events()

    first = await anext(events)
    after_ok.set()
    rest = [e async for e in events]

    assert len(first.spans) == 1 and [e.event for e in rest] == ["end"]
    end = rest[0]
    assert end.outcome.value == "partial" and end.saved == 1 and "unexpected error" in end.error
    assert "ValueError" in caplog.text and "SECRET-MARKER" not in caplog.text
    assert provider.cancelled == ["slow"] and provider.running == 0


async def test_route_closes_the_run_when_the_client_disconnects():
    # Starlette does not close a streaming response's iterator after a disconnect.
    world = World("done", "slow")
    never = asyncio.Event()
    provider = FakeProvider(world, {"done": [proposal(PERSON, 0, 4)], "slow": (never, [])})
    run = await thorough(world, provider)
    response = _RunResponse(run)
    sent, disconnected = [], asyncio.Event()

    async def send(message):
        sent.append(message)
        if message.get("body"):
            disconnected.set()
            await never.wait()  # the client is gone: the write never completes

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    await asyncio.wait_for(response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send), 5)

    assert b'"event":"result"' in sent[1]["body"]
    assert provider.cancelled == ["slow"] and provider.running == 0
    assert run.summary.outcome.value == "cancelled"


async def test_running_again_stores_duplicate_suggestions():
    # Characterization (ADR 0003): proposals are not compared with stored spans; decide the
    # regeneration policy before adding retries.
    world = World("Jan Novák")
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3)]})

    for _ in range(2):
        await run_all(await thorough(world, provider))

    assert [(s.chunkId, s.start, s.end) for s in world.stored.values()] == [(str(world.chunks[0].id), 0, 3)] * 2


# ── Access and request checks ──────────────────────────────────────────────


@pytest.mark.parametrize("user, req, error", [
    (None, request(), AuthenticationRequired),
    (OTHER, request(), NotFoundError),
    (OWNER, request(tags=(FOREIGN_TAG,)), NotFoundError),
    (OWNER, request(tags=()), InvalidRequestError),
    (OWNER, request(collection=OTHER_COLLECTION), NotFoundError),
])
async def test_denied_or_invalid_requests_fail_before_any_provider_call(user, req, error):
    world = World("Jan Novák")
    provider = FakeProvider(world)

    with pytest.raises(error):
        await thorough(world, provider, user=user, req=req)

    assert provider.calls == [] and world.log == []


async def test_shared_user_may_run_suggestions():
    world = World("Jan Novák")
    provider = FakeProvider(world, {"Jan Novák": [proposal(PERSON, 0, 3)]})

    _, end = await run_all(await thorough(world, provider, user=SHARED))

    assert end.saved == 1


# ── Choice of the Topicer configuration (#189) ─────────────────────────────


@pytest.mark.parametrize("config_name", [None, "fake-config"])
async def test_the_default_configuration_is_used_without_asking_for_the_list(config_name):
    world = World("Jan Novák")
    provider = FakeProvider(world)

    await run_all(await thorough(world, provider, req=request(config_name=config_name)))

    assert provider.configs_used == ["fake-config"] and provider.config_lists == 0


async def test_a_listed_configuration_is_used_in_every_mode():
    world = World("Jan Novák")
    provider = FakeProvider(world, stream={"person": []})

    await run_all(await thorough(world, provider, req=request(config_name="fake-other")))
    await run_all(await suggestions.prepare_document_run(
        world.store(), provider, OWNER, request(config_name="fake-other"), "optimized"))
    await run_all(await suggestions.prepare_selection_run(
        world.store(), provider, OWNER, selection(world, world.chunks, 0, 3, config_name="fake-other")))

    assert provider.configs_used == ["fake-other"] * 3


@pytest.mark.parametrize("configs, error", [
    (["fake-config"], InvalidRequestError),
    (TopicerError("HTTP 500"), ServiceUnavailableError),
])
async def test_an_unknown_configuration_or_an_unreadable_list_fails_before_any_provider_call(configs, error):
    world = World("Jan Novák")
    provider = FakeProvider(world, configs=configs)

    with pytest.raises(error):
        await thorough(world, provider, req=request(config_name="fake-other"))
    with pytest.raises(error):
        await suggestions.prepare_selection_run(
            world.store(), provider, OWNER, selection(world, world.chunks, 0, 3, config_name="fake-other"))

    assert provider.calls == [] and world.log == []


async def test_an_optimized_run_stops_when_the_configuration_has_no_optimized_mode():
    world = World("Jan Novák")
    refused = TopicerError("HTTP 409", no_work=True)
    provider = FakeProvider(world, stream={"person": [refused], "place": [refused]})

    results, end = await run_all(await suggestions.prepare_document_run(
        world.store(), provider, OWNER, request(tags=(PERSON, PLACE), config_name="fake-other"), "optimized"))

    assert provider.calls == ["person"] and results == []
    assert (end.outcome.value, end.error, end.units_processed) == (
        "failed", suggestions.UNSUPPORTED_OPTIMIZED, 1)


async def test_access_is_checked_before_the_configurations_are_listed():
    world = World("Jan Novák")
    provider = FakeProvider(world)

    with pytest.raises(NotFoundError):
        await thorough(world, provider, user=OTHER, req=request(config_name="fake-other"))

    assert provider.config_lists == 0


# ── Optimized mode ─────────────────────────────────────────────────────────


async def test_optimized_validates_chunks_returned_by_the_provider():
    world = World("Jan Novák", ("Brno", False))
    inside, outside = world.chunks
    provider = FakeProvider(world, stream={
        "person": [
            {"id": str(inside.id), "tag_span_proposals": [{"span_start": 0, "span_end": 3}]},  # tag of the stream
            {"id": str(outside.id), "tag_span_proposals": [proposal(PERSON, 0, 4)]},
            {"id": "garbage", "tag_span_proposals": [proposal(PERSON, 0, 4)]},
        ],
        "place": [TopicerError("down")],
    })
    run = await suggestions.prepare_document_run(world.store(), provider, OWNER, request((PERSON, PLACE)),
                                                 "optimized")

    results, end = await run_all(run)

    assert [(e.chunk_id, len(e.spans), e.unsaved) for e in results] == [
        (str(inside.id), 1, 0), (str(outside.id), 0, 1), ("", 0, 0)]
    assert results[0].spans[0].tagId == str(PERSON)
    assert "chunk outside the collection" in results[1].error
    assert results[2].error == "topicer (tag=place): down"
    assert (end.outcome.value, end.saved, end.rejected, end.provider_failures) == ("partial", 1, 2, 1)


# ── Selection ──────────────────────────────────────────────────────────────


def selection(world, chunks, start, end, tags=(PERSON,), config_name=None):
    return SuggestSpansSelectionRequest(
        collection_id=str(COLLECTION), document_id=str(DOCUMENT), chunk_ids=[str(c.id) for c in chunks],
        selection_start=start, selection_end=end, tag_ids=[str(t) for t in tags], config_name=config_name)


async def test_selection_spans_are_anchored_where_they_start():
    world = World("Jan 😀 Novák", "z Brna")
    first, second = world.chunks
    # UTF-16: "Jan 😀 Novák" is 12 units (11 code points). Select "Novák" + "z Brna".
    provider = FakeProvider(world, {"Novákz Brna": [proposal(PERSON, 0, 5), proposal(PLACE, 5, 11),
                                                    proposal(PERSON, 2, 7)]})

    results, end = await run_all(await suggestions.prepare_selection_run(
        world.store(), provider, OWNER, selection(world, [first, second], 7, 18, (PERSON, PLACE))))

    spans = [(s.chunkId, s.start, s.end) for e in results for s in e.spans]
    assert spans == [
        (str(first.id), 7, 12),     # "Novák" in the first chunk, UTF-16 units
        (str(second.id), 0, 6),     # "z Brna" anchored on the second chunk
        (str(first.id), 9, 14),     # "vák" + "z " continues into the second chunk
    ]
    assert end.saved == 3


async def test_selection_across_a_chunk_outside_the_collection_counts_its_text():
    world = World("Jan ", ("Novák ", False), "z Brna")
    first, hidden, last = world.chunks
    # The browser sends only the collection's chunks: the selection text is "Jan z Brna".
    provider = FakeProvider(world, {"Jan z Brna": [proposal(PERSON, 0, 5)]})

    results, _ = await run_all(await suggestions.prepare_selection_run(
        world.store(), provider, OWNER, selection(world, [first, last], 0, 10)))

    [span] = results[0].spans
    # Stored like a user span over "Jan Novák z": the end counts the hidden chunk.
    assert (span.chunkId, span.start, span.end) == (str(first.id), 0, len("Jan Novák z"))


async def test_selection_proposal_across_a_gap_is_rejected():
    world = World("Jan ", "z Brna")
    first, last = world.chunks
    last.order = 5  # chunks 1-4 do not exist
    provider = FakeProvider(world, {"Jan z Brna": [proposal(PERSON, 0, 5)]})

    [event], end = await run_all(await suggestions.prepare_selection_run(
        world.store(), provider, OWNER, selection(world, [first, last], 0, 10)))

    assert (event.spans, event.unsaved) == ([], 1) and "crosses a gap" in event.error
    assert end.rejected == 1 and world.stored == {}


@pytest.mark.parametrize("order, start, end, message", [
    ("reversed", 0, 3, "document order"),
    ("forward", 30, 40, "no text"),
    ("forward", 3, 3, "greater than"),
])
async def test_invalid_selections_are_refused_before_the_provider(order, start, end, message):
    world = World("Jan ", "z Brna")
    chunks = world.chunks if order == "forward" else world.chunks[::-1]
    provider = FakeProvider(world)

    with pytest.raises(InvalidRequestError, match=message):
        await suggestions.prepare_selection_run(world.store(), provider, OWNER, selection(world, chunks, start, end))

    assert provider.calls == []


async def test_selection_provider_failure_is_an_event_and_a_failed_run():
    world = World("Jan Novák")
    provider = FakeProvider(world, {"Jan": TopicerError("down")})

    [event], end = await run_all(await suggestions.prepare_selection_run(
        world.store(), provider, OWNER, selection(world, world.chunks, 0, 3)))

    assert event.error == "topicer: down" and end.outcome.value == "failed"
