"""Typed results of multi-write operations (ADR 0002).

Multi-write operations are best effort: completed writes are kept and failures are
reported, never turned into a plain success. ``succeeded`` lists the items whose writes
were acknowledged, so callers can update local state for exactly those items.
"""
from enum import Enum

from pydantic import BaseModel


class WriteOutcome(str, Enum):
    complete = "complete"
    """Every requested write was acknowledged (also when there was nothing to do)."""
    partial = "partial"
    """Some writes were acknowledged and some failed or were not attempted."""
    failed = "failed"
    """No requested write was acknowledged."""


class StepFailure(BaseModel):
    item_id: str | None = None
    """The object the failed write concerned (chunk, span, document, ...)."""
    step: str
    """Which write failed, e.g. ``link_chunk`` or ``delete_span``."""
    message: str
    uncertain: bool = False
    """The write timed out: it may have been applied even though it was not acknowledged."""


class WriteResult(BaseModel):
    outcome: WriteOutcome
    succeeded: list[str] = []
    failed: list[StepFailure] = []
    unattempted: list[str] = []
    """Items not attempted because the operation stopped early."""


def outcome_of(succeeded: int, failed: int, unattempted: int = 0) -> WriteOutcome:
    if failed == 0 and unattempted == 0:
        return WriteOutcome.complete
    return WriteOutcome.partial if succeeded else WriteOutcome.failed
