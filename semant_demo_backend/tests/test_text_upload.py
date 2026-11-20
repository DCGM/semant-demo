"""Text document upload (#785, features/user_collections/text_upload.py), with an in-memory store.

Access and configuration are checked before the files are read; invalid input writes
nothing; a failed write never links the document; a completed one is private, ordered,
embedded and linked last.
"""
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from semant_demo.adapters.weaviate.text_upload import StoredUploadChunk, UploadSchema
from semant_demo.core.errors import ServiceUnavailableError
from semant_demo.features.documents.positions import chunk_positions
from semant_demo.features.search.vectors import SearchVector, SearchVectors
from semant_demo.features.user_collections import text_upload
from semant_demo.features.user_collections.access import AccessDenied, AuthenticationRequired, ResourceNotFound
from semant_demo.features.user_collections.text_upload import (
    CSV_TEMPLATE, UploadedFile, UploadLimits, chunk_text, parse_metadata_csv,
)

OWNER, SHARED, OTHER = (SimpleNamespace(id=uuid4(), name=n) for n in ("Owner", "Shared", "Other"))
COLLECTION = uuid4()
LINK = "userCollection"
LIMITS = UploadLimits(retry_delay=0)


class Collections:
    link = LINK

    def __init__(self, store):
        self.store = store

    async def read_access_record(self, cid):
        return (OWNER.id, {SHARED.id}) if cid == COLLECTION else None

    async def document_in_collection(self, document_id, cid):
        return cid in self.store.documents.get(document_id, {}).get("collections", set())


SCHEMA = UploadSchema(
    document_properties={"title": "text", "public": "boolean", "author": "text[]", "yearIssued": "int",
                         "language": "text"},
    document_references=frozenset({"collection"}),
    chunk_properties={"text": "text", "order": "int", "end_paragraph": "boolean", "classification_provenance": "text",
                      "startChar": "int", "startWord": "int", "wordOpenAtStart": "boolean", "yearIssued": "int",
                      "language": "text"},
    chunk_references=frozenset({"document", LINK}),
    chunk_vectors=frozenset({"default", "second"}))


class Store:
    """Documents and chunks in memory; ``fail`` names a method that raises (``ConnectionError``)."""

    def __init__(self, schema=SCHEMA, fail=None, fail_after=0):
        self.documents: dict[UUID, dict] = {}
        self.chunks: dict[UUID, dict] = {}
        self.schema_value = schema
        self.fail, self.fail_after = fail, fail_after
        self.calls: list[str] = []

    def _maybe_fail(self, name):
        self.calls.append(name)
        if self.fail == name:
            if self.fail_after <= 0:
                raise ConnectionError(name)
            self.fail_after -= 1

    async def schema(self):
        self._maybe_fail("schema")
        return self.schema_value

    async def create_document(self, document_id, properties):
        self._maybe_fail("create_document")
        self.documents[document_id] = {"properties": properties, "collections": set()}

    async def insert_chunk(self, chunk_id, document_id, collection_id, properties, vectors):
        self._maybe_fail("insert_chunk")
        self.chunks[chunk_id] = {"document": document_id, "collections": {collection_id}, "properties": properties,
                                 "vectors": vectors}

    async def read_chunks(self, ids, vector_names):
        self._maybe_fail("read_chunks")
        return {i: StoredUploadChunk(i, c["document"], frozenset(c["collections"]), c["properties"]["order"],
                                     c["properties"]["text"],
                                     {n: len(v) for n, v in c["vectors"].items() if n in vector_names})
                for i, c in self.chunks.items() if i in ids}

    async def count_chunks(self, document_id):
        self._maybe_fail("count_chunks")
        return sum(c["document"] == document_id for c in self.chunks.values())

    async def link_document(self, document_id, collection_id):
        self._maybe_fail("link_document")
        self.documents[document_id]["collections"].add(collection_id)

    def chunks_of(self, document_id):
        return sorted((c for c in self.chunks.values() if c["document"] == document_id),
                      key=lambda c: c["properties"]["order"])


class Embedder:
    def __init__(self, dim=4, fail_times=0, answer=None):
        self.dim, self.fail_times, self.answer = dim, fail_times, answer
        self.calls: list[list[str]] = []

    async def embed_documents(self, texts):
        self.calls.append(texts)
        if self.fail_times:
            self.fail_times -= 1
            raise TimeoutError("embedding")
        if self.answer is not None:
            return self.answer
        return [[float(len(t)), 1.0, 0.5, 0.25][:self.dim] for t in texts]


def vectors(first=None, second=None, private=(True, True)):
    return SearchVectors([
        SearchVector("main", "Main", "", "default", first or Embedder(), private_text=private[0]),
        SearchVector("small", "Small", "", "second", second or Embedder(dim=2), private_text=private[1]),
    ], default="main")


def reader(files, csv=None):
    calls = []

    async def read():
        calls.append(1)
        return [UploadedFile(name, data) for name, data in files], (UploadedFile("m.csv", csv) if csv else None)
    read.calls = calls
    return read


async def upload(files, csv=None, store=None, user=OWNER, search_vectors=None, collection=COLLECTION, limits=LIMITS):
    store = store or Store()
    read = reader(files, csv)
    result = await text_upload.upload_text_documents(Collections(store), store, search_vectors or vectors(), user,
                                                     collection, read, limits)
    return result, store, read


# ── Chunking ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", [
    "One line.",
    "First paragraph.\n\nSecond paragraph.\n",
    "\n\n  Leading blank lines.\n\n\n\nMany breaks.\n\n",
    "Žluťoučký kůň 😀 úpěl.\n \nďábelské ódy\t\n\n" * 50,
    "word " * 2000,
    "x" * 5000,
])
def test_chunks_join_to_the_text_exactly_and_respect_the_bounds(text):
    chunks = chunk_text(text, target=100, maximum=150)
    assert "".join(c.text for c in chunks) == text
    assert all(0 < len(c.text) <= 150 for c in chunks)
    assert chunks[-1].end_paragraph
    assert chunk_text(text, target=100, maximum=150) == chunks  # deterministic


def test_chunks_pack_whole_paragraphs_and_split_long_ones_at_whitespace():
    text = "aaaa\n\nbbbb\n\n" + "word " * 40 + "\n\ncc"
    chunks = chunk_text(text, target=20, maximum=60)
    assert chunks[0].text == "aaaa\n\nbbbb\n\n" and chunks[0].end_paragraph
    long = [c for c in chunks[1:-1]]
    assert all(c.text.endswith(" ") for c in long[:-1]) and not any(c.end_paragraph for c in long[:-1])
    assert long[-1].end_paragraph and chunks[-1].text == "cc"


# ── CSV ──────────────────────────────────────────────────────────────────


def test_the_template_parses():
    parsed = parse_metadata_csv(CSV_TEMPLATE.encode())
    assert not parsed.errors and not parsed.file_errors
    m = parsed.rows["example.txt"]
    assert (m.title, m.author, m.yearIssued, m.language) == ("Example document", "Jane Doe", 1925, "ces")


def test_the_dialog_offers_the_same_template():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    example = CSV_TEMPLATE.split("\r\n")[1]
    assert example.split(",")[4] == "ces"  # the Language filter's code for Czech
    assert example in (root / "semant_demo_frontend/src/features/documents/upload/textUpload.ts").read_text()


@pytest.mark.parametrize("given, stored", [("ces", "ces"), ("cs", "ces"), ("CS", "ces"), ("cze", "ces"),
                                           ("de", "deu"), ("ger", "deu"), ("hu", "hun"), ("la", "lat"),
                                           ("zxx", "zxx"), ("Pol", "pol")])
def test_the_language_is_stored_as_the_language_filter_code(given, stored):
    parsed = parse_metadata_csv(f"filename,language\na.txt,{given}\n".encode())
    assert parsed.rows["a.txt"].language == stored


@pytest.mark.parametrize("content,error", [
    (b"\xff\xfe", "not UTF-8"),
    (b"", "empty"),
    (b"title,author\n", "filename column"),
    (b"filename,public\na.txt,true\n", "Unsupported"),
    (b"filename,library\na.txt,mzk\n", "Unsupported"),
    (b"filename,title,title\na.txt,x,y\n", "Repeated"),
    (b"filename\na.txt,extra\n", "more values"),
])
def test_csv_problems_of_the_whole_file(content, error):
    assert any(error in e for e in parse_metadata_csv(content).errors)


def test_csv_row_problems_belong_to_their_file():
    parsed = parse_metadata_csv(b"filename,yearIssued\na.txt,19x5\nb.txt,1900\nb.txt,1901\n")
    assert "not a year" in parsed.file_errors["a.txt"]
    assert "more than one row" in parsed.file_errors["b.txt"]


# ── Access and configuration before reading ──────────────────────────────


@pytest.mark.parametrize("user,collection,error", [
    (None, COLLECTION, AuthenticationRequired),
    (SHARED, COLLECTION, AccessDenied),
    (OTHER, COLLECTION, ResourceNotFound),
    (OWNER, uuid4(), ResourceNotFound),
])
async def test_only_the_owner_uploads_and_denied_requests_read_nothing(user, collection, error):
    store, first = Store(), Embedder()
    read = reader([("a.txt", b"text")])
    with pytest.raises(error):
        await text_upload.upload_text_documents(Collections(store), store, vectors(first), user, collection, read)
    assert not read.calls and not store.calls and not first.calls


async def test_a_vector_not_approved_for_private_text_disables_uploads():
    store = Store()
    read = reader([("a.txt", b"text")])
    with pytest.raises(ServiceUnavailableError, match="Small"):
        await text_upload.upload_text_documents(Collections(store), store, vectors(private=(True, False)),
                                                OWNER, COLLECTION, read)
    assert not read.calls and not store.calls


@pytest.mark.parametrize("schema", [
    UploadSchema({"title": "text"}, frozenset({"collection"}), SCHEMA.chunk_properties, SCHEMA.chunk_references,
                 SCHEMA.chunk_vectors),
    UploadSchema(SCHEMA.document_properties, SCHEMA.document_references,
                 {k: v for k, v in SCHEMA.chunk_properties.items() if k != "classification_provenance"},
                 SCHEMA.chunk_references, SCHEMA.chunk_vectors),
    UploadSchema(SCHEMA.document_properties, SCHEMA.document_references, SCHEMA.chunk_properties,
                 SCHEMA.chunk_references, frozenset({"default"})),
    UploadSchema(SCHEMA.document_properties, SCHEMA.document_references,
                 {**SCHEMA.chunk_properties, "documentPublic": "text"}, SCHEMA.chunk_references, SCHEMA.chunk_vectors),
    UploadSchema(SCHEMA.document_properties, SCHEMA.document_references,
                 {**SCHEMA.chunk_properties, "haveVector": "text"}, SCHEMA.chunk_references, SCHEMA.chunk_vectors),
])
async def test_a_store_that_lacks_what_the_upload_writes_is_refused_before_reading(schema):
    store = Store(schema=schema)
    read = reader([("a.txt", b"text")])
    with pytest.raises(ServiceUnavailableError):
        await text_upload.upload_text_documents(Collections(store), store, vectors(), OWNER, COLLECTION, read)
    assert not read.calls and store.calls == ["schema"]


async def test_the_operator_log_names_what_is_declared_and_what_is_needed(caplog):
    schema = UploadSchema(SCHEMA.document_properties, SCHEMA.document_references,
                          {**{k: v for k, v in SCHEMA.chunk_properties.items() if k != "startChar"},
                           "order": "number"}, SCHEMA.chunk_references, frozenset({"default"}))
    ready = await text_upload.availability(Store(schema=schema), vectors(), LINK)
    assert not ready.available and "database does not support it" in ready.message
    assert "startChar" not in ready.message  # the details are only logged
    assert ready.problems == ("Chunks.order (declared number, needs int)", "Chunks.startChar (not declared, needs int)",
                              "Chunks vector second of search vector Small (not configured; the store has default)")
    assert all(p in caplog.text for p in ready.problems)


async def test_a_ready_store_is_available_and_read_once():
    store = Store()
    ready = await text_upload.availability(store, vectors(), LINK)
    assert ready.available and ready.message is None and store.calls == ["schema"]


# ── Validation: nothing is written ───────────────────────────────────────


@pytest.mark.parametrize("files,csv,error", [
    ([("a.pdf", b"x")], None, "Only .txt"),
    ([(".txt", b"x")], None, "Only .txt"),
    ([("a.txt", b"\xff\xfe\x00")], None, "not UTF-8"),
    ([("a.txt", b"bin\x00ary")], None, "binary"),
    ([("a.txt", b"  \n\n ")], None, "empty"),
    ([("a.txt", b"x" * 101)], None, "larger than"),
    ([("a.txt", b"x"), ("dir/a.txt", b"y")], None, "same name"),
    ([("a.txt", b"x")], b"filename,yearIssued\na.txt,around 1900\n", "not a year"),
    ([("a.txt", b"x")], b"filename,title\na.txt," + b"t" * 501 + b"\n", "longer than"),
])
async def test_an_invalid_file_writes_nothing(files, csv, error):
    result, store, _ = await upload([*files, ("ok.txt", b"fine")], csv, limits=UploadLimits(max_file_bytes=100))
    assert any(error in (f.error or "") for f in result.files if f.status == "invalid")
    assert [f.status for f in result.files if f.filename == "ok.txt"] == ["not_written"]
    assert not store.documents and not store.chunks


@pytest.mark.parametrize("csv,error", [
    (b"filename,title\nmissing.txt,X\n", "not uploaded"),
    (b"filename,public\na.txt,true\n", "Unsupported"),
])
async def test_a_csv_problem_refuses_the_whole_upload(csv, error):
    result, store, _ = await upload([("a.txt", b"text")], csv)
    assert any(error in e for e in result.errors)
    assert [f.status for f in result.files] == ["not_written"]
    assert not store.documents


async def test_too_many_files_or_chunks_are_refused():
    result, store, _ = await upload([(f"{i}.txt", b"x") for i in range(3)], limits=UploadLimits(max_files=2))
    assert result.errors and not store.documents
    result, store, _ = await upload([("a.txt", b"p\n\n" * 50)],
                                    limits=UploadLimits(max_chunks_per_file=2, chunk_chars=3, max_chunk_chars=5))
    assert "too long" in result.files[0].error and not store.documents


async def test_metadata_the_store_cannot_hold_is_reported_not_dropped():
    schema = UploadSchema({k: v for k, v in SCHEMA.document_properties.items() if k != "language"},
                          SCHEMA.document_references, SCHEMA.chunk_properties, SCHEMA.chunk_references,
                          SCHEMA.chunk_vectors)
    result, store, _ = await upload([("a.txt", b"x")], b"filename,language\na.txt,ces\n", Store(schema=schema))
    assert "language" in result.files[0].error and not store.documents


async def test_a_description_column_is_refused():
    """No deployed Documents schema declares description (docs/DATABASE.md), so the template
    does not offer it and a CSV naming it is refused as a whole, not dropped."""
    result, store, _ = await upload([("a.txt", b"x")], b"filename,description\na.txt,About\n")
    assert any("description" in e for e in result.errors) and not store.documents


# ── Completed upload ─────────────────────────────────────────────────────


async def test_a_completed_upload_is_private_ordered_embedded_and_linked():
    text = "První odstavec.\n\nDruhý odstavec, delší.\n\n" * 30
    main, small = Embedder(), Embedder(dim=2)
    result, store, _ = await upload([("Kronika obce.txt", ("﻿" + text).encode())],
                                    search_vectors=vectors(main, small), limits=UploadLimits(
        retry_delay=0, embed_batch=5, chunk_chars=50, max_chunk_chars=80))
    [file] = result.files
    assert file.status == "completed" and file.title == "Kronika obce" and file.error is None
    document = store.documents[file.document_id]
    assert document["properties"] == {"title": "Kronika obce", "public": False}
    assert document["collections"] == {COLLECTION}
    chunks = store.chunks_of(file.document_id)
    assert len(chunks) == file.chunks > 5
    assert "".join(c["properties"]["text"] for c in chunks) == text  # BOM dropped, text kept
    assert [c["properties"]["order"] for c in chunks] == list(range(len(chunks)))
    positions = list(chunk_positions(c["properties"]["text"] for c in chunks))
    assert [(c["properties"]["startChar"], c["properties"]["startWord"], c["properties"]["wordOpenAtStart"])
            for c in chunks] == [(p.start_char, p.start_word, p.word_open_at_start) for p in positions]
    assert all(c["properties"]["classification_provenance"] == "UNPROCESSED" for c in chunks)
    assert all(c["collections"] == {COLLECTION} and set(c["vectors"]) == {"default", "second"} for c in chunks)
    assert all(len(batch) <= 5 for batch in main.calls + small.calls)
    assert not any(k in chunks[0]["properties"] for k in ("start_page_id", "from_page", "to_page", "yearIssued",
                                                          "documentPublic", "haveVector"))  # not declared
    assert store.calls[-1] == "link_document"  # linked only after the readback


async def test_declared_chunk_flags_mark_the_chunks_private_and_list_their_vectors():
    """``documentPublic=false`` (#793) and ``haveVector`` (#805), when the store declares them."""
    schema = UploadSchema(SCHEMA.document_properties, SCHEMA.document_references,
                          {**SCHEMA.chunk_properties, "documentPublic": "boolean", "haveVector": "text[]"},
                          SCHEMA.chunk_references, SCHEMA.chunk_vectors)
    result, store, _ = await upload([("a.txt", b"Jeden.\n\nDva.")], store=Store(schema=schema),
                                    search_vectors=vectors(Embedder(), Embedder(dim=2)))
    [file] = result.files
    chunks = store.chunks_of(file.document_id)
    assert file.status == "completed" and chunks
    assert all(c["properties"]["documentPublic"] is False for c in chunks)
    assert all(c["properties"]["haveVector"] == ["default", "second"] for c in chunks)


async def test_csv_metadata_is_stored_and_the_year_copied_to_the_chunks():
    csv = ("filename,title,author,yearIssued,language\n"
           "a.txt,Dopisy z Prahy,Jana Nováková,1925,cs\nb.txt,,,,\n").encode()
    result, store, _ = await upload([("a.txt", "Milá Anno,\n\nzdravím.".encode()), ("b.txt", b"Bez metadat.")], csv)
    a, b = result.files
    assert (a.status, b.status) == ("completed", "completed")
    assert store.documents[a.document_id]["properties"] == {
        "title": "Dopisy z Prahy", "public": False, "author": ["Jana Nováková"], "yearIssued": 1925,
        "language": "ces"}
    assert all(c["properties"]["yearIssued"] == 1925 and c["properties"]["language"] == "ces"
               for c in store.chunks_of(a.document_id))
    assert store.documents[b.document_id]["properties"] == {"title": "b", "public": False}


async def test_repeated_uploads_create_distinct_documents():
    store = Store()
    first, _, _ = await upload([("a.txt", b"same")], store=store)
    second, _, _ = await upload([("a.txt", b"same")], store=store)
    assert first.files[0].document_id != second.files[0].document_id
    assert len(store.documents) == 2 and len(store.chunks) == 2


# ── Failures ─────────────────────────────────────────────────────────────


async def test_embedding_is_retried_a_bounded_number_of_times():
    flaky = Embedder(fail_times=2)
    result, _, _ = await upload([("a.txt", b"text")], search_vectors=vectors(flaky))
    assert result.files[0].status == "completed" and len(flaky.calls) == 3

    broken = Embedder(fail_times=99)
    result, store, _ = await upload([("a.txt", b"text"), ("b.txt", b"more")], search_vectors=vectors(broken))
    assert [f.status for f in result.files] == ["failed", "failed"]
    assert "Main" in result.files[0].error and "TimeoutError" in result.files[0].error
    assert len(broken.calls) == 2 * LIMITS.embed_attempts
    assert not store.chunks and all(not d["collections"] for d in store.documents.values())


@pytest.mark.parametrize("answer", [[], [[1.0], [2.0]], [[float("nan")]], [["x"]]])
async def test_an_invalid_embedding_answer_fails_the_file(answer):
    result, store, _ = await upload([("a.txt", b"text")], search_vectors=vectors(Embedder(answer=answer)))
    assert result.files[0].status == "failed" and not store.chunks


@pytest.mark.parametrize("fail", ["create_document", "insert_chunk", "read_chunks", "count_chunks"])
async def test_a_failed_write_leaves_the_document_unlinked_and_reports_it(fail):
    result, store, _ = await upload([("a.txt", b"p\n\n" * 20), ("b.txt", b"ok")], store=Store(fail=fail, fail_after=1),
                                    limits=UploadLimits(retry_delay=0, chunk_chars=3, max_chunk_chars=5))
    statuses = [f.status for f in result.files]
    assert "failed" in statuses
    for f in result.files:
        if f.status == "failed":
            assert "Not added to the collection" in f.error
            if f.document_id:
                assert not store.documents[f.document_id]["collections"]
                assert store.documents[f.document_id]["properties"]["public"] is False
    assert "link_document" not in store.calls[:store.calls.index(fail) + 1]


async def test_a_chunk_that_reads_back_differently_fails_the_file():
    class Lying(Store):
        async def read_chunks(self, ids, vector_names):
            stored = await super().read_chunks(ids, vector_names)
            return {i: StoredUploadChunk(c.id, c.document, c.collections, c.order, "changed", c.vector_lengths)
                    for i, c in stored.items()}
    result, store, _ = await upload([("a.txt", b"text")], store=Lying())
    assert result.files[0].status == "failed" and "link_document" not in store.calls


async def test_a_failed_link_is_read_back():
    class LinkedThenFailed(Store):
        async def link_document(self, document_id, collection_id):
            await super().link_document(document_id, collection_id)
            raise TimeoutError
    result, _, _ = await upload([("a.txt", b"text")], store=LinkedThenFailed())
    assert result.files[0].status == "completed"

    result, store, _ = await upload([("a.txt", b"text")], store=Store(fail="link_document"))
    assert result.files[0].status == "failed" and "link_document" in result.files[0].error

    class Unconfirmed(Store):
        async def link_document(self, document_id, collection_id):
            raise TimeoutError

    class BrokenCollections(Collections):
        async def document_in_collection(self, document_id, cid):
            raise ConnectionError
    store = Unconfirmed()
    result = await text_upload.upload_text_documents(BrokenCollections(store), store, vectors(), OWNER, COLLECTION,
                                                     reader([("a.txt", b"text")]), LIMITS)
    assert result.files[0].status == "uncertain" and "Reload" in result.files[0].error


async def test_a_collection_that_changed_owner_during_the_upload_gets_no_further_document():
    """Ownership is checked again before each document is linked: a transfer while the first
    file was embedded leaves its document unlinked (and invisible)."""
    class Transferred(Collections):
        checks = 0

        async def read_access_record(self, cid):
            Transferred.checks += 1
            return (OWNER.id if Transferred.checks == 1 else OTHER.id, set()) if cid == COLLECTION else None
    store = Store()
    result = await text_upload.upload_text_documents(Transferred(store), store, vectors(), OWNER, COLLECTION,
                                                     reader([("a.txt", b"text")]), LIMITS)
    [file] = result.files
    assert file.status == "failed" and "can no longer add documents" in file.error
    assert store.documents[file.document_id]["collections"] == set() and "link_document" not in store.calls


async def test_concurrent_uploads_are_bounded_and_refused_before_reading():
    import asyncio
    gate = asyncio.Event()
    store = Store()

    def slow_reader():
        async def read():
            await gate.wait()
            return [UploadedFile("a.txt", b"text")], None
        return read
    limits = UploadLimits(retry_delay=0, max_concurrent_uploads=1)
    first = asyncio.create_task(text_upload.upload_text_documents(
        Collections(store), store, vectors(), OWNER, COLLECTION, slow_reader(), limits))
    await asyncio.sleep(0)
    read = reader([("b.txt", b"text")])
    with pytest.raises(ServiceUnavailableError, match="Other uploads"):
        await text_upload.upload_text_documents(Collections(store), store, vectors(), OWNER, COLLECTION, read, limits)
    assert not read.calls
    gate.set()
    assert (await first).files[0].status == "completed"
    assert text_upload.RUNNING.running == 0
    # The slot is free again, also after a refused or failed upload.
    result, _, _ = await upload([("c.txt", b"text")], limits=limits)
    assert result.files[0].status == "completed"
