"""Outcome classification, the no-progress guard and the "first page again" delete loop."""
from types import SimpleNamespace

import pytest
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.schema.outcomes import WriteOutcome, outcome_of
from semant_demo.adapters.weaviate.writes import PAGE_SIZE, NoProgressError, _Progress, _drain, guard_progress, step_failure


@pytest.mark.parametrize("succeeded, failed, unattempted, expected", [
    (0, 0, 0, WriteOutcome.complete),   # nothing to do
    (3, 0, 0, WriteOutcome.complete),
    (2, 1, 0, WriteOutcome.partial),
    (2, 0, 1, WriteOutcome.partial),
    (0, 2, 0, WriteOutcome.failed),
    (0, 1, 1, WriteOutcome.failed),
])
def test_outcome_of(succeeded, failed, unattempted, expected):
    assert outcome_of(succeeded, failed, unattempted) == expected


def test_timeouts_are_uncertain_other_failures_are_not():
    assert step_failure("link_chunk", "a", WeaviateTimeoutError("slow")).uncertain
    assert not step_failure("link_chunk", "a", RuntimeError("boom")).uncertain


def test_failure_message_does_not_expose_error_details():
    failure = step_failure("link_chunk", "a", RuntimeError("secret internal detail"))

    assert "secret" not in failure.message


def test_guard_allows_new_pages_and_stops_on_a_repeated_object():
    seen: set = set()
    guard_progress(seen, ["a", "b"])
    guard_progress(seen, ["c"])

    with pytest.raises(NoProgressError):
        guard_progress(seen, ["c", "d"])


class FakeCollection:
    """A collection whose query returns the objects still in ``matching``."""

    def __init__(self, ids):
        self.matching = list(ids)
        self.queries = 0
        self.query = self

    async def fetch_objects(self, filters=None, limit=None, return_properties=None):
        self.queries += 1
        return SimpleNamespace(objects=[SimpleNamespace(uuid=i) for i in self.matching[:limit]])


async def test_drain_stops_on_a_short_page_whose_writes_do_not_take_effect():
    collection = FakeCollection(["a", "b", "c"])  # fewer than one page
    processed = []

    async def no_op(uuid):  # reports success, removes nothing
        processed.append(uuid)

    with pytest.raises(NoProgressError):
        await _drain(collection, None, no_op, _Progress(), "delete_span")

    assert processed == ["a", "b", "c"]
    assert collection.queries == 2


async def test_drain_requeries_until_nothing_matches():
    collection = FakeCollection(range(PAGE_SIZE + 5))

    async def remove(uuid):
        collection.matching.remove(uuid)

    await _drain(collection, None, remove, _Progress(), "delete_span")

    assert collection.matching == []
    assert collection.queries == 3  # full page, short page, empty result
