"""Deterministic offline stand-ins for external AI providers.

Fakes implement only what the code under test uses. They never open connections, so
fast tests stay offline and produce the same result on every run.
"""
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
