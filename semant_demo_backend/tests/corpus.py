"""The synthetic fixture corpus in ``tests/fixtures/corpus.json``.

The JSON file is the single source: integration tests, the browser-test server and the
Playwright suite all read it. Loading validates the cross-references and that every span's
``start``/``end`` select its ``quote``, so a corrupt fixture fails before it is seeded.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

CORPUS_PATH = Path(__file__).parent / "fixtures" / "corpus.json"


@dataclass(frozen=True)
class Corpus:
    raw: dict[str, Any]

    def _by_key(self, section: str) -> dict[str, dict[str, Any]]:
        return {item["key"]: item for item in self.raw[section]}

    @property
    def users(self) -> dict[str, dict[str, Any]]:
        return self._by_key("users")

    @property
    def collections(self) -> dict[str, dict[str, Any]]:
        return self._by_key("collections")

    @property
    def documents(self) -> dict[str, dict[str, Any]]:
        return self._by_key("documents")

    @property
    def chunks(self) -> dict[str, dict[str, Any]]:
        """All chunks by key, each with an added ``document`` key."""
        return {
            chunk["key"]: {**chunk, "document": doc["key"]}
            for doc in self.raw["documents"]
            for chunk in doc["chunks"]
        }

    @property
    def tags(self) -> dict[str, dict[str, Any]]:
        return self._by_key("tags")

    @property
    def spans(self) -> dict[str, dict[str, Any]]:
        return self._by_key("spans")

    @property
    def chunk_tags(self) -> list[dict[str, Any]]:
        return self.raw["chunk_tags"]


def _validate(corpus: Corpus) -> None:
    users, collections, chunks, tags = corpus.users, corpus.collections, corpus.chunks, corpus.tags
    ids = [item["id"] for section in ("users", "collections", "documents", "tags", "spans")
           for item in corpus.raw[section]] + [c["id"] for c in chunks.values()]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"
    for col in collections.values():
        assert col["owner"] in users
        assert all(u in users for u in col["shared_with"])
    for doc in corpus.documents.values():
        assert all(c in collections for c in doc["collections"])
        for chunk in doc["chunks"]:
            assert set(chunk["collections"]) <= set(doc["collections"]), chunk["key"]
    for tag in tags.values():
        assert tag["collection"] in collections
    for span in corpus.spans.values():
        text = chunks[span["chunk"]]["text"]
        assert span["tag"] in tags
        assert span["type"] in ("pos", "neg", "auto")
        assert text[span["start"]:span["end"]] == span["quote"], span["key"]
        # Offsets are code points; keep them equal to UTF-16 offsets (see corpus description).
        assert all(ord(ch) <= 0xFFFF for ch in text[:span["end"]]), span["key"]
    for entry in corpus.chunk_tags:
        assert entry["chunk"] in chunks
        for ref in ("positiveTag", "automaticTag", "negativeTag"):
            assert all(t in tags for t in entry[ref])
    # Chunk tags are exactly the projection of the spans (ADR 0004, #204).
    ref_of = {"pos": "positiveTag", "auto": "automaticTag", "neg": "negativeTag"}
    required = {(s["chunk"], s["tag"], ref_of[s["type"]]) for s in corpus.spans.values()}
    stored = {(e["chunk"], t, ref) for e in corpus.chunk_tags for ref in ref_of.values() for t in e[ref]}
    assert stored == required, "chunk_tags must match the spans"


@cache
def load_corpus(path: Path = CORPUS_PATH) -> Corpus:
    corpus = Corpus(json.loads(path.read_text(encoding="utf-8")))
    _validate(corpus)
    return corpus
