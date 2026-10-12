"""Deterministic offline stand-ins for external AI providers.

Fakes implement only what the code under test uses. They never open connections, so
fast tests stay offline and produce the same result on every run.
"""
import hashlib
import math
from collections.abc import Callable


class FakeLlm:
    """Replaces ``adapters.llm.gateway.LlmGateway`` for callers of ``complete``.

    ``reply`` maps the request's messages to the reply text, or raises to simulate a
    provider failure. Every call is recorded in ``calls`` as ``(feature, messages, options)``.
    """

    def __init__(self, reply: Callable[[list[dict[str, str]]], str] | str = "fake reply"):
        self.reply = reply if callable(reply) else (lambda messages: reply)
        self.calls: list[tuple[str, list[dict[str, str]], dict]] = []

    async def complete(self, feature: str, messages, **options) -> str:
        self.calls.append((feature, list(messages), options))
        return self.reply(list(messages))


FAKE_EMBEDDING_DIM = 16


def fake_embedding(text: str, dim: int = FAKE_EMBEDDING_DIM) -> list[float]:
    """Deterministic unit vector for ``text``; stands in for the embedding service.

    Identical texts get identical vectors, so a query equal to a chunk's text is its
    nearest neighbour. It carries no semantic meaning beyond that.
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [digest[i % len(digest)] / 255.0 - 0.5 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class FakeStreamingChat:
    """Replaces ``adapters.llm.gateway.FeatureChat``: yields ``deltas``, records calls.

    With ``error`` set, raises it after the deltas (a provider failing mid-stream).
    """

    def __init__(self, deltas: list[str] | None = None, error: Exception | None = None):
        self.deltas = list(deltas if deltas is not None else ["Fits", " the tag."])
        self.error = error
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def stream(self, instructions: str, messages: list[dict[str, str]]):
        self.calls.append((instructions, messages))
        for delta in self.deltas:
            yield delta
        if self.error is not None:
            raise self.error
