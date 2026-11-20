"""Document embeddings of the benchmark store: the input template and the on-disk cache.

**Template.** ``VectorSpec.document_template`` is a ``str.format`` template of a chunk's
``TEMPLATE_FIELDS``: ``{text}`` (the chunk text as stored) and ``{title}`` (the chunk's own
title; empty when it has none). The rendered text is embedded as is, without a document prefix
of the embedding client. The query prefix (``VectorSpec.query_prefix``) applies to queries only
and does not change document vectors.

**Cache.** Embeddings are cached in ``cache_dir`` by (model, dimensions, template) and the
SHA-256 of the rendered input, so recreating a store or adding a model never embeds a text twice.
One namespace per (model, dimensions, template): ``<namespace>.json`` describes it and
``<namespace>.jsonl`` holds ``{"sha256": ..., "embedding": [...]}`` lines, appended after each
embedded batch; a line cut off by an interrupted write is ignored when the cache is read.
"""
from __future__ import annotations

import hashlib
import json
import math
import string
from collections.abc import Mapping
from pathlib import Path

TEMPLATE_FIELDS = ("text", "title")


class TemplateError(ValueError):
    """A document template naming something other than ``TEMPLATE_FIELDS``."""


def check_template(template: str) -> None:
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as e:
        raise TemplateError(f"Invalid document template {template!r}: {e}") from None
    fields = {name for _, name, _, _ in parsed if name is not None}
    unknown = sorted(f for f in fields if f not in TEMPLATE_FIELDS)
    if "" in fields or unknown:
        raise TemplateError(f"Document template {template!r} may use only named fields "
                            f"{', '.join('{' + f + '}' for f in TEMPLATE_FIELDS)}")
    if "text" not in fields:
        raise TemplateError(f"Document template {template!r} does not use {{text}}")


def render(template: str, text: str, title: str | None) -> str:
    return template.format(text=text, title=title or "")


def input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def valid_embedding(embedding: object, dimensions: int | None) -> bool:
    """A non-empty list of finite numbers, of ``dimensions`` when given."""
    return (isinstance(embedding, list) and len(embedding) > 0
            and (dimensions is None or len(embedding) == dimensions)
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in embedding))


class EmbeddingCache:
    """The cached document embeddings of one (model, dimensions, template)."""

    def __init__(self, cache_dir: Path, model: str, template: str, dimensions: int | None):
        self.identity = {"model": model, "dimensions": dimensions, "document_template": template}
        self.namespace = hashlib.sha256(json.dumps(self.identity, sort_keys=True).encode()).hexdigest()[:32]
        self.directory = Path(cache_dir).expanduser()
        self.path = self.directory / f"{self.namespace}.jsonl"
        self._dimensions = dimensions
        self._entries: dict[str, list[float]] | None = None

    def _load(self) -> dict[str, list[float]]:
        if self._entries is None:
            self._entries = {}
            if self.path.is_file():
                with self.path.open(encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line)
                            key, embedding = record["sha256"], record["embedding"]
                        except (ValueError, KeyError, TypeError):
                            continue  # an interrupted append
                        if valid_embedding(embedding, self._dimensions):
                            self._entries[key] = embedding
        return self._entries

    def get(self, key: str) -> list[float] | None:
        return self._load().get(key)

    def __len__(self) -> int:
        return len(self._load())

    def put_many(self, embeddings: Mapping[str, list[float]]) -> None:
        """Add embeddings (input hash -> embedding) and append them to the file."""
        entries = self._load()
        new = {k: v for k, v in embeddings.items() if k not in entries}
        if not new:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        meta = self.directory / f"{self.namespace}.json"
        if not meta.exists():
            meta.write_text(json.dumps(self.identity, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        with self.path.open("a+b") as f:
            f.seek(0, 2)
            if f.tell():
                f.seek(-1, 2)
                if f.read(1) != b"\n":  # after an interrupted append: start a new line
                    f.write(b"\n")
        with self.path.open("a", encoding="utf-8") as f:
            f.write("".join(json.dumps({"sha256": k, "embedding": v}) + "\n" for k, v in new.items()))
            f.flush()
        entries.update(new)
