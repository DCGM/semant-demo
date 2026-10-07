"""Outcome classification and the no-progress guard for "first page again" loops."""
import pytest
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.schema.outcomes import WriteOutcome, outcome_of
from semant_demo.weaviate_exceptions import WeaviateOperationError
from semant_demo.weaviate_utils.helpers import guard_progress, step_failure


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

    with pytest.raises(WeaviateOperationError):
        guard_progress(seen, ["c", "d"])
