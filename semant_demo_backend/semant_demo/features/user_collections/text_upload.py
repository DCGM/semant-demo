"""Upload of private plain-text documents into a user collection (#785, docs/TEXT_UPLOAD.md).

One request imports one or more UTF-8 ``.txt`` files, optionally with a CSV of their
bibliographic metadata. Each file becomes a new ``Documents`` object (``public=false``) with
ordered ``Chunks`` that carry their absolute positions (#463),
``classification_provenance=UNPROCESSED`` (#590) and a vector for every configured search
vector, and is linked to the collection.

Order of checks: the owner's membership-edit right (ADR 0007), then that every configured
vector may embed private text (``VectorSettings.private_text``) and that the store declares
what the upload writes; only then is the request body read (``read_files``). Every file and
the CSV are validated before anything is written: any invalid input refuses the whole batch
(``invalid`` files, the others ``not_written``) so that metadata is never silently dropped.

Writes per file, in this order, never deleting anything (ADR 0002):

1. the document, private and **not linked** to any collection;
2. its chunks, each inserted with its document and collection references and its vectors in
   one write, batch by batch as they are embedded;
3. a readback: every chunk stored with its order, text and vectors, and no other chunk
   referencing the document;
4. the document's link to the collection: from this step on the document is readable
   through the collection (#279).

A document is private from its first write and unreadable to everyone until step 4, so a
failure or crash before it leaves an unreachable document that no reader shows
(``failed``; uploading the file again creates a new document, docs/TEXT_UPLOAD.md lists how
operators find the leftovers). A failed link is read back: ``uncertain`` only when that
fails too. File text and names are never logged.
"""
import asyncio
import csv
import io
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

from semant_demo.adapters.weaviate.chunk_visibility import PROPERTY as DOCUMENT_PUBLIC
from semant_demo.adapters.weaviate.classification_provenance import PROPERTY as PROVENANCE, UNPROCESSED
from semant_demo.adapters.weaviate.have_vector import PROPERTY as HAVE_VECTOR
from semant_demo.adapters.weaviate.documents import POSITION_PROPERTIES
from semant_demo.adapters.weaviate.text_upload import StoredUploadChunk, UploadSchema
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.core.errors import ServiceUnavailableError
from semant_demo.features.documents.positions import chunk_positions
from semant_demo.features.search.vectors import SearchVector, SearchVectors
from semant_demo.features.user_collections import access
from semant_demo.features.user_collections.access import Principal
from semant_demo.features.user_collections.schemas import TextUploadFileResult, TextUploadResponse

logger = logging.getLogger(__name__)

CSV_COLUMNS = ("filename", "title", "author", "yearIssued", "language", "description")
"""The columns of the metadata CSV; ``filename`` is required, the others optional."""
CSV_TEMPLATE = "filename,title,author,yearIssued,language,description\r\n" \
               "example.txt,Example document,Jane Doe,1925,cs,Optional description\r\n"
"""The downloadable template (also in docs/TEXT_UPLOAD.md)."""
METADATA_LIMITS = {"title": 500, "author": 300, "language": 32, "description": 5000}
"""The longest accepted value of each text column, in characters."""
YEAR = re.compile(r"-?\d{1,4}")


@dataclass(frozen=True)
class UploadLimits:
    """Backend limits, enforced whatever the client checks."""
    max_files: int = 20
    max_file_bytes: int = 2_000_000
    max_csv_bytes: int = 1_000_000
    max_request_bytes: int = 24_000_000
    """The whole multipart body, checked from ``Content-Length`` before it is read."""
    max_filename_chars: int = 255
    chunk_chars: int = 1000
    """A chunk is closed before a paragraph that would make it longer than this."""
    max_chunk_chars: int = 1500
    """A longer paragraph is split at whitespace (at most this many characters a chunk)."""
    max_chunks_per_file: int = 2000
    embed_batch: int = 32
    embed_attempts: int = 3
    retry_delay: float = 1.0
    """Seconds before the second embedding attempt; doubled before each further one."""
    write_concurrency: int = 8
    max_concurrent_uploads: int = 2
    """Uploads one backend process runs at a time; another is refused (503) before its body
    is read, so uploads cannot crowd out the query embeddings of search on the same embedder."""


DEFAULT_LIMITS = UploadLimits()


class _Slots:
    """Running uploads of this process (one event loop: a plain counter is enough)."""

    def __init__(self) -> None:
        self.running = 0

    def acquire(self, limit: int) -> bool:
        if self.running >= limit:
            return False
        self.running += 1
        return True

    def release(self) -> None:
        self.running -= 1


RUNNING = _Slots()


@dataclass(frozen=True)
class UploadedFile:
    """A file of the request: the name the client sent and its bytes."""
    filename: str
    content: bytes


class UploadStore(Protocol):
    async def schema(self) -> UploadSchema: ...

    async def create_document(self, document_id: UUID, properties: dict[str, Any]) -> None: ...

    async def insert_chunk(self, chunk_id: UUID, document_id: UUID, collection_id: UUID,
                           properties: dict[str, Any], vectors: dict[str, list[float]]) -> None: ...

    async def read_chunks(self, ids: list[UUID], vector_names: list[str]) -> dict[UUID, StoredUploadChunk]: ...

    async def count_chunks(self, document_id: UUID) -> int: ...

    async def link_document(self, document_id: UUID, collection_id: UUID) -> None: ...


class BatchEmbedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


ReadFiles = Callable[[], Awaitable[tuple[list[UploadedFile], UploadedFile | None]]]
"""Reads the request's text files and optional CSV; called only after the access checks."""


# ── Text and chunks ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextChunk:
    text: str
    end_paragraph: bool


_PARAGRAPH_BREAK = re.compile(r"(\n[ \t]*\n\s*)")


def decode_text(content: bytes) -> str:
    """UTF-8 (an initial BOM is dropped) with line ends normalized to ``\\n``; ``ValueError``
    for anything else than readable plain text."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The file is not UTF-8 text.") from None
    if "\x00" in text:
        raise ValueError("The file is binary, not plain text.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ValueError("The file is empty.")
    return text


def _paragraphs(text: str) -> list[str]:
    """``text`` cut after each blank-line break, every break kept with the paragraph before
    it; leading whitespace stays with the first paragraph. Joined they are ``text``."""
    parts = _PARAGRAPH_BREAK.split(text)
    paragraphs = [parts[i] + (parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]
    merged: list[str] = []
    for paragraph in paragraphs:
        if merged and not merged[-1].strip():
            merged[-1] += paragraph
        else:
            merged.append(paragraph)
    if len(merged) > 1 and not merged[-1].strip():
        tail = merged.pop()
        merged[-1] += tail
    return [p for p in merged if p]


def _split_long(paragraph: str, maximum: int) -> list[str]:
    """Pieces of at most ``maximum`` characters, cut after the last whitespace of each piece
    when it has one in its second half, else exactly at ``maximum``."""
    pieces = []
    while len(paragraph) > maximum:
        window = paragraph[:maximum]
        cut = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
        cut = cut + 1 if cut >= maximum // 2 else maximum
        pieces.append(paragraph[:cut])
        paragraph = paragraph[cut:]
    if paragraph:
        pieces.append(paragraph)
    return pieces


def chunk_text(text: str, target: int = DEFAULT_LIMITS.chunk_chars,
               maximum: int = DEFAULT_LIMITS.max_chunk_chars) -> list[TextChunk]:
    """Deterministic chunks of ``text``: whole paragraphs (split at blank lines) packed up to
    ``target`` characters, a paragraph longer than ``maximum`` split at whitespace. The chunk
    texts joined in order are exactly ``text``, so positions and annotation offsets are those
    of the file's text (#463). ``end_paragraph`` marks a chunk that ends a paragraph."""
    chunks: list[TextChunk] = []
    current = ""
    for paragraph in _paragraphs(text):
        if len(paragraph) > maximum:
            if current:
                chunks.append(TextChunk(current, True))
                current = ""
            pieces = _split_long(paragraph, maximum)
            chunks.extend(TextChunk(piece, i == len(pieces) - 1) for i, piece in enumerate(pieces))
            continue
        if current and len(current) + len(paragraph) > target:
            chunks.append(TextChunk(current, True))
            current = ""
        current += paragraph
    if current:
        chunks.append(TextChunk(current, True))
    return chunks


# ── Names and metadata ───────────────────────────────────────────────────


def clean_filename(name: str | None, limit: int) -> str:
    """The base name of an uploaded file; ``ValueError`` unless it is a usable ``.txt`` name."""
    base = re.split(r"[\\/]", name or "")[-1].strip()
    if not base:
        raise ValueError("The file has no name.")
    if len(base) > limit:
        raise ValueError(f"The file name is longer than {limit} characters.")
    if any(unicodedata.category(c) == "Cc" for c in base):
        raise ValueError("The file name contains control characters.")
    if not base.lower().endswith(".txt") or not base[:-4].strip():
        raise ValueError("Only .txt files can be uploaded.")
    return base


def default_title(filename: str) -> str:
    return filename[:-4].strip()


@dataclass
class Metadata:
    title: str | None = None
    author: str | None = None
    yearIssued: int | None = None
    language: str | None = None
    description: str | None = None


@dataclass
class ParsedCsv:
    rows: dict[str, Metadata] = field(default_factory=dict)
    """By file name."""
    file_errors: dict[str, str] = field(default_factory=dict)
    """Rows of a file name that are invalid."""
    errors: list[str] = field(default_factory=list)
    """Problems not tied to an uploaded file: encoding, header, unknown file names."""


def parse_metadata_csv(content: bytes) -> ParsedCsv:
    """The metadata rows by file name; every problem is reported, none skipped silently."""
    result = ParsedCsv()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        result.errors.append("The metadata CSV is not UTF-8.")
        return result
    try:
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as e:
        result.errors.append(f"The metadata CSV cannot be read: {e}.")
        return result
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        result.errors.append("The metadata CSV is empty: it needs a header row.")
        return result
    header = [cell.strip() for cell in rows[0]]
    unknown = [c for c in header if c not in CSV_COLUMNS]
    if unknown:
        result.errors.append(f"Unsupported metadata CSV column(s): {', '.join(unknown)}. "
                             f"Supported: {', '.join(CSV_COLUMNS)}.")
    duplicates = sorted({c for c in header if header.count(c) > 1})
    if duplicates:
        result.errors.append(f"Repeated metadata CSV column(s): {', '.join(duplicates)}.")
    if "filename" not in header:
        result.errors.append("The metadata CSV needs a filename column.")
    if result.errors:
        return result
    seen: set[str] = set()
    for line, row in enumerate(rows[1:], 2):
        if len(row) > len(header):
            result.errors.append(f"Metadata CSV row {line} has more values than columns.")
            continue
        values = {name: (row[i].strip() if i < len(row) else "") for i, name in enumerate(header)}
        filename = values.pop("filename")
        if not filename:
            result.errors.append(f"Metadata CSV row {line} has no filename.")
            continue
        if filename in seen:
            result.file_errors[filename] = f"The metadata CSV has more than one row for this file (row {line})."
            continue
        seen.add(filename)
        metadata, problems = Metadata(), []
        for name, value in values.items():
            if not value:
                continue
            if name == "yearIssued":
                if not YEAR.fullmatch(value):
                    problems.append(f"yearIssued {value!r} is not a year (a whole number)")
                    continue
                metadata.yearIssued = int(value)
            elif len(value) > METADATA_LIMITS[name]:
                problems.append(f"{name} is longer than {METADATA_LIMITS[name]} characters")
            else:
                setattr(metadata, name, value)
        if problems:
            result.file_errors[filename] = f"Metadata CSV row {line}: {'; '.join(problems)}."
        else:
            result.rows[filename] = metadata
    return result


# ── Validation of the batch ──────────────────────────────────────────────


@dataclass
class PreparedFile:
    filename: str
    title: str
    metadata: Metadata
    chunks: list[TextChunk]


def _document_properties(prepared: PreparedFile) -> dict[str, Any]:
    """The new document's properties: ``public`` is always false, nothing the client sends
    sets it, the library, a URL or any id."""
    m = prepared.metadata
    properties: dict[str, Any] = {"title": prepared.title, "public": False}
    if m.author:
        properties["author"] = [m.author]
    if m.yearIssued is not None:
        properties["yearIssued"] = m.yearIssued
    if m.language:
        properties["language"] = m.language
    if m.description:
        properties["description"] = m.description
    return properties


REQUIRED_CHUNK_PROPERTIES = {"text": "text", "order": "int", "end_paragraph": "boolean", PROVENANCE: "text",
                             **{name: "boolean" if name == "wordOpenAtStart" else "int"
                                for name in POSITION_PROPERTIES}}
"""What every uploaded chunk stores, with the declared type it needs."""
OPTIONAL_CHUNK_PROPERTIES = {"yearIssued": "int", "language": "text"}
"""Copies of the document's year (the year filter, #153) and language, written when declared."""
FLAG_CHUNK_PROPERTIES = {DOCUMENT_PUBLIC: "boolean", HAVE_VECTOR: "text[]"}
"""Written when declared: ``documentPublic=false`` (the document is private, #793) and
``haveVector`` listing the vectors written (#805), so no embedder selects the chunk again.
Declared with another type, they refuse the upload."""
DOCUMENT_PROPERTY_TYPES = {"title": ("text",), "public": ("boolean",), "author": ("text[]",),
                           "yearIssued": ("int", "number"), "language": ("text",), "description": ("text",)}


def check_schema(schema: UploadSchema, vectors: list[SearchVector], link: str) -> list[str]:
    """What the store lacks for an upload; empty when it can take one."""
    problems = []
    for name in ("title", "public"):
        if schema.document_properties.get(name) not in DOCUMENT_PROPERTY_TYPES[name]:
            problems.append(f"Documents.{name}")
    if "collection" not in schema.document_references:
        problems.append("Documents.collection")
    for name, kind in REQUIRED_CHUNK_PROPERTIES.items():
        if schema.chunk_properties.get(name) != kind:
            problems.append(f"Chunks.{name}")
    for name, kind in FLAG_CHUNK_PROPERTIES.items():
        if schema.chunk_properties.get(name) not in (None, kind):
            problems.append(f"Chunks.{name}")
    for name in ("document", link):
        if name not in schema.chunk_references:
            problems.append(f"Chunks.{name}")
    for vector in vectors:
        if vector.target_vector not in schema.chunk_vectors:
            problems.append(f"Chunks vector {vector.target_vector}")
    return problems


def prepare(files: list[UploadedFile], metadata_csv: UploadedFile | None, schema: UploadSchema,
            limits: UploadLimits) -> tuple[list[PreparedFile], list[TextUploadFileResult], list[str]]:
    """Validate every file and the CSV before any write: the prepared files, a result for each
    uploaded file in request order (``invalid`` with its error, else ``not_written`` until it
    is imported) and the errors of the batch as a whole."""
    errors: list[str] = []
    if not files:
        errors.append("Choose at least one .txt file.")
    if len(files) > limits.max_files:
        errors.append(f"At most {limits.max_files} files can be uploaded at once.")
    parsed = ParsedCsv()
    if metadata_csv is not None:
        if len(metadata_csv.content) > limits.max_csv_bytes:
            errors.append(f"The metadata CSV is larger than {limits.max_csv_bytes // 1000} kB.")
        else:
            parsed = parse_metadata_csv(metadata_csv.content)
            errors.extend(parsed.errors)

    names: list[str | None] = []
    problems: list[str | None] = []
    for upload in files:
        try:
            names.append(clean_filename(upload.filename, limits.max_filename_chars))
            problems.append(None)
        except ValueError as e:
            names.append(None)
            problems.append(str(e))
    for i, name in enumerate(names):
        if name is not None and names.count(name) > 1:
            problems[i] = "Another file of this upload has the same name; rename one of them."

    uploaded = {n for n in names if n is not None}
    unmatched = sorted((set(parsed.rows) | set(parsed.file_errors)) - uploaded)
    if unmatched:
        errors.append(f"The metadata CSV names file(s) that are not uploaded: {', '.join(unmatched)}.")

    prepared: list[PreparedFile] = []
    results: list[TextUploadFileResult] = []
    for upload, name, problem in zip(files, names, problems):
        display = name or (upload.filename or "")
        if problem is None and len(upload.content) > limits.max_file_bytes:
            problem = f"The file is larger than {limits.max_file_bytes // 1_000_000} MB."
        if problem is None:
            problem = parsed.file_errors.get(name)
        metadata = parsed.rows.get(name, Metadata()) if name else Metadata()
        if problem is None:
            unsupported = [k for k, v in _document_properties(PreparedFile(name, "", metadata, [])).items()
                           if k not in ("title", "public")
                           and schema.document_properties.get(k) not in DOCUMENT_PROPERTY_TYPES[k]]
            if unsupported:
                problem = f"This store cannot hold the metadata field(s) {', '.join(unsupported)}."
        chunks: list[TextChunk] = []
        if problem is None:
            try:
                chunks = chunk_text(decode_text(upload.content), limits.chunk_chars, limits.max_chunk_chars)
            except ValueError as e:
                problem = str(e)
        if problem is None and len(chunks) > limits.max_chunks_per_file:
            problem = f"The file is too long: more than {limits.max_chunks_per_file} chunks."
        if problem is not None:
            results.append(TextUploadFileResult(filename=display, status="invalid", error=problem))
            continue
        title = metadata.title or default_title(name)
        prepared.append(PreparedFile(name, title, metadata, chunks))
        results.append(TextUploadFileResult(filename=name, status="not_written", title=title, chunks=len(chunks)))
    return prepared, results, errors


# ── Embedding ────────────────────────────────────────────────────────────


class EmbeddingFailed(Exception):
    pass


def _valid_embeddings(embeddings: Any, count: int) -> bool:
    if not isinstance(embeddings, list) or len(embeddings) != count:
        return False
    lengths = set()
    for vector in embeddings:
        if not isinstance(vector, list) or not vector:
            return False
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in vector):
            return False
        lengths.add(len(vector))
    return len(lengths) == 1


async def embed_batch(vector: SearchVector, texts: list[str], limits: UploadLimits) -> list[list[float]]:
    """The document embeddings of ``texts`` by ``vector``'s model, with bounded retries;
    ``EmbeddingFailed`` naming the vector and the last error class."""
    embedder: BatchEmbedder = vector.embedder  # type: ignore[assignment]
    delay, last = limits.retry_delay, "no answer"
    for attempt in range(limits.embed_attempts):
        if attempt:
            await asyncio.sleep(delay)
            delay *= 2
        try:
            embeddings = await embedder.embed_documents(texts)
        except Exception as e:
            last = type(e).__name__
            continue
        if _valid_embeddings(embeddings, len(texts)):
            return embeddings
        last = "an invalid answer"
    raise EmbeddingFailed(f"Embedding with {vector.name} failed ({last}) after {limits.embed_attempts} attempts.")


# ── Writing ──────────────────────────────────────────────────────────────


@dataclass
class _Written:
    ids: list[UUID] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    vector_lengths: dict[str, int] = field(default_factory=dict)


def _chunk_properties(prepared: PreparedFile, chunks: list[TextChunk], first_order: int,
                      positions: list, schema: UploadSchema, vector_names: list[str]) -> list[dict[str, Any]]:
    result = []
    for i, (chunk, position) in enumerate(zip(chunks, positions)):
        properties: dict[str, Any] = {
            "text": chunk.text, "order": first_order + i, "end_paragraph": chunk.end_paragraph,
            PROVENANCE: UNPROCESSED,
            **{name: getattr(position, field_name) for name, field_name in POSITION_PROPERTIES.items()},
        }
        m = prepared.metadata
        if m.yearIssued is not None and schema.chunk_properties.get("yearIssued") == "int":
            properties["yearIssued"] = m.yearIssued
        if m.language and schema.chunk_properties.get("language") == "text":
            properties["language"] = m.language
        if DOCUMENT_PUBLIC in schema.chunk_properties:
            properties[DOCUMENT_PUBLIC] = False
        if HAVE_VECTOR in schema.chunk_properties:
            properties[HAVE_VECTOR] = sorted(vector_names)
        result.append(properties)
    return result


async def _bounded(coroutines: list[Awaitable[None]], limit: int) -> list[BaseException | None]:
    semaphore = asyncio.Semaphore(limit)

    async def run(coroutine: Awaitable[None]) -> BaseException | None:
        async with semaphore:
            try:
                await coroutine
                return None
            except Exception as e:
                return e
    return list(await asyncio.gather(*(run(c) for c in coroutines)))


async def _write_chunks(store: UploadStore, vectors: list[SearchVector], prepared: PreparedFile,
                        document_id: UUID, collection_id: UUID, schema: UploadSchema,
                        limits: UploadLimits) -> _Written:
    """Embed and insert the chunks batch by batch; raises at the first failed batch."""
    written = _Written()
    positions = list(chunk_positions(c.text for c in prepared.chunks))
    for start in range(0, len(prepared.chunks), limits.embed_batch):
        batch = prepared.chunks[start:start + limits.embed_batch]
        texts = [c.text for c in batch]
        embedded = {v.target_vector: await embed_batch(v, texts, limits) for v in vectors}
        properties = _chunk_properties(prepared, batch, start, positions[start:start + len(batch)], schema,
                                       list(embedded))
        ids = [uuid4() for _ in batch]
        failures = await _bounded([
            store.insert_chunk(chunk_id, document_id, collection_id, props,
                               {name: values[i] for name, values in embedded.items()})
            for i, (chunk_id, props) in enumerate(zip(ids, properties))], limits.write_concurrency)
        written.ids.extend(ids)
        written.texts.extend(texts)
        for name, values in embedded.items():
            written.vector_lengths[name] = len(values[0])
        failed = [e for e in failures if e is not None]
        if failed:
            raise _WriteFailed("insert_chunks", type(failed[0]).__name__,
                               f"{len(failed)} of {len(batch)} chunks were not saved")
    return written


class _WriteFailed(Exception):
    def __init__(self, step: str, error: str, detail: str = ""):
        super().__init__(step)
        self.step, self.error, self.detail = step, error, detail


async def _verify(store: UploadStore, written: _Written, document_id: UUID, collection_id: UUID) -> None:
    """Every chunk stored as written, with its vectors and references, and no other chunk."""
    names = list(written.vector_lengths)
    stored = await store.read_chunks(written.ids, names)
    for order, (chunk_id, text) in enumerate(zip(written.ids, written.texts)):
        chunk = stored.get(chunk_id)
        if chunk is None:
            raise _WriteFailed("verify", "missing chunk", f"chunk {order} was not found")
        if (chunk.document != document_id or collection_id not in chunk.collections or chunk.order != order
                or chunk.text != text):
            raise _WriteFailed("verify", "different chunk", f"chunk {order} differs from what was written")
        if chunk.vector_lengths != written.vector_lengths:
            raise _WriteFailed("verify", "missing vector", f"chunk {order} lacks a vector")
    count = await store.count_chunks(document_id)
    if count != len(written.ids):
        raise _WriteFailed("verify", "chunk count", f"{count} chunks stored, {len(written.ids)} written")


async def _import_file(store: UploadStore, collections: UserCollectionRepository, vectors: list[SearchVector],
                       prepared: PreparedFile, collection_id: UUID, schema: UploadSchema,
                       limits: UploadLimits) -> TextUploadFileResult:
    result = TextUploadFileResult(filename=prepared.filename, status="failed", title=prepared.title,
                                  chunks=len(prepared.chunks))
    document_id = uuid4()
    step = "create_document"
    try:
        await store.create_document(document_id, _document_properties(prepared))
        result.document_id = document_id
        step = "insert_chunks"
        written = await _write_chunks(store, vectors, prepared, document_id, collection_id, schema, limits)
        step = "verify"
        await _verify(store, written, document_id, collection_id)
    except EmbeddingFailed as e:
        return _failed(result, step, "EmbeddingFailed", str(e))
    except _WriteFailed as e:
        return _failed(result, e.step, e.error, e.detail)
    except Exception as e:
        return _failed(result, step, type(e).__name__)

    try:
        await store.link_document(document_id, collection_id)
    except Exception as e:
        logger.warning("Text upload: linking document %s to collection %s failed: %s",
                       document_id, collection_id, type(e).__name__)
        try:
            linked = await collections.document_in_collection(document_id, collection_id)
        except Exception as readback:
            logger.warning("Text upload: reading back the link of document %s failed: %s",
                           document_id, type(readback).__name__)
            result.status = "uncertain"
            result.error = ("Saving finished, but adding the document to the collection could not be "
                            "confirmed. Reload the collection: upload the file again only if it is missing.")
            return result
        if not linked:
            return _failed(result, "link_document", type(e).__name__)
    result.status = "completed"
    logger.info("Text upload: document %s with %d chunks added to collection %s",
                document_id, len(prepared.chunks), collection_id)
    return result


def _failed(result: TextUploadFileResult, step: str, error: str, detail: str = "") -> TextUploadFileResult:
    logger.warning("Text upload: document %s stopped at %s (%s); it is not in any collection",
                   result.document_id, step, error)
    result.status = "failed"
    reason = detail or f"{step} failed ({error})"
    result.error = (f"Not added to the collection: {reason}. Nothing of it is visible; "
                    "upload the file again to retry.")
    return result


# ── Use case ─────────────────────────────────────────────────────────────


async def upload_text_documents(collections: UserCollectionRepository, store: UploadStore,
                                search_vectors: SearchVectors, user: Principal | None, collection_id: str | UUID,
                                read_files: ReadFiles, limits: UploadLimits = DEFAULT_LIMITS
                                ) -> TextUploadResponse:
    """Import the request's text files into the collection (see the module docs). Owner
    only; raises before reading the files when the user may not, when a configured vector is
    not approved for private text or when the store lacks what the upload writes."""
    grant = await access.require_membership_edit(collections, user, collection_id)
    vectors = search_vectors.all()
    unapproved = [v.name for v in vectors if not v.private_text]
    if unapproved:
        raise ServiceUnavailableError(
            "Uploading documents is not enabled on this server: the search vector(s) "
            f"{', '.join(unapproved)} are not approved to embed private text.")
    schema = await store.schema()
    missing = check_schema(schema, vectors, collections.link)
    if missing:
        logger.error("Text upload refused: the store does not declare %s", ", ".join(missing))
        raise ServiceUnavailableError("Uploading documents is not available: the database does not support it yet.")

    if not RUNNING.acquire(limits.max_concurrent_uploads):
        raise ServiceUnavailableError("Other uploads are running; try again in a minute.")
    try:
        files, metadata_csv = await read_files()
        prepared, results, errors = prepare(files, metadata_csv, schema, limits)
        if errors or any(r.status == "invalid" for r in results):
            for r in results:
                if r.status == "not_written":
                    r.error = "Nothing was saved because of the other errors of this upload."
            return TextUploadResponse(files=results, errors=errors)

        by_name = {r.filename: i for i, r in enumerate(results)}
        for item in prepared:
            results[by_name[item.filename]] = await _import_file(
                store, collections, vectors, item, grant.collection_id, schema, limits)
        return TextUploadResponse(files=results, errors=[])
    finally:
        RUNNING.release()
