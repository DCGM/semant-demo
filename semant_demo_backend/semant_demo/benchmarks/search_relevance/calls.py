"""Model calls of the generator with an on-disk cache: a rerun makes no call it made before.

A call is keyed by the SHA-256 of its feature, prompt version, model identity (provider, model,
endpoint, tier) and messages. Only usable replies are cached (failures are retried by the next
run); each is appended to ``calls/<feature>.jsonl`` as it arrives, so an interrupted run keeps
them. The cache holds model replies about corpus text: it stays in the work directory, outside Git.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.benchmarks.search_relevance.contracts import to_json
from semant_demo.benchmarks.search_relevance.llm import InvalidReply, ask, model_provenance

T = TypeVar("T")
IDENTITY = ("feature", "tier", "provider", "model", "model_endpoint")


class CachedModel:
    """One feature's model with its prompt version, cache and statistics."""

    def __init__(self, llm: LlmGateway, feature: str, prompt_version: str, cache_dir: Path):
        self.llm, self.feature, self.prompt_version = llm, feature, prompt_version
        self.provenance = model_provenance(llm, feature)
        self.identity = {key: self.provenance.get(key) for key in IDENTITY}
        self.path = cache_dir / f"{feature}.jsonl"
        self.replies: dict[str, str] = {}
        if self.path.exists():
            broken = False
            content = self.path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:  # a line cut short by an interrupted run: called again
                    broken = True
                    continue
                self.replies[entry["key"]] = entry["reply"]
            if broken:  # rewritten without it, so the next reply is not appended to the cut line
                partial = self.path.with_name(self.path.name + ".tmp")
                partial.write_text("".join(json.dumps({"key": k, "reply": r}, ensure_ascii=False) + "\n"
                                           for k, r in self.replies.items()), encoding="utf-8")
                partial.replace(self.path)
            elif content and not content.endswith("\n"):  # a whole last line without its newline
                with self.path.open("a", encoding="utf-8") as f:
                    f.write("\n")
        self.stats: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self._lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Future[tuple[Any, str | None, str | None]]] = {}

    def key(self, messages: list[dict[str, str]]) -> str:
        return hashlib.sha256(to_json({"prompt_version": self.prompt_version, "model": self.identity,
                                       "messages": messages}).encode()).hexdigest()

    async def ask(self, messages: list[dict[str, str]], parse: Callable[[str], T]) -> tuple[T | None, str | None]:
        """``(parsed, None)`` or ``(None, reason)``; a cached usable reply makes no call, and an
        identical ask already in flight is awaited instead of asked again (counted as cached)."""
        key = self.key(messages)
        cached = self.replies.get(key)
        if cached is not None:
            try:
                value = parse(cached)
            except InvalidReply:
                pass  # a stricter parser now: ask again
            else:
                self.stats["cached"] += 1
                return value, None
        call = self._inflight.get(key)
        if call is None:
            call = asyncio.ensure_future(self._call(key, messages, parse))
            self._inflight[key] = call
            call.add_done_callback(lambda done: self._forget(key, done))
            value, _, reason = await call
            return value, reason
        _, reply, reason = await call
        if reply is None:
            return None, reason  # that call's failure is counted once; not cached, so asked again later
        self.stats["cached"] += 1
        return parse(reply), None

    def _forget(self, key: str, done: asyncio.Future) -> None:
        if self._inflight.get(key) is done:
            del self._inflight[key]

    async def _call(self, key: str, messages: list[dict[str, str]], parse: Callable[[str], T]
                    ) -> tuple[T | None, str | None, str | None]:
        """``(parsed, raw reply, None)`` or ``(None, None, reason)``; a usable reply is cached."""
        raw: list[str] = []

        def keep(reply: str) -> T:
            value = parse(reply)
            raw.append(reply)
            return value
        value, reason = await ask(self.llm, self.feature, messages, keep)
        self.stats["asked"] += 1
        if reason is not None:
            self.stats["failed"] += 1
            self.failures[reason] += 1
            return None, None, reason
        async with self._lock:
            self.replies[key] = raw[-1]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "reply": raw[-1]}, ensure_ascii=False) + "\n")
        return value, raw[-1], None

    def report(self) -> dict[str, Any]:
        return {"asked": self.stats["asked"], "cached": self.stats["cached"], "failed": self.stats["failed"],
                "failure_reasons": dict(self.failures)}
