"""Collection export tickets and the one running export per user (#656)."""
import asyncio
from uuid import uuid4

import pytest

from semant_demo.core.errors import NotFoundError
from semant_demo.features.exports.service import ExportRegistry, _file_names, _slug
from semant_demo.features.user_collections.schemas import Collection


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_ticket_is_used_once_and_expires():
    clock = Clock()
    registry = ExportRegistry(ttl_seconds=60, clock=clock)
    user, collection = uuid4(), uuid4()

    token = registry.issue(user, [collection])
    ticket, run = registry.redeem(token)
    assert (ticket.user_id, ticket.collection_ids) == (user, (collection,))
    registry.release(run)
    with pytest.raises(NotFoundError):
        registry.redeem(token)

    late = registry.issue(user, [collection])
    clock.now = 60
    with pytest.raises(NotFoundError):
        registry.redeem(late)


def test_a_new_export_replaces_the_unused_ticket_and_ends_the_running_export():
    registry = ExportRegistry(clock=Clock())
    user, other = uuid4(), uuid4()

    unused = registry.issue(user, [uuid4()])
    current = registry.issue(user, [uuid4()])
    with pytest.raises(NotFoundError):
        registry.redeem(unused)

    _, run = registry.redeem(current)
    ended: list[str] = []
    run.cancel = lambda: ended.append("first")
    _, others = registry.redeem(registry.issue(other, [uuid4()]))  # others are not affected
    others.cancel = lambda: ended.append("other")

    # A stalled download never locks its user out: the next request ends it.
    newer = registry.issue(user, [uuid4()])
    assert ended == ["first"] and not registry.running(user)
    _, second = registry.redeem(newer)
    registry.release(run)  # the ended export's late release keeps the newer one
    assert registry.running(user)
    registry.release(second)
    assert not registry.running(user) and registry.running(other)


def _collection(name: str, collection_id=None) -> Collection:
    return Collection(id=collection_id or uuid4(), name=name, owner="owner", created_at="2026-01-01T00:00:00Z",
                      updated_at="2026-01-01T00:00:00Z", color="blue")


def test_file_names_are_ascii_and_unique():
    assert _slug("Kroniky a dopisy") == "kroniky-a-dopisy"
    assert _slug("Žluťoučký kůň / 1848") == "zlutoucky-kun-1848"
    assert _slug("…") == "collection"

    a = _collection("Same", "5e3a0000-0000-4000-8000-0000000c0001")
    b = _collection("Same", "5e3a0000-0000-4000-8000-0000000c0002")
    assert _file_names([a]) == ["same-5e3a0000.json"]
    assert _file_names([a, b]) == [f"same-{a.id}.json", f"same-{b.id}.json"]


def _run(registry: ExportRegistry, user):
    return registry.redeem(registry.issue(user, [uuid4()]))[1]


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


_SCOPE = {"type": "http", "asgi": {"spec_version": "2.4"}}


async def test_a_download_that_ends_part_way_closes_the_stream_and_releases_the_user():
    from starlette.requests import ClientDisconnect

    from semant_demo.features.exports.routes import _ExportResponse
    registry, user, closed = ExportRegistry(), uuid4(), []

    async def stream():
        try:
            yield b"PK"
            yield b"more"
        finally:
            closed.append(True)

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            raise OSError("client went away")

    response = _ExportResponse(stream(), "x.zip", _run(registry, user), registry.release)
    with pytest.raises(ClientDisconnect):  # Starlette's name for the failed send
        await response(_SCOPE, _receive, send)
    assert closed == [True] and not registry.running(user)


async def test_a_stalled_download_is_ended_by_the_next_export_of_its_user():
    from semant_demo.features.exports.routes import _ExportResponse
    registry, user, closed = ExportRegistry(), uuid4(), []
    stalled = asyncio.Event()

    async def stream():
        try:
            yield b"PK"
        finally:
            closed.append(True)

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            stalled.set()
            await asyncio.Event().wait()  # a paused download: the send never returns

    response = _ExportResponse(stream(), "x.zip", _run(registry, user), registry.release)
    download = asyncio.create_task(response(_SCOPE, _receive, send))
    await stalled.wait()

    registry.issue(user, [uuid4()])  # the user starts another export
    await asyncio.wait_for(download, 1)  # ends without an error of its own
    assert closed == [True] and not registry.running(user)


async def test_a_cancelled_export_waits_for_the_write_in_progress():
    import threading

    from semant_demo.features.exports.service import _write
    started, finish, written = threading.Event(), threading.Event(), []

    class Entry:
        def write(self, data):
            started.set()
            finish.wait(1)
            written.append(data)

    task = asyncio.create_task(_write(Entry(), b"data"))
    await asyncio.to_thread(started.wait, 1)
    task.cancel()
    await asyncio.sleep(0.01)
    assert not task.done()  # still waiting for the thread, which writes on
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written == [b"data"]
