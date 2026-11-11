"""Generate, on explicit request, short titles for text chunks and write only ``Chunks.title`` (#575).

Run after ``chunk_ingest`` and ``metadata_sync``: the prompt uses the title of the chunk's
document, and chunks of documents without one are deferred (below).

Check (read-only, no model calls)::

    python -m semant_demo.maintenance.chunk_titles --check --models-config MODELS.yaml [SELECTION]

Write::

    python -m semant_demo.maintenance.chunk_titles --write --confirm-endpoint HOST:PORT \\
        --models-config MODELS.yaml [SELECTION] [--limit N] [--after ID] [--report FILE] \\
        [--concurrency 8] [--tier TIER] [--allow-missing-document-title] [--regenerate]

The store is the state: a chunk with a non-empty ``title`` is done, an untitled one is
selected again by the next run. Nothing else is kept between runs: an interrupted run or a
failed chunk is taken up by running the command again (a few titles may be generated again).

Selection: without options, every chunk of the store without a title, whichever way it was
added (read in id order, pages of 100; only the id, title, language and document reference;
the title is checked here, not by a filter). ``--documents ID ...``, ``--documents-from FILE``
(one document UUID per line; ``#`` starts a comment), ``--chunks ID ...`` and ``--chunks-from
FILE`` (the same format) narrow it explicitly; they may be combined (the union of the
chunks), and are resolved to sorted chunk ids at the start of every run. On a store with
older untitled chunks (#87) the default covers them too: read its size from ``--check``.

Each selected chunk is planned as:

* ``has_title``: it has a non-empty title and is left as it is (unless ``--regenerate``,
  which needs an explicit selection);
* ``generate``: its title is generated from its text, its language and its document's title;
* ``deferred_no_document_title``: its document has no title yet (``metadata_sync`` has not
  run, or Kramerius has none); ``--allow-missing-document-title`` generates it without one;
* ``no_document``, ``missing_document``, ``several_documents``: reported, left as it is;
* ``absent``: an explicitly selected chunk id that does not exist.

``--limit N`` bounds the chunks planned ``generate`` in this run (the model calls of a write);
titled, deferred and reported chunks are passed over without counting. The run stops at the
first chunk beyond the limit and reports ``next_after``, the last chunk it examined: a later
run with ``--after`` that id continues from there, past chunks that keep failing; a run
without ``--after`` starts from the beginning and tries them again.

The model comes from ``--models-config``, a model tier catalog (the format of
``configs/llm_models.yaml``) that declares the ``chunk_titles`` feature, e.g.
``configs/chunk_titles_ollama.yaml`` or ``configs/chunk_titles_vllm.yaml``; the application's
catalog is not used unless given.
Calls go through the LLM gateway: the feature's limits cap the output and refuse an input
estimated above ``max_input_tokens`` before sending (``too_large``; never truncated), and
Ollama gets a context of ``max_input_tokens + max_output_tokens``. Both modes check first,
without a model call, that the catalog resolves the feature (and ``--tier``) and that the
tier's provider settings are present (``OPENAI_API_KEY``, ``GOOGLE_API_KEY``).

The prompt (``PROMPT_VERSION``) asks for a heading (a noun phrase, not a sentence) of at most
10 words in the excerpt's language, and ends by naming that language when the chunk's
``language`` is a single known code (``LANGUAGE_NAMES``). It does not alter a reply: a reply is
the answer alone (the provider separates a model's thinking: ``thinking`` of an Ollama tier, a
vLLM server's reasoning parser); it is cleaned (quotes around the whole title and markdown
removed) and refused as ``invalid_output`` when empty, on several lines, longer than
``MAX_TITLE_WORDS`` words or ``MAX_TITLE_CHARS`` characters; a model call is tried ``ATTEMPTS``
times (``model_failed``). Chunks with an empty text are ``empty_text``. Nothing but a valid
title is ever written.

Writing is a merge of ``title`` alone (text, order, positions, references, vectors and other
properties are kept) and every written page is read back (``write_failed`` when the stored
title differs). The schema is never changed: a store whose chunks do not declare ``title`` as
``text`` is refused.

The summary (printed as JSON, and written to ``--report FILE`` at the end of the run) holds the endpoint, the collections,
the mode, the selection, the options, the provenance of the run (prompt version and SHA-256,
feature, tier, provider, model, endpoint of the model, the catalog's path and SHA-256), the
times, ``complete`` and ``next_after``, the counts, the languages of the examined chunks (one
value, ``(mixed)`` or ``(unknown)``) and the model usage (calls, tokens, cost). With
``--report FILE``, the reported and failed chunks (id, status, reason, document ids; never text
or titles) are written as they occur, one JSON line each, to ``FILE`` with the suffix
``.chunks.jsonl``; the run keeps only their counts, so its memory does not grow with them. The
summary file is removed when a run starts, so a run that did not finish leaves none.

Exit code 0 only when the selection is complete: scanned to its end with nothing to generate
(check) or every selected chunk titled (write); 1 when the limit stopped the run or anything
was deferred, reported or failed; 2 when refused (missing collection or ``title`` property,
unconfirmed endpoint, unresolvable model catalog or missing provider setting).
Run while nothing else writes chunk titles.

The Weaviate endpoint comes from ``WEAVIATE_HOST`` / ``WEAVIATE_REST_PORT`` /
``WEAVIATE_GRPC_PORT``; provider endpoints and keys from ``OPENAI_API_URL``,
``OPENAI_API_KEY``, ``OLLAMA_URLS`` (first) and ``GOOGLE_API_KEY`` unless the tier sets
``base_url``.
"""
import argparse
import asyncio
import bisect
import hashlib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from weaviate import WeaviateAsyncClient

from semant_demo.adapters.llm.gateway import LlmGateway
from semant_demo.adapters.llm.models import LlmConfigurationError, Provider
from semant_demo.adapters.llm.usage import LlmInputTooLarge, LlmRequestRefused
from semant_demo.adapters.weaviate import chunk_titles as store
from semant_demo.adapters.weaviate.document_cleanup import resolve_collection
from semant_demo.adapters.weaviate.names import CollectionNames

FEATURE = "chunk_titles"
PROMPT_VERSION = "chunk-title-v1"
SYSTEM_PROMPT = (
    "You write headings for excerpts of larger historical documents (newspapers, books, letters, records). "
    "A heading names the main topic of the excerpt as a short noun phrase, like a newspaper or chapter "
    "heading: it is not a sentence and does not end with a full stop. Use at most 10 words. Describe only the "
    "provided excerpt, not the entire document. Write the heading in the language of the excerpt; never "
    "translate it into English or any other language. Respond only with the heading itself, without quotes, "
    "without markdown formatting and without any introductory or concluding phrases.\n\n"
    "Examples of headings:\n"
    "Požár obce v roce 1850\n"
    "Odsouzení obchodníka za podvod\n"
    "Anzeige einer Buchhandlung in Brünn\n"
    "Výroční schůze hasičského spolku")
DOCUMENT_BLOCK = "Original Document Title:\n{document_title}\n\n"
EXCERPT_BLOCK = "Excerpt Text:\n{text}\n\n"
LANGUAGE_BLOCK = "Write the heading in {language}."
"""The user message, in this order; the block of a missing document title is left out. The
instruction comes last, where a model weighs it most."""
LANGUAGE_NAMES = {"ces": "Czech", "slk": "Slovak", "deu": "German", "eng": "English", "pol": "Polish",
                  "fra": "French", "lat": "Latin", "ita": "Italian", "spa": "Spanish", "hun": "Hungarian",
                  "rus": "Russian", "ukr": "Ukrainian", "nld": "Dutch", "slv": "Slovenian", "hrv": "Croatian",
                  "srp": "Serbian", "bul": "Bulgarian", "dan": "Danish", "swe": "Swedish", "nor": "Norwegian"}
"""Languages named in the instruction. Another code (a rare language, or a wrong value such as
``yue`` for a Czech text) is not named: the instruction is the excerpt's own language."""
EXCERPT_LANGUAGE = "the language of the excerpt"

PAGE_SIZE = 100
"""Chunks examined per page."""
CONCURRENCY = 8
ATTEMPTS = 3
"""Tries of a store read or write, and of a model call (a failed or invalid reply)."""
BACKOFF = 2.0
QUERY_TIMEOUT = 600
MAX_TITLE_WORDS = 20
MAX_TITLE_CHARS = 200
MIXED, UNKNOWN = "(mixed)", "(unknown)"

PLANNED = ("has_title", "generate")
REPORTED = ("deferred_no_document_title", "no_document", "missing_document", "several_documents", "absent",
            "empty_text", "too_large")
"""Left as they are and reported; a later run plans them again."""
FAILED = ("model_failed", "invalid_output", "write_failed")
"""Left untitled and reported; a later run over them tries again."""
USAGE_KEYS = ("calls", "failed_calls", "input_tokens", "output_tokens", "cost_usd", "unknown_cost_calls")


class Refused(LookupError):
    """The run cannot start (or continue); nothing more is written."""


class InvalidTitle(ValueError):
    """A model reply that is not a usable title."""


# ---- prompt and output -------------------------------------------------------------------

def prompt_sha256() -> str:
    parts = (PROMPT_VERSION, SYSTEM_PROMPT, DOCUMENT_BLOCK, EXCERPT_BLOCK, LANGUAGE_BLOCK, EXCERPT_LANGUAGE,
             json.dumps(LANGUAGE_NAMES, sort_keys=True))
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def language_key(value: Any) -> str:
    """A chunk's language for the hint and the report: its single value, ``(mixed)`` or ``(unknown)``."""
    items = [value] if isinstance(value, str) else value if isinstance(value, (list, tuple)) else []
    values = sorted({item.strip() for item in items if isinstance(item, str) and item.strip()})
    return values[0] if len(values) == 1 else MIXED if values else UNKNOWN


def text_value(value: Any) -> str | None:
    """A stored text property, stripped; None when absent, empty or not text."""
    return value.strip() or None if isinstance(value, str) else None


def messages(text: str, language: str | None, document_title: str | None) -> list[dict[str, str]]:
    user = ((DOCUMENT_BLOCK.format(document_title=document_title) if document_title else "")
            + EXCERPT_BLOCK.format(text=text)
            + LANGUAGE_BLOCK.format(language=LANGUAGE_NAMES.get(language or "", EXCERPT_LANGUAGE)))
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


_QUOTE_PAIRS = {('"', '"'), ("'", "'"), ("`", "`"), ("„", "“"), ("„", "”"), ("“", "”"), ("”", "”"),
                ("«", "»"), ("»", "«"), ("‚", "‘"), ("‚", "’"), ("‘", "’")}
_EMPHASIS = ("**", "__", "*", "_")


def clean_title(reply: str) -> str:
    """The title in a model reply; raises ``InvalidTitle`` for a reply that is not one.

    The reply is the answer alone: a model's thinking, whose format differs between models, is
    separated by the provider (an Ollama tier's ``thinking``, a vLLM server's reasoning parser),
    never parsed here. Thinking left in the answer makes it invalid (several lines, too long)."""
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    if not lines:
        raise InvalidTitle("empty")
    if len(lines) > 1:
        raise InvalidTitle(f"{len(lines)} lines")
    title, previous = lines[0], None
    while title != previous:
        previous = title
        title = title.lstrip("#").strip()
        # Only emphasis around the whole title: **A** v **B** keeps its marks.
        for mark in _EMPHASIS:
            inner = title[len(mark):-len(mark)]
            if (len(title) > 2 * len(mark) and title.startswith(mark) and title.endswith(mark)
                    and mark not in inner):
                title = inner.strip()
        # Only quotes around the whole title: „A“ a „B“ keeps its quotes.
        if len(title) >= 2 and (title[0], title[-1]) in _QUOTE_PAIRS and not set(title[0] + title[-1]) & set(
                title[1:-1]):
            title = title[1:-1].strip()
    title = " ".join(title.split())
    if not title:
        raise InvalidTitle("empty")
    words = len(title.split())
    if words > MAX_TITLE_WORDS:
        raise InvalidTitle(f"{words} words")
    if len(title) > MAX_TITLE_CHARS:
        raise InvalidTitle(f"{len(title)} characters")
    return title


# ---- selection and output ------------------------------------------------------------------

@dataclass(frozen=True)
class Selection:
    """Explicitly selected documents and chunks; ``explicit`` False selects every untitled chunk."""
    explicit: bool = False
    documents: tuple[UUID, ...] = ()
    chunks: tuple[UUID, ...] = ()

    def identity(self) -> dict[str, Any]:
        if not self.explicit:
            return {"kind": "untitled"}
        documents, chunks = sorted(set(self.documents)), sorted(set(self.chunks))
        digest = hashlib.sha256(("documents:" + ",".join(map(str, documents)) + ";chunks:"
                                 + ",".join(map(str, chunks))).encode()).hexdigest()
        return {"kind": "explicit", "documents": len(documents), "chunks": len(chunks), "sha256": digest}


def read_id_file(path: Path) -> list[UUID]:
    """The ids of a text file with one UUID per line (``#`` starts a comment)."""
    ids = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if line:
            try:
                ids.append(UUID(line))
            except ValueError:
                raise Refused(f"{path}:{number}: not a UUID") from None
    return ids


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _progress(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


# ---- planning ------------------------------------------------------------------------------

def plan(chunk: store.ChunkState, document_titles: dict[UUID, Any], *, regenerate: bool = False,
         allow_missing_document_title: bool = False) -> tuple[str, str | None]:
    """The chunk's action and the document title to prompt with."""
    if text_value(chunk.title) is not None and not regenerate:
        return "has_title", None
    if not chunk.document_ids:
        return "no_document", None
    if len(chunk.document_ids) > 1:
        return "several_documents", None
    document = chunk.document_ids[0]
    if document not in document_titles:
        return "missing_document", None
    title = text_value(document_titles[document])
    if title is None and not allow_missing_document_title:
        return "deferred_no_document_title", None
    return "generate", title


class UsageTotals:
    """Model usage of this process, recorded by the gateway (``LlmMetrics``)."""

    def __init__(self) -> None:
        self.totals: dict[str, float] = {key: 0 for key in USAGE_KEYS}

    def record_llm_call(self, *, attributes: dict[str, str], outcome: str, duration_seconds: float,
                        input_tokens: int | None, output_tokens: int | None, cost_usd: float | None) -> None:
        self.totals["calls"] += 1
        self.totals["failed_calls"] += outcome != "success"
        self.totals["input_tokens"] += input_tokens or 0
        self.totals["output_tokens"] += output_tokens or 0
        if cost_usd is None:
            self.totals["unknown_cost_calls"] += 1
        else:
            self.totals["cost_usd"] += cost_usd


def provenance(llm: LlmGateway, tier: str | None, models_config: Path) -> dict[str, Any]:
    """What produced the titles of a run; raises ``Refused`` when the catalog cannot serve the
    feature or a provider setting is missing (no model call)."""
    try:
        model = llm.tier_model(FEATURE, tier)
        missing = llm.missing_setting(FEATURE, tier)
        limits = llm.catalog.policy(FEATURE).limits
    except LlmConfigurationError as e:
        raise Refused(f"{models_config}: {e}") from None
    if missing:
        raise Refused(f"{missing} is not set; the {model.tier} tier ({model.provider}) of {models_config} needs it")
    endpoint = model.base_url or {Provider.openai: llm.providers.openai_base_url,
                                  Provider.ollama: llm.providers.ollama_base_url}.get(model.provider)
    return {"prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_sha256(), "feature": FEATURE,
            "tier": str(model.tier), "provider": str(model.provider), "model": model.model,
            "model_endpoint": endpoint, "max_input_tokens": limits.max_input_tokens,
            "max_output_tokens": limits.max_output_tokens, "models_config": str(models_config.resolve()),
            "models_config_sha256": hashlib.sha256(models_config.read_bytes()).hexdigest()}


async def _retrying(call):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return await call()
        except Exception:
            if attempt == ATTEMPTS:
                raise
            await asyncio.sleep(BACKOFF * attempt)


async def _gather(items, concurrency: int, call) -> list:
    """``call`` for every item, at most ``concurrency`` at a time. When one raises (a refused
    model call stops the run), the others are cancelled before the error propagates."""
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            return await call(item)
    tasks = [asyncio.ensure_future(one(item)) for item in items]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def generate_title(llm: LlmGateway, prompt: list[dict[str, str]], *, tier: str | None = None,
                         context_size: int | None = None) -> tuple[str, str | None]:
    """``("generated", title)``, or a failure status (``too_large``, ``model_failed``,
    ``invalid_output``) and its reason. Raises ``Refused`` when the gateway refuses the feature
    (e.g. a missing setting), which stops the run."""
    reason = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            async with llm.operation(FEATURE):
                reply = await llm.complete(FEATURE, prompt, tier=tier, context_size=context_size)
        except LlmInputTooLarge:
            return "too_large", "input above the feature's max_input_tokens"
        except LlmRequestRefused as e:
            raise Refused(f"The model call was refused: {type(e).__name__}") from None
        except Exception as e:  # the provider's message may hold the prompt: report the class only
            status, reason = "model_failed", type(e).__name__
        else:
            try:
                return "generated", clean_title(reply)
            except InvalidTitle as e:
                status, reason = "invalid_output", str(e)
        if attempt < ATTEMPTS:
            await asyncio.sleep(BACKOFF * attempt)
    return status, reason


# ---- the run -------------------------------------------------------------------------------

def _counts() -> dict[str, int]:
    return {"examined": 0, **{key: 0 for key in (*PLANNED, *REPORTED, *FAILED)}, "written": 0}


class _Run:
    def __init__(self, client: WeaviateAsyncClient, llm: LlmGateway, *, chunks: str, documents: str,
                 with_language: bool, with_document_title: bool, write: bool, tier: str | None, concurrency: int,
                 regenerate: bool, allow_missing_document_title: bool, limit: int | None,
                 reported: Callable[[dict[str, Any]], None]):
        self.client, self.llm, self.chunks, self.documents = client, llm, chunks, documents
        self.with_language, self.with_document_title = with_language, with_document_title
        self.write, self.tier, self.concurrency, self.limit = write, tier, concurrency, limit
        self.regenerate, self.allow_missing_document_title = regenerate, allow_missing_document_title
        self.counts = _counts()
        self.languages: dict[str, int] = {}
        self.reported = reported
        self.taken = 0
        self.last: UUID | None = None
        self.document_titles: dict[UUID, Any] = {}
        self.missing_documents: set[UUID] = set()
        limits = llm.catalog.policy(FEATURE).limits
        self.context_size = limits.max_input_tokens + limits.max_output_tokens

    def report(self, chunk_id: UUID, status: str, reason: str | None = None, documents: tuple[UUID, ...] = ()) -> None:
        self.counts[status] += 1
        self.reported({"id": str(chunk_id), "status": status, **({"reason": reason} if reason else {}),
                       **({"document_ids": [str(i) for i in documents]} if documents else {})})

    async def titles_of(self, chunks: list[store.ChunkState]) -> dict[UUID, Any]:
        """The titles of the documents of the chunks that may get a title (untitled, or all with
        ``--regenerate``); a document found missing is not queried again in this run."""
        wanted = sorted({c.document_ids[0] for c in chunks if len(c.document_ids) == 1
                         and (self.regenerate or text_value(c.title) is None)}
                        - set(self.document_titles) - self.missing_documents)
        if wanted:
            found = await _retrying(lambda: store.read_document_titles(
                self.client, self.documents, wanted, self.with_document_title))
            self.document_titles.update(found)
            self.missing_documents.update(set(wanted) - set(found))
        return self.document_titles

    async def generate(self, chunks: list[tuple[store.ChunkState, str | None]]) -> dict[UUID, str]:
        """Titles generated for the planned chunks; the chunks that got none are reported."""
        ids = [chunk.id for chunk, _ in chunks]
        texts = await _retrying(lambda: store.read_texts(self.client, self.chunks, ids))
        titles: dict[UUID, str] = {}

        async def one(item: tuple[store.ChunkState, str | None]) -> None:
            chunk, document_title = item
            text = text_value(texts.get(chunk.id))
            if text is None:
                self.report(chunk.id, "absent" if chunk.id not in texts else "empty_text")
                return
            language = language_key(chunk.language)
            hint = None if language in (MIXED, UNKNOWN) else language
            status, value = await generate_title(self.llm, messages(text, hint, document_title), tier=self.tier,
                                                 context_size=self.context_size)
            if status == "generated":
                titles[chunk.id] = value
            else:
                self.report(chunk.id, status, value)
        await _gather(chunks, self.concurrency, one)
        return titles

    async def store_titles(self, titles: dict[UUID, str]) -> None:
        """Write the titles and read them back; a title not stored is ``write_failed``."""
        if not titles:
            return
        errors: dict[UUID, str] = {}

        async def write(chunk_id: UUID) -> None:
            try:
                await _retrying(lambda: store.set_chunk_title(self.client, self.chunks, chunk_id, titles[chunk_id]))
            except Exception as e:  # the write may or may not have happened; the read back decides
                errors[chunk_id] = f"{type(e).__name__}: {e}"
        await _gather(sorted(titles), self.concurrency, write)
        try:
            stored = await _retrying(lambda: store.read_chunks(self.client, self.chunks, list(titles), False))
        except Exception as e:
            stored = {}
            errors.update({i: f"read back failed: {type(e).__name__}: {e}" for i in titles if i not in errors})
        for chunk_id in sorted(titles):
            if chunk_id in stored and stored[chunk_id].title == titles[chunk_id]:
                self.counts["written"] += 1
            else:
                self.report(chunk_id, "write_failed", errors.get(chunk_id) or (
                    "the stored title differs on read back" if chunk_id in stored else "absent on read back"))

    async def page(self, items: list[tuple[UUID, store.ChunkState | None]]) -> bool:
        """Plan the chunks in id order and, when writing, title the planned ones; False when the
        limit stopped the page before its end (``last`` is then the last chunk examined)."""
        titles = await self.titles_of([chunk for _, chunk in items if chunk is not None])
        planned: list[tuple[store.ChunkState, str | None]] = []
        whole = True
        for chunk_id, chunk in items:
            if chunk is None:
                action, document_title = "absent", None
            else:
                action, document_title = plan(chunk, titles, regenerate=self.regenerate,
                                              allow_missing_document_title=self.allow_missing_document_title)
            if action == "generate":
                if self.limit is not None and self.taken >= self.limit:
                    whole = False
                    break
                self.taken += 1
            self.last = chunk_id
            self.counts["examined"] += 1
            if chunk is not None:
                key = language_key(chunk.language)
                self.languages[key] = self.languages.get(key, 0) + 1
            if action in REPORTED:
                self.report(chunk_id, action, documents=chunk.document_ids if chunk else ())
            else:
                self.counts[action] += 1
                if action == "generate" and self.write:
                    planned.append((chunk, document_title))
        if planned:
            await self.store_titles(await self.generate(planned))
        return whole


async def run(client: WeaviateAsyncClient, names: CollectionNames, llm: LlmGateway, *, endpoint: str, write: bool,
              models_config: Path, selection: Selection = Selection(), tier: str | None = None,
              regenerate: bool = False, allow_missing_document_title: bool = False, limit: int | None = None,
              after: UUID | None = None, concurrency: int = CONCURRENCY, usage: UsageTotals | None = None,
              progress: Callable[[str], None] = _progress,
              reported: Callable[[dict[str, Any]], None] = lambda line: None) -> dict[str, Any]:
    """One pass over the selection (see the module docstring); returns the summary. Each reported
    or failed chunk is passed to ``reported`` when it occurs, and only counted here. Raises ``Refused`` before writing when a
    collection or ``Chunks.title`` is missing, the model catalog cannot serve the feature or
    ``--regenerate`` lacks an explicit selection."""
    if regenerate and not selection.explicit:
        raise Refused("--regenerate needs an explicit selection (--documents, --chunks or their files)")
    chunks = await resolve_collection(client, names.chunks_collection_name)
    documents = await resolve_collection(client, names.document_collection_name)
    for name in (chunks, documents):
        if not await client.collections.exists(name):
            raise Refused(f"Collection {name} does not exist")
    chunk_types = await store.declared_types(client, chunks)
    if chunk_types.get(store.TITLE) != "text":
        declared = f"declared as {chunk_types[store.TITLE]}" if store.TITLE in chunk_types else "not declared"
        raise Refused(f"{chunks}.{store.TITLE} is {declared}; this command never changes the schema: "
                      "declare it as text through the schema process (#128)")
    document_types = await store.declared_types(client, documents)
    origin = provenance(llm, tier, models_config)

    summary: dict[str, Any] = {
        "endpoint": endpoint, "chunks": chunks, "documents": documents, "mode": "write" if write else "check",
        "selection": selection.identity(), "regenerate": regenerate,
        "allow_missing_document_title": allow_missing_document_title, "limit": limit,
        "after": str(after) if after else None, "provenance": origin, "started": _now()}
    work = _Run(client, llm, chunks=chunks, documents=documents,
                with_language=chunk_types.get(store.LANGUAGE) in ("text", "text[]"),
                with_document_title=document_types.get(store.TITLE) == "text", write=write, tier=tier,
                concurrency=concurrency, regenerate=regenerate,
                allow_missing_document_title=allow_missing_document_title, limit=limit, reported=reported)
    selected = None
    if selection.explicit:
        selected = await _resolve(client, chunks, selection, concurrency)
        progress(f"Selected {len(selected)} chunks")
    started, cursor, complete = time.monotonic(), after, False
    while True:
        if selected is None:
            page = await _retrying(lambda: store.read_chunk_page(client, chunks, cursor, PAGE_SIZE, work.with_language))
            items = [(chunk.id, chunk) for chunk in page]
            end = len(page) < PAGE_SIZE
        else:
            start = 0 if cursor is None else bisect.bisect_right(selected, cursor)
            ids = selected[start:start + PAGE_SIZE]
            stored = await _retrying(lambda: store.read_chunks(client, chunks, ids, work.with_language))
            items = [(i, stored.get(i)) for i in ids]
            end = start + PAGE_SIZE >= len(selected)
        whole = await work.page(items)
        cursor = work.last
        counts, seconds = work.counts, max(time.monotonic() - started, 1e-3)
        progress(f"examined {counts['examined']} " + " ".join(
            f"{key} {counts[key]}" for key in (*PLANNED, *REPORTED, *FAILED, "written") if counts[key])
            + f" after {cursor} ({counts['examined'] / seconds:.1f}/s)")
        if not whole:
            break
        if end:
            complete = True
            break

    if usage is not None:
        summary["usage"] = dict(usage.totals)
    return summary | {
        "finished": _now(), "complete": complete, "next_after": None if complete else str(cursor) if cursor else None,
        "counts": work.counts, "languages": work.languages,
        "reported": sum(work.counts[key] for key in (*REPORTED, *FAILED))}


async def _resolve(client: WeaviateAsyncClient, chunks: str, selection: Selection, concurrency: int) -> list[UUID]:
    """The sorted chunk ids of an explicit selection."""
    async def of(document: UUID) -> list[UUID]:
        return await _retrying(lambda: store.document_chunk_ids(client, chunks, document))
    ids = set(selection.chunks)
    for found in await _gather(sorted(set(selection.documents)), concurrency, of):
        ids.update(found)
    return sorted(ids)


def exit_code(result: dict[str, Any]) -> int:
    """0 only for a complete selection: scanned to its end with nothing to generate (check),
    deferred, reported or failed."""
    counts = result["counts"]
    if not result["complete"] or any(counts[key] for key in (*REPORTED, *FAILED)):
        return 1
    if result["mode"] == "check" and counts["generate"]:
        return 1
    return 0


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, not {number}")
    return number


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="plan the selection without model calls or writes")
    mode.add_argument("--write", action="store_true", help="generate and write the titles")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--models-config", type=Path, required=True, metavar="MODELS.yaml",
                   help="model tier catalog declaring the chunk_titles feature")
    p.add_argument("--tier", help="a tier the feature allows (default: the feature's default)")
    p.add_argument("--documents", type=UUID, nargs="+", default=[], metavar="ID", help="select these documents' chunks")
    p.add_argument("--documents-from", type=Path, metavar="FILE", help="select the chunks of the documents listed")
    p.add_argument("--chunks", type=UUID, nargs="+", default=[], metavar="ID", help="select these chunks")
    p.add_argument("--chunks-from", type=Path, metavar="FILE", help="select the chunks listed")
    p.add_argument("--regenerate", action="store_true", help="also replace existing titles (explicit selection only)")
    p.add_argument("--allow-missing-document-title", action="store_true",
                   help="generate titles of chunks whose document has no title, without it")
    p.add_argument("--limit", type=_positive, help="at most this many chunks to title in this run")
    p.add_argument("--after", type=UUID, metavar="ID",
                   help="start after this chunk id (the next_after of an earlier run)")
    p.add_argument("--report", type=Path, metavar="FILE",
                   help="also write the summary to this JSON file, and the reported and failed chunks "
                        "to FILE with the suffix .chunks.jsonl (one JSON line each, written as they occur)")
    p.add_argument("--concurrency", type=_positive, default=CONCURRENCY, help=f"parallel model calls and writes "
                                                                         f"(default {CONCURRENCY})")
    return p


def chunks_report(summary: Path) -> Path:
    """The JSON Lines file of the reported and failed chunks next to the summary ``--report FILE``."""
    return summary.with_suffix(".chunks.jsonl")


def selection_from(args: argparse.Namespace) -> Selection:
    documents = [*args.documents, *(read_id_file(args.documents_from) if args.documents_from else [])]
    chunks = [*args.chunks, *(read_id_file(args.chunks_from) if args.chunks_from else [])]
    explicit = bool(args.documents or args.documents_from or args.chunks or args.chunks_from)
    return Selection(explicit, tuple(documents), tuple(chunks))


async def _main(argv: list[str]) -> int:
    from semant_demo.adapters.llm.gateway import ProviderSettings
    from semant_demo.adapters.llm.models import ModelCatalog
    from semant_demo.adapters.weaviate.client import connect_weaviate
    from semant_demo.config import Config

    args = _parser().parse_args(argv)
    config = Config()
    endpoint = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_REST_PORT}"
    if args.write and args.confirm_endpoint != endpoint:
        print(f"Refusing to write: configured endpoint {endpoint}, --confirm-endpoint {args.confirm_endpoint}",
              file=sys.stderr)
        return 2
    try:
        selection = selection_from(args)
        catalog = ModelCatalog.load(args.models_config)
    except (Refused, LlmConfigurationError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    lines = None
    if args.report:
        try:
            args.report.unlink(missing_ok=True)
            lines = chunks_report(args.report).open("w", encoding="utf-8")
        except OSError as e:
            print(e, file=sys.stderr)
            return 2
    usage = UsageTotals()
    llm = LlmGateway(catalog, ProviderSettings.from_config(config), usage)
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = None
    try:
        client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
        result = await run(client, config.collectionNames, llm, endpoint=endpoint, write=args.write,
                           models_config=args.models_config, selection=selection, tier=args.tier,
                           regenerate=args.regenerate, allow_missing_document_title=args.allow_missing_document_title,
                           limit=args.limit, after=args.after, concurrency=args.concurrency, usage=usage,
                           reported=(lambda line: lines.write(json.dumps(line) + "\n")) if lines else lambda line: None)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        if lines:
            lines.close()
        if client is not None:
            await client.close()
    if args.report:
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
