"""Model calls of the search benchmark (#712): retries, unusable replies and fatal errors."""
import contextlib
from types import SimpleNamespace

import httpx
import ollama
import openai
import pytest

from semant_demo.benchmarks.search_relevance import llm as benchmark_llm
from semant_demo.benchmarks.search_relevance.llm import InvalidReply, Refused, ask, is_fatal


class FakeLlm:
    """The parts of ``LlmGateway`` that ``ask`` uses; ``replies`` are returned or raised in turn."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0
        limits = SimpleNamespace(max_input_tokens=100, max_output_tokens=10)
        self.catalog = SimpleNamespace(policy=lambda feature: SimpleNamespace(limits=limits))

    def operation(self, feature):
        return contextlib.nullcontext()

    async def complete(self, feature, messages, context_size=None):
        self.calls += 1
        reply = self.replies[min(self.calls, len(self.replies)) - 1]
        if isinstance(reply, BaseException):
            raise reply
        return reply


def grade(reply: str) -> int:
    if reply not in ("0", "1", "2"):
        raise InvalidReply("not a grade")
    return int(reply)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(benchmark_llm, "BACKOFF", 0)


def http_error(cls, status: int):
    return cls("refused", response=httpx.Response(status, request=httpx.Request("POST", "http://m")), body=None)


async def test_a_usable_reply_is_returned_and_a_transient_failure_is_retried():
    llm = FakeLlm(http_error(openai.InternalServerError, 503), ConnectionError("reset"), "2")
    assert await ask(llm, "judge", [], grade) == (2, None) and llm.calls == 3


async def test_an_unusable_reply_is_retried_once_only():
    llm = FakeLlm("Grade: 2", "Grade: 2", "2")
    assert await ask(llm, "judge", [], grade) == (None, "invalid_output: not a grade") and llm.calls == 2


async def test_failed_calls_stop_after_the_attempts_with_the_class_as_reason():
    llm = FakeLlm(http_error(openai.RateLimitError, 429))
    assert await ask(llm, "judge", [], grade) == (None, "model_failed: RateLimitError")
    assert llm.calls == benchmark_llm.ATTEMPTS


@pytest.mark.parametrize("error", [
    http_error(openai.AuthenticationError, 401), http_error(openai.PermissionDeniedError, 403),
    http_error(openai.NotFoundError, 404), http_error(openai.BadRequestError, 400),
    ollama.ResponseError("model 'x' not found", 404)])
async def test_a_fatal_client_error_stops_the_step_at_the_first_call(error):
    llm = FakeLlm(error, "2")
    with pytest.raises(Refused, match=f"HTTP {error.status_code}"):
        await ask(llm, "judge", [], grade)
    assert llm.calls == 1


def test_rate_limits_timeouts_and_server_errors_are_not_fatal():
    assert not is_fatal(http_error(openai.RateLimitError, 429))
    assert not is_fatal(http_error(openai.InternalServerError, 500))
    assert not is_fatal(ConnectionError("reset")) and not is_fatal(TimeoutError())
    request = httpx.Request("POST", "http://m")
    assert is_fatal(httpx.HTTPStatusError("x", request=request, response=httpx.Response(402, request=request)))
