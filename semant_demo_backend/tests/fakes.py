"""Deterministic offline stand-ins for external AI providers.

Fakes implement only what the code under test uses. They never open connections, so
fast tests stay offline and produce the same result on every run.
"""
import hashlib
import math

from ollama import ChatResponse, Message

from semant_demo.llm_api import APIModelResponseOllama, APIOutput, APIRequest


class FakeChatAPI:
    """Replaces an ``APIAsync`` chat provider.

    Replies are looked up by request ``custom_id``; requests without a configured reply get
    ``default_reply``. Every request is recorded in ``requests`` for assertions.
    """

    def __init__(self, replies: dict[str, str] | None = None, default_reply: str = "fake reply"):
        self.replies = dict(replies or {})
        self.default_reply = default_reply
        self.requests: list[APIRequest] = []

    async def process_single_request(self, request: APIRequest) -> APIOutput:
        self.requests.append(request)
        content = self.replies.get(request.custom_id, self.default_reply)
        return APIOutput(
            custom_id=request.custom_id,
            response=APIModelResponseOllama(
                body=ChatResponse(message=Message(role="assistant", content=content)),
                structured=False,
            ),
        )

    async def process_requests(self, requests):
        for request in requests:
            yield await self.process_single_request(request)


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
    """Replaces ``adapters.llm.responses.ResponsesChat``: yields ``deltas``, records calls.

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
