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
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    self.replies[entry["key"]] = entry["reply"]
        self.stats: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self._lock = asyncio.Lock()

    def key(self, messages: list[dict[str, str]]) -> str:
        return hashlib.sha256(to_json({"prompt_version": self.prompt_version, "model": self.identity,
                                       "messages": messages}).encode()).hexdigest()

    async def ask(self, messages: list[dict[str, str]], parse: Callable[[str], T]) -> tuple[T | None, str | None]:
        """``(parsed, None)`` or ``(None, reason)``; a cached usable reply makes no call."""
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
            return None, reason
        async with self._lock:
            self.replies[key] = raw[-1]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"key": key, "reply": raw[-1]}, ensure_ascii=False) + "\n")
        return value, None

    def report(self) -> dict[str, Any]:
        return {"asked": self.stats["asked"], "cached": self.stats["cached"], "failed": self.stats["failed"],
                "failure_reasons": dict(self.failures)}
