"""Collection export tickets and the one running export per user (#656)."""
from uuid import uuid4

import pytest

from semant_demo.core.errors import BusyError, NotFoundError
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
    ticket = registry.redeem(token)
    assert (ticket.user_id, ticket.collection_ids) == (user, (collection,))
    registry.release(user)
    with pytest.raises(NotFoundError):
        registry.redeem(token)

    late = registry.issue(user, [collection])
    clock.now = 60
    with pytest.raises(NotFoundError):
        registry.redeem(late)


def test_one_running_export_per_user_and_a_new_ticket_replaces_the_unused_one():
    registry = ExportRegistry(clock=Clock())
    user, other = uuid4(), uuid4()

    unused = registry.issue(user, [uuid4()])
    current = registry.issue(user, [uuid4()])
    with pytest.raises(NotFoundError):
        registry.redeem(unused)

    registry.redeem(current)
    assert registry.running(user)
    with pytest.raises(BusyError):
        registry.issue(user, [uuid4()])
    registry.redeem(registry.issue(other, [uuid4()]))  # others are not affected

    registry.release(user)
    assert not registry.running(user)
    registry.issue(user, [uuid4()])


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


async def test_a_download_that_ends_part_way_closes_the_stream_and_releases_the_user():
    from starlette.requests import ClientDisconnect

    from semant_demo.features.exports.routes import _ExportResponse
    closed, released = [], []

    async def stream():
        try:
            yield b"PK"
            yield b"more"
        finally:
            closed.append(True)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            raise OSError("client went away")

    response = _ExportResponse(stream(), "x.zip", lambda: released.append(True))
    with pytest.raises(ClientDisconnect):  # Starlette's name for the failed send
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert closed == [True] and released == [True]
