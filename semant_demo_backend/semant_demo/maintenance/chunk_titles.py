"""Generate, on explicit request, short titles for text chunks and write only ``Chunks.title`` (#575).

Run after ``chunk_ingest`` and ``metadata_sync``: the prompt uses the title of the chunk's
document, and chunks of documents without one are deferred (below).

Check (read-only, no model calls)::

    python -m semant_demo.maintenance.chunk_titles --check check.json --models-config MODELS.yaml [SELECTION]

Write::

    python -m semant_demo.maintenance.chunk_titles --write write.json --confirm-endpoint HOST:PORT \\
        --models-config MODELS.yaml [SELECTION] [--concurrency 8] [--limit N] [--tier TIER] \\
        [--allow-missing-document-title] [--regenerate]

Selection: without options, every chunk of the store without a title (read in id order,
pages of 100; only the id, title, language and document reference). ``--documents ID ...``,
``--documents-from FILE`` (one document UUID per line; ``#`` starts a comment),
``--chunks ID ...`` and ``--chunks-from FILE`` (the same text format, or a ``.uuids`` file of
an earlier run, below) select explicitly; they may be combined (the union of the chunks).
An explicit selection is resolved to its sorted chunk ids at the start of every run. The
default needs no document list after an import and also finds chunks added by other means; on
a store with older untitled chunks (#87) it covers them too, so read its size from ``--check``
and bound a run with ``--limit``.

Each selected chunk is planned as:

* ``has_title``: it has a non-empty title and is left as it is (unless ``--regenerate``,
  which needs an explicit selection);
* ``generate``: its title is generated from its text, its language and its document's title;
* ``deferred_no_document_title``: its document has no title yet (``metadata_sync`` has not
  run, or Kramerius has none); ``--allow-missing-document-title`` generates it without one;
* ``no_document``, ``missing_document``, ``several_documents``: reported, left as it is;
* ``absent``: an explicitly selected chunk id that does not exist.

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
removed) and refused as ``invalid_output`` when empty, on several lines, longer than ``MAX_TITLE_WORDS`` words or
``MAX_TITLE_CHARS`` characters; a model call is tried ``ATTEMPTS`` times (``model_failed``).
Chunks with an empty text are ``empty_text``. Nothing but a valid title is ever written.

Writing is a merge of ``title`` alone (text, order, positions, references, vectors and other
properties are kept) and every written page is read back. The schema is never changed: a
store whose chunks do not declare ``title`` as ``text`` is refused.

The checkpoint (JSON, replaced atomically) holds the endpoint, the collections, the mode, the
selection (its size and SHA-256), the options, the provenance of the run (prompt version and
SHA-256, feature, tier, provider, model, endpoint of the model, the catalog's path and SHA-256),
the cursor, the counts, the languages of the examined chunks (one value, ``(mixed)`` or
``(unknown)``), the model usage (calls, tokens, cost) and the ids to retry (failed generation,
invalid output, failed write), which a rerun retries first, each once per run (one that fails
again is left for the next run; a failed write is retried with its recorded title, unless the
chunk was deleted or titled by another writer since). The manifest lines of a page are saved in
the checkpoint before they are appended, so an interruption neither loses nor repeats one. Generated
titles are recorded in the checkpoint before they are written, so an interrupted or failed write
is completed on resume without new model calls. A finished checkpoint is refused, as is one of another endpoint, collection,
mode, selection, option set or provenance: a new run needs a new file name. Every reported
chunk gets a line in ``CHECKPOINT.manifest.jsonl`` (its id, status and reason; never text or
titles).

``CHECKPOINT.titled.uuids`` lists the ids of the chunks whose title this run wrote and read
back: raw 16-byte UUIDs, appended after each verified page (a partial last record left by an
interruption is dropped). Read it with ``read_uuids`` or
``numpy.fromfile(path, dtype="V16")``; it is accepted by ``--chunks-from`` (with
``--regenerate`` to redo one run's titles). The checkpoint gives the provenance of every id in it.

Exit code 0 only when the selection is complete: a check with nothing to generate, or a write
with every selected chunk titled; 1 when anything is to generate (check), deferred, reported
or left to retry; 2 when refused (missing collection or ``title`` property, unconfirmed
endpoint, unresolvable model catalog or missing provider setting, a checkpoint of another run).
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
import os
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
"""Chunks examined per page; the cursor is saved after each page."""
CONCURRENCY = 8
ATTEMPTS = 3
"""Tries of a store read or write, and of a model call (a failed or invalid reply)."""
BACKOFF = 2.0
QUERY_TIMEOUT = 600
MAX_TITLE_WORDS = 20
MAX_TITLE_CHARS = 200
UUID_BYTES = 16
MIXED, UNKNOWN = "(mixed)", "(unknown)"

PLANNED = ("has_title", "generate")
REPORTED = ("deferred_no_document_title", "no_document", "missing_document", "several_documents", "absent",
            "empty_text", "too_large")
"""Left as they are and listed in the manifest; a later run plans them again."""
RETRIED = ("model_failed", "invalid_output", "write_failed")
"""Kept in the checkpoint and retried first when the same command runs again."""
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


# ---- selection and files -------------------------------------------------------------------

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


def titled_path(checkpoint: Path) -> Path:
    return checkpoint.with_name(checkpoint.name + ".titled.uuids")


def manifest_path(checkpoint: Path) -> Path:
    return checkpoint.with_name(checkpoint.name + ".manifest.jsonl")


def read_uuids(path: Path) -> list[UUID]:
    """The ids of a ``.uuids`` file (raw 16-byte UUIDs); a partial last record is ignored."""
    data = path.read_bytes()
    return [UUID(bytes=data[i:i + UUID_BYTES]) for i in range(0, len(data) - len(data) % UUID_BYTES, UUID_BYTES)]


def read_id_file(path: Path) -> list[UUID]:
    """The ids of a ``.uuids`` file, or of a text file with one UUID per line (``#`` comments)."""
    if path.suffix == ".uuids":
        return read_uuids(path)
    ids = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if line:
            try:
                ids.append(UUID(line))
            except ValueError:
                raise Refused(f"{path}:{number}: not a UUID") from None
    return ids


def _repair_uuids(path: Path) -> None:
    """Drop a partial last record left by an interrupted append."""
    if path.exists():
        size = path.stat().st_size
        if size % UUID_BYTES:
            with path.open("r+b") as file:
                file.truncate(size - size % UUID_BYTES)


def _uuids_tail(path: Path, records: int) -> set[UUID]:
    if not path.exists() or records <= 0:
        return set()
    with path.open("rb") as file:
        file.seek(max(0, path.stat().st_size - records * UUID_BYTES))
        data = file.read()
    return {UUID(bytes=data[i:i + UUID_BYTES]) for i in range(0, len(data) - len(data) % UUID_BYTES, UUID_BYTES)}


def _append_uuids(path: Path, ids: list[UUID]) -> None:
    if ids:
        with path.open("ab") as file:
            file.write(b"".join(i.bytes for i in ids))
            file.flush()
            os.fsync(file.fileno())


def _write_json(path: Path, data: Any) -> None:
    """Replace the file atomically, so a crash leaves the previous checkpoint."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


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
    return {"examined": 0, **{key: 0 for key in (*PLANNED, *REPORTED, *RETRIED)}, "written": 0}


class _Run:
    def __init__(self, client: WeaviateAsyncClient, llm: LlmGateway, state: dict[str, Any], checkpoint: Path, *,
                 chunks: str, documents: str, with_language: bool, with_document_title: bool, write: bool,
                 tier: str | None, concurrency: int, usage: UsageTotals | None, progress: Callable[[str], None]):
        self.client, self.llm, self.state, self.checkpoint = client, llm, state, checkpoint
        self.chunks, self.documents = chunks, documents
        self.with_language, self.with_document_title = with_language, with_document_title
        self.write, self.tier, self.concurrency, self.progress = write, tier, concurrency, progress
        self.usage, self.usage_base = usage, dict(state["usage"])
        self.counts: dict[str, int] = state["counts"]
        self.document_titles: dict[UUID, Any] = {}
        self.missing_documents: set[UUID] = set()
        limits = llm.catalog.policy(FEATURE).limits
        self.context_size = limits.max_input_tokens + limits.max_output_tokens
        self.manifest, self.titled = manifest_path(checkpoint), titled_path(checkpoint)

    def save(self) -> None:
        if self.usage is not None:
            self.state["usage"] = {key: self.usage_base[key] + self.usage.totals[key] for key in USAGE_KEYS}
        self.state["updated"] = _now()
        _write_json(self.checkpoint, self.state)

    def log(self, lines: list[dict[str, Any]]) -> None:
        """Save the checkpoint with these manifest lines, then append them: an interruption
        neither loses nor repeats a line (``append_manifest`` completes it on resume)."""
        self.state["manifest_lines"] = lines
        self.save()
        self.append_manifest()

    def append_manifest(self) -> None:
        """Append the checkpoint's pending manifest lines after the size it recorded, dropping
        lines appended before an interruption that the checkpoint did not record."""
        lines, size = self.state["manifest_lines"], self.state["manifest_size"]
        if self.manifest.exists() and self.manifest.stat().st_size > size:
            with self.manifest.open("r+b") as file:
                file.truncate(size)
        if lines:
            with self.manifest.open("ab") as file:
                file.write("".join(json.dumps(line) + "\n" for line in lines).encode("utf-8"))
                size = file.tell()
        self.state["manifest_size"], self.state["manifest_lines"] = size, []

    async def titles_of(self, chunks: list[store.ChunkState]) -> dict[UUID, Any]:
        """The titles of the documents of the chunks that may get a title (untitled, or all with
        ``--regenerate``); a document found missing is not queried again in this run."""
        regenerate = self.state["regenerate"]
        wanted = sorted({c.document_ids[0] for c in chunks if len(c.document_ids) == 1
                         and (regenerate or text_value(c.title) is None)}
                        - set(self.document_titles) - self.missing_documents)
        if wanted:
            found = await _retrying(lambda: store.read_document_titles(
                self.client, self.documents, wanted, self.with_document_title))
            self.document_titles.update(found)
            self.missing_documents.update(set(wanted) - set(found))
        return self.document_titles

    async def generate(self, chunks: list[tuple[store.ChunkState, str | None]]) -> tuple[dict[UUID, str], list]:
        """Titles generated for the planned chunks, and the chunks that got none with their status and reason."""
        ids = [chunk.id for chunk, _ in chunks]
        texts = await _retrying(lambda: store.read_texts(self.client, self.chunks, ids))
        titles: dict[UUID, str] = {}
        failures: list[tuple[store.ChunkState, str, str | None]] = []

        async def one(item: tuple[store.ChunkState, str | None]) -> None:
            chunk, document_title = item
            text = text_value(texts.get(chunk.id))
            if text is None:
                failures.append((chunk, "absent" if chunk.id not in texts else "empty_text", None))
                return
            language = language_key(chunk.language)
            hint = None if language in (MIXED, UNKNOWN) else language
            status, value = await generate_title(self.llm, messages(text, hint, document_title), tier=self.tier,
                                                 context_size=self.context_size)
            if status == "generated":
                titles[chunk.id] = value
            else:
                failures.append((chunk, status, value))
        await _gather(chunks, self.concurrency, one)
        return titles, failures

    def record_failures(self, failures: list) -> list[dict[str, Any]]:
        lines = []
        for chunk, status, reason in failures:
            self.counts[status] += 1
            if status in RETRIED:
                self.state["retry"][str(chunk.id)] = status
            lines.append({"id": str(chunk.id), "status": status, **({"reason": reason} if reason else {})})
        return lines

    async def flush(self) -> None:
        """Write the titles recorded in the checkpoint, read them back and record the verified ones."""
        titles = {UUID(i): t for i, t in self.state["in_flight"].items()}
        if not titles:
            return
        errors: dict[UUID, str] = {}

        async def write(chunk_id: UUID) -> None:
            try:
                await _retrying(lambda: store.set_chunk_title(self.client, self.chunks, chunk_id, titles[chunk_id]))
            except Exception as e:  # the write may or may not have happened; the read back decides
                errors[chunk_id] = f"{type(e).__name__}: {e}"
        await _gather(list(titles), self.concurrency, write)
        try:
            stored = await _retrying(lambda: store.read_chunks(self.client, self.chunks, list(titles), False))
        except Exception as e:
            stored = {}
            errors.update({i: f"read back failed: {type(e).__name__}: {e}" for i in titles if i not in errors})
        verified = []
        for chunk_id, title in titles.items():
            if stored.get(chunk_id) is not None and stored[chunk_id].title == title:
                verified.append(chunk_id)
                errors.pop(chunk_id, None)
            elif chunk_id not in errors:
                errors[chunk_id] = "the stored title differs on read back" if chunk_id in stored else "absent on read back"
        # Ids appended before an interruption (the last records) are not appended again.
        recorded = _uuids_tail(self.titled, len(titles))
        _append_uuids(self.titled, sorted(i for i in verified if i not in recorded))
        self.counts["written"] += len(verified)
        lines = []
        for chunk_id, reason in sorted(errors.items()):
            self.counts["write_failed"] += 1
            self.state["retry"][str(chunk_id)] = "write_failed"
            self.state["unwritten"][str(chunk_id)] = titles[chunk_id]   # retried without a new model call
            lines.append({"id": str(chunk_id), "status": "write_failed", "reason": reason})
        self.state["in_flight"] = {}
        self.log(lines)

    async def process(self, chunks: list[store.ChunkState]) -> list[dict[str, Any]]:
        """Plan the chunks (counted) and, when writing, generate the titles of the planned ones
        into ``in_flight``; returns the manifest lines."""
        state = self.state
        titles = await self.titles_of(chunks)
        planned, lines = [], []
        for chunk in chunks:
            action, document_title = plan(chunk, titles, regenerate=state["regenerate"],
                                          allow_missing_document_title=state["allow_missing_document_title"])
            self.counts["examined"] += 1
            self.counts[action] += 1
            key = language_key(chunk.language)
            state["languages"][key] = state["languages"].get(key, 0) + 1
            if action in REPORTED:
                lines.append({"id": str(chunk.id), "status": action,
                              "document_ids": [str(i) for i in chunk.document_ids]})
            elif action == "generate" and self.write:
                planned.append((chunk, document_title))
        if planned:
            generated, failures = await self.generate(planned)
            lines += self.record_failures(failures)
            state["in_flight"] = {str(i): t for i, t in sorted(generated.items())}
        return lines

    async def retry(self, limit: int | None = None) -> int:
        """Process again the ids an earlier run left to retry (their earlier failure is no longer
        counted), each once: an id that fails again is left for the next run. A failed write is
        retried with its recorded title, without a model call, unless the chunk no longer exists
        (``absent``) or got another title since (``has_title``; replaced only with
        ``--regenerate``). Returns the number of ids taken."""
        pending = sorted(self.state["retry"])[:limit]
        for start in range(0, len(pending), PAGE_SIZE):
            batch, to_write = pending[start:start + PAGE_SIZE], {}
            for chunk_id in batch:
                self.counts[self.state["retry"].pop(chunk_id)] -= 1
            unwritten = {i: self.state["unwritten"].pop(i) for i in batch if i in self.state["unwritten"]}
            ids = [UUID(i) for i in batch]
            stored = await _retrying(lambda: store.read_chunks(self.client, self.chunks, ids, self.with_language))
            titles = await self.titles_of([c for c in stored.values() if str(c.id) not in unwritten])
            planned, lines = [], []
            for chunk_id in ids:
                chunk = stored.get(chunk_id)
                if chunk is None:
                    self.counts["absent"] += 1
                    lines.append({"id": str(chunk_id), "status": "absent"})
                    continue
                recorded = unwritten.get(str(chunk_id))
                if recorded is not None:
                    current = text_value(chunk.title)
                    if current is not None and current != recorded and not self.state["regenerate"]:
                        self.counts["has_title"] += 1
                        lines.append({"id": str(chunk_id), "status": "has_title",
                                      "reason": "titled by another writer since the failed write"})
                    else:
                        to_write[str(chunk_id)] = recorded
                    continue
                action, document_title = plan(chunk, titles, regenerate=self.state["regenerate"],
                                              allow_missing_document_title=self.state["allow_missing_document_title"])
                if action == "generate":
                    planned.append((chunk, document_title))
                elif action in REPORTED:
                    self.counts[action] += 1
                    lines.append({"id": str(chunk_id), "status": action})
            generated: dict[UUID, str] = {}
            if planned:
                generated, failures = await self.generate(planned)
                lines += self.record_failures(failures)
            self.state["in_flight"] = to_write | {str(i): t for i, t in sorted(generated.items())}
            self.log(lines)
            await self.flush()
        return len(pending)


async def run(client: WeaviateAsyncClient, names: CollectionNames, llm: LlmGateway, *, checkpoint: Path,
              endpoint: str, write: bool, models_config: Path, selection: Selection = Selection(),
              tier: str | None = None, regenerate: bool = False, allow_missing_document_title: bool = False,
              limit: int | None = None, concurrency: int = CONCURRENCY, usage: UsageTotals | None = None,
              progress: Callable[[str], None] = _progress) -> dict[str, Any]:
    """One pass over the selection (see the module docstring); returns the summary. Raises
    ``Refused`` before writing when a collection or ``Chunks.title`` is missing, the model
    catalog cannot serve the feature, ``--regenerate`` lacks an explicit selection or the
    checkpoint belongs to another run."""
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

    identity = {"endpoint": endpoint, "chunks": chunks, "documents": documents, "mode": "write" if write else "check",
                "selection": selection.identity(), "regenerate": regenerate,
                "allow_missing_document_title": allow_missing_document_title, "provenance": origin}
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        state.setdefault("unwritten", {})
        state.setdefault("manifest_lines", [])
        if "manifest_size" not in state:
            manifest = manifest_path(checkpoint)
            state["manifest_size"] = manifest.stat().st_size if manifest.exists() else 0
        differing = sorted(key for key, value in identity.items() if state.get(key) != value)
        if differing:
            raise Refused(f"The checkpoint {checkpoint} has a different {', '.join(differing)}; use a new checkpoint")
        if state["done"] and not state["retry"] and not state["in_flight"]:
            raise Refused(f"The checkpoint {checkpoint} belongs to a finished run; give a new checkpoint file name")
        progress(f"Resuming {checkpoint}: after {state['after']}, {len(state['retry'])} to retry, "
                 f"{len(state['in_flight'])} titles to write")
    else:
        state = {**identity, "started": _now(), "after": None, "done": False, "retry": {}, "in_flight": {}, "unwritten": {},
                 "manifest_size": 0, "manifest_lines": [],
                 "counts": _counts(), "languages": {}, "usage": {key: 0 for key in USAGE_KEYS}}
        _write_json(checkpoint, state)
    _repair_uuids(titled_path(checkpoint))

    work = _Run(client, llm, state, checkpoint, chunks=chunks, documents=documents,
                with_language=chunk_types.get(store.LANGUAGE) in ("text", "text[]"),
                with_document_title=document_types.get(store.TITLE) == "text", write=write, tier=tier,
                concurrency=concurrency, usage=usage, progress=progress)
    started = time.monotonic()
    work.append_manifest()   # lines recorded before an interruption
    await work.flush()   # titles generated before an interruption: written without new model calls
    examined = await work.retry(limit)

    selected = None
    if selection.explicit:
        selected = await _resolve(client, chunks, selection, concurrency)
        progress(f"Selected {len(selected)} chunks")
    while not state["done"] and (limit is None or examined < limit):
        size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - examined)
        after = UUID(state["after"]) if state["after"] else None
        lines: list[dict[str, Any]] = []
        if selected is None:
            page = await _retrying(lambda: store.read_chunk_page(client, chunks, after, size, work.with_language))
            last = page[-1].id if page else None
            state["done"] = len(page) < size
        else:
            start = 0 if after is None else bisect.bisect_right(selected, after)
            ids = selected[start:start + size]
            stored = await _retrying(lambda: store.read_chunks(client, chunks, ids, work.with_language))
            page = [stored[i] for i in ids if i in stored]
            for missing in (i for i in ids if i not in stored):
                work.counts["absent"] += 1
                lines.append({"id": str(missing), "status": "absent"})
            last = ids[-1] if ids else None
            state["done"] = start + size >= len(selected)
        lines += await work.process(page)
        examined += len(page) if selected is None else len(ids)   # an absent id counts toward --limit
        if last is not None:
            state["after"] = str(last)
        work.log(lines)
        await work.flush()
        seconds = max(time.monotonic() - started, 1e-3)
        counts = work.counts
        progress(f"examined {counts['examined']} " + " ".join(
            f"{key} {counts[key]}" for key in (*PLANNED, *REPORTED, *RETRIED, "written") if counts[key])
            + f" to retry {len(state['retry'])} after {state['after']} ({examined / seconds:.1f}/s this run)")

    state["finished"] = _now()
    work.save()
    return summary(state, checkpoint)


async def _resolve(client: WeaviateAsyncClient, chunks: str, selection: Selection, concurrency: int) -> list[UUID]:
    """The sorted chunk ids of an explicit selection."""
    async def of(document: UUID) -> list[UUID]:
        return await _retrying(lambda: store.document_chunk_ids(client, chunks, document))
    ids = set(selection.chunks)
    for found in await _gather(sorted(set(selection.documents)), concurrency, of):
        ids.update(found)
    return sorted(ids)


def summary(state: dict[str, Any], checkpoint: Path) -> dict[str, Any]:
    keys = ("endpoint", "chunks", "documents", "mode", "selection", "regenerate", "allow_missing_document_title",
            "provenance", "after", "done", "counts", "languages", "usage")
    return {key: state[key] for key in keys} | {
        "to_retry": len(state["retry"]), "titles_to_write": len(state["in_flight"]),
        "checkpoint": str(checkpoint), "manifest": str(manifest_path(checkpoint)),
        "titled": str(titled_path(checkpoint))}


def exit_code(result: dict[str, Any]) -> int:
    """0 only for a complete selection: nothing to generate (check), deferred, reported or
    left to retry."""
    counts = result["counts"]
    if not result["done"] or result["to_retry"] or result["titles_to_write"]:
        return 1
    if any(counts[key] for key in (*REPORTED, *RETRIED)):
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
    mode.add_argument("--check", type=Path, metavar="CHECKPOINT",
                      help="plan the selection without model calls or writes; resumes a checkpoint")
    mode.add_argument("--write", type=Path, metavar="CHECKPOINT",
                      help="generate and write the titles; resumes a checkpoint")
    p.add_argument("--confirm-endpoint", metavar="HOST:PORT", help="with --write: the configured Weaviate endpoint")
    p.add_argument("--models-config", type=Path, required=True, metavar="MODELS.yaml",
                   help="model tier catalog declaring the chunk_titles feature")
    p.add_argument("--tier", help="a tier the feature allows (default: the feature's default)")
    p.add_argument("--documents", type=UUID, nargs="+", default=[], metavar="ID", help="select these documents' chunks")
    p.add_argument("--documents-from", type=Path, metavar="FILE", help="select the chunks of the documents listed")
    p.add_argument("--chunks", type=UUID, nargs="+", default=[], metavar="ID", help="select these chunks")
    p.add_argument("--chunks-from", type=Path, metavar="FILE", help="select the chunks listed (text or .uuids)")
    p.add_argument("--regenerate", action="store_true", help="also replace existing titles (explicit selection only)")
    p.add_argument("--allow-missing-document-title", action="store_true",
                   help="generate titles of chunks whose document has no title, without it")
    p.add_argument("--limit", type=_positive,
                   help="at most this many chunks examined in this run (absent selected ids and retries of "
                        "an earlier run included)")
    p.add_argument("--concurrency", type=_positive, default=CONCURRENCY, help=f"parallel model calls and writes "
                                                                         f"(default {CONCURRENCY})")
    return p


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
    usage = UsageTotals()
    llm = LlmGateway(catalog, ProviderSettings.from_config(config), usage)
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    client = await connect_weaviate(config, query_timeout=QUERY_TIMEOUT)
    try:
        result = await run(client, config.collectionNames, llm, checkpoint=args.write or args.check,
                           endpoint=endpoint, write=bool(args.write), models_config=args.models_config,
                           selection=selection, tier=args.tier, regenerate=args.regenerate,
                           allow_missing_document_title=args.allow_missing_document_title, limit=args.limit,
                           concurrency=args.concurrency, usage=usage)
        print(json.dumps(result, indent=2))
        return exit_code(result)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
