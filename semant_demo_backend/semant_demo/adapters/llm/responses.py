"""Streaming text from an OpenAI-compatible Responses API endpoint (used by span chat)."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass(frozen=True)
class ResponsesChat:
    api_key: str
    base_url: str
    model: str
    temperature: float
    max_tokens: int
    key_setting: str = "SPAN_CHAT_API_KEY (or OPENAI_API_KEY)"
    """Named in the error when no key is configured."""

    async def stream(self, instructions: str, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        """Yield the reply's text deltas. ``messages`` are ``{"role", "content"}`` turns."""
        if not self.api_key:
            raise ValueError(f"{self.key_setting} is not configured on the server")

        async with AsyncOpenAI(api_key=self.api_key, base_url=self.base_url) as client:
            stream = await client.responses.create(
                model=self.model,
                instructions=instructions,
                input=messages,
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                stream=True,
            )
            async for event in stream:
                # Only incremental output text matters; other typed events
                # (response.created, response.completed, ...) are ignored.
                event_type = getattr(event, "type", None)
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        yield delta
                elif event_type == "response.error":
                    err = getattr(event, "error", None)
                    message = getattr(err, "message", None) or str(err) or "unknown error"
                    raise RuntimeError(f"Responses API error: {message}")
