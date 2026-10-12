"""Audit and deletion of documents without chunks against an in-memory store (#281)."""
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from semant_demo.adapters.weaviate.document_cleanup import Backup, DocumentLinks
from semant_demo.config import Config
from semant_demo.maintenance import document_cleanup
from semant_demo.maintenance.document_cleanup import (
    audit, audit_exit_code, candidates_path, delete, delete_exit_code, delete_paths, read_lines)

OLD = datetime(2026, 1, 1, tzinfo=timezone.utc)
NAMES = Config(environ={}).collectionNames
DOCUMENTS, CHUNKS, USER_COLLECTIONS = "Documents_test", "Chunks_test", "Usercollection_test"


def uid(n: int) -> UUID:
    return UUID(int=n)


class FakeStore:
    """The adapter functions over dicts; ``fail[(name, id)]`` makes that many calls raise."""

    def __init__(self):
        self.documents: dict[UUID, dict] = {}
        self.chunks: dict[UUID, UUID] = {}
        self.user_collections: set[UUID] = set()
        self.extra: dict[UUID, UUID] = {}  # an object of another collection referencing a document
        self.schema = {DOCUMENTS: {"collection": [USER_COLLECTIONS]}, CHUNKS: {"document": [DOCUMENTS]},
                       USER_COLLECTIONS: {}}
        self.backups = [Backup("before-cleanup", "SUCCESS", (DOCUMENTS, CHUNKS, USER_COLLECTIONS),
                               OLD + timedelta(days=30), OLD + timedelta(days=30))]
        self.fail: dict[tuple[str, UUID | None], int] = {}
        self.disagree: set[UUID] = set()
        self.deleted: list[UUID] = []
        self.on_delete = None

    def add_document(self, n: int, *, chunks: int = 0, collections=(), created=OLD) -> UUID:
        document_id = uid(n)
        self.documents[document_id] = {"created": created, "collections": set(collections)}
        self.user_collections |= set(collections)
        for _ in range(chunks):
            self.chunks[uuid4()] = document_id
        return document_id

    def _check(self, name: str, key: UUID | None = None) -> None:
        for k in ((name, key), (name, None)):
            if self.fail.get(k):
                self.fail[k] -= 1
                raise ConnectionError(f"{name} unavailable")

    def _links(self, document_id: UUID) -> DocumentLinks:
        document = self.documents[document_id]
        return DocumentLinks(document_id, document["created"], tuple(sorted(document["collections"])))

    async def resolve_collection(self, client, name):
        return {NAMES.document_collection_name: DOCUMENTS, NAMES.chunks_collection_name: CHUNKS,
                NAMES.user_collection_name: USER_COLLECTIONS}.get(name, name)

    async def reference_schema(self, client):
        return self.schema

    async def total_count(self, client, collection):
        return {DOCUMENTS: len(self.documents), CHUNKS: len(self.chunks)}[collection]

    async def read_document_links_page(self, client, collection, link, after, limit):
        self._check("page")
        ids = sorted(i for i in self.documents if after is None or i > after)
        return [self._links(i) for i in ids[:limit]]

    async def read_document_links(self, client, collection, link, ids):
        self._check("read", ids[0])
        return {i: self._links(i) for i in ids if i in self.documents}

    def _referencing(self, collection, link, target_id):
        if collection == CHUNKS:
            return [c for c, d in self.chunks.items() if d == target_id]
        if collection == DOCUMENTS and link == "collection":
            return [d for d, v in self.documents.items() if target_id in v["collections"]]
        return [o for o, d in self.extra.items() if d == target_id]

    async def any_referencing(self, client, collection, link, target_id):
        self._check("any", target_id)
        return bool(self._referencing(collection, link, target_id))

    async def count_referencing(self, client, collection, link, target_id):
        self._check("count", target_id)
        return len(self._referencing(collection, link, target_id)) + (target_id in self.disagree)

    async def referencing_among(self, client, collection, link, target_id, ids):
        return [i for i in self._referencing(collection, link, target_id) if i in ids]

    async def sample_referenced(self, client, collection, link, limit):
        return sorted(set(list(self.chunks.values())[:limit]))

    async def existing_ids(self, client, collection, ids):
        self._check("exists", ids[0])
        pool = self.documents if collection == DOCUMENTS else self.user_collections
        return {i for i in ids if i in pool}

    async def delete_object(self, client, collection, object_id):
        self._check("delete", object_id)
        if self.on_delete:
            self.on_delete(object_id)
        self.deleted.append(object_id)
        return self.documents.pop(object_id, None) is not None

    async def filesystem_backups(self, client):
        self._check("backups")
        return self.backups


@pytest.fixture
def fake(monkeypatch) -> FakeStore:
    store = FakeStore()
    monkeypatch.setattr(document_cleanup, "store", store)
    monkeypatch.setattr(document_cleanup, "BACKOFF", 0)
    return store


async def run_audit(tmp_path, **kwargs):
    return await audit(None, NAMES, checkpoint=tmp_path / "audit.json", endpoint="localhost:8082",
                       progress=lambda line: None, **kwargs)


async def run_delete(tmp_path, **kwargs):
    kwargs.setdefault("backup_id", "before-cleanup")
    return await delete(None, NAMES, audit_checkpoint=tmp_path / "audit.json", endpoint="localhost:8082",
                        progress=lambda line: None, **kwargs)


def corpus(fake: FakeStore) -> dict[str, UUID]:
    a, b = uid(1001), uid(1002)
    return {
        "one_chunk": fake.add_document(1, chunks=1, collections=[a]),
        "many_chunks": fake.add_document(2, chunks=5),
        "lonely": fake.add_document(3),
        "member": fake.add_document(4, collections=[a]),
        "two_collections": fake.add_document(5, collections=[a, b]),
        "recent": fake.add_document(6, created=datetime.now(timezone.utc)),
    }


async def test_audit_classifies_and_lists_removable_documents(fake, tmp_path):
    docs = corpus(fake)
    summary = await run_audit(tmp_path)

    assert summary["counts"] == {"has_chunks": 2, "no_chunks_unreferenced": 1, "no_chunks_collection_member": 2,
                                 "unknown_or_error": 0, "excluded_recent": 1, "excluded_other_reference": 0}
    assert (summary["examined"], summary["removable"], summary["removable_percent"]) == (6, 3, 50.0)
    assert summary["collection_memberships"] == {
        "candidates_in_collections": 2, "memberships": 3, "candidates_in_several_collections": 1,
        "affected_collections": 2, "missing_collections": 0}
    assert summary["collections"] == {"documents": DOCUMENTS, "chunks": CHUNKS, "user_collections": USER_COLLECTIONS}
    assert summary["probe"] == {"documents_checked": 2}
    assert (summary["chunk_total_start"], summary["chunk_total_end"], summary["chunks_changed_during_audit"]) \
        == (6, 6, False)
    assert summary["examples"]["no_chunks_collection_member"] == [str(docs["member"]), str(docs["two_collections"])]
    lines = read_lines(candidates_path(tmp_path / "audit.json"))
    assert {i: line["category"] for i, line in lines.items()} == {
        str(docs["lonely"]): "no_chunks_unreferenced", str(docs["member"]): "no_chunks_collection_member",
        str(docs["two_collections"]): "no_chunks_collection_member", str(docs["recent"]): "excluded_recent"}
    assert lines[str(docs["two_collections"])]["collection_ids"] == [str(uid(1001)), str(uid(1002))]
    assert audit_exit_code(summary) == 0
    assert fake.deleted == []


async def test_failed_lookups_are_never_zero_chunks(fake, tmp_path):
    transient, broken, inconsistent = fake.add_document(1), fake.add_document(2), fake.add_document(3)
    fake.add_document(4, chunks=1)
    fake.fail[("any", transient)] = 2          # recovers on the last attempt
    fake.fail[("count", broken)] = 99          # the confirming count never answers
    fake.disagree.add(inconsistent)            # no chunk found, one counted

    summary = await run_audit(tmp_path)

    assert summary["counts"]["no_chunks_unreferenced"] == 1
    assert summary["counts"]["unknown_or_error"] == 2
    lines = read_lines(candidates_path(tmp_path / "audit.json"))
    assert lines[str(transient)]["category"] == "no_chunks_unreferenced"
    assert "ConnectionError" in lines[str(broken)]["reason"]
    assert "disagree" in lines[str(inconsistent)]["reason"]
    assert audit_exit_code(summary) == 1


async def test_other_references_to_documents_exclude_them(fake, tmp_path):
    referenced, free = fake.add_document(1), fake.add_document(2)
    fake.add_document(3, chunks=1)
    fake.schema["Bookmarks"] = {"target": [DOCUMENTS]}
    fake.extra[uuid4()] = referenced

    summary = await run_audit(tmp_path)

    assert summary["dependencies"] == ["Bookmarks.target"]
    assert summary["counts"]["excluded_other_reference"] == 1
    assert read_lines(candidates_path(tmp_path / "audit.json"))[str(referenced)]["references"] == ["Bookmarks.target"]
    assert summary["counts"]["no_chunks_unreferenced"] == 1 and str(free) in summary["examples"]["no_chunks_unreferenced"]


async def test_unexpected_schema_or_lookup_is_refused(fake, tmp_path):
    fake.add_document(1, chunks=1)
    fake.schema[CHUNKS] = {"document": ["Documents_old"]}
    with pytest.raises(LookupError, match="targets"):
        await run_audit(tmp_path)
    fake.schema[CHUNKS] = {"document": [DOCUMENTS]}

    async def blind(client, collection, link, target_id):  # e.g. a filter that matches nothing
        return 0
    fake.any_referencing = fake.count_referencing = blind
    with pytest.raises(LookupError, match="missed"):
        await run_audit(tmp_path)
    assert not (tmp_path / "audit.json").exists()


async def test_audit_pages_by_cursor_and_resumes(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(document_cleanup, "PAGE_SIZE", 3)
    for n in range(1, 9):
        fake.add_document(n, chunks=n % 2)
    first = await run_audit(tmp_path, limit=4)
    assert (first["examined"], first["done"], first["after"]) == (4, False, str(uid(4)))

    fake.fail[("page", None)] = 99
    with pytest.raises(ConnectionError):
        await run_audit(tmp_path)
    fake.fail.clear()
    resumed = await run_audit(tmp_path)
    assert (resumed["examined"], resumed["done"], resumed["removable"]) == (8, True, 4)
    with pytest.raises(LookupError, match="endpoint"):
        await audit(None, NAMES, checkpoint=tmp_path / "audit.json", endpoint="localhost:8080",
                    progress=lambda line: None)


async def test_chunks_changing_during_the_audit_block_deletion(fake, tmp_path, monkeypatch):
    fake.add_document(1)
    fake.add_document(2, chunks=1)
    total = fake.total_count
    calls = []

    async def growing(client, collection):
        calls.append(collection)
        return await total(client, collection) + (collection == CHUNKS and calls.count(CHUNKS) > 1)
    fake.total_count = growing
    summary = await run_audit(tmp_path)
    assert summary["chunks_changed_during_audit"] is True and audit_exit_code(summary) == 1
    with pytest.raises(LookupError, match="during the audit"):
        await run_delete(tmp_path)
    assert fake.deleted == []


async def test_delete_removes_candidates_including_collection_members(fake, tmp_path):
    docs = corpus(fake)
    await run_audit(tmp_path)
    summary = await run_delete(tmp_path)

    assert set(fake.deleted) == {docs["lonely"], docs["member"], docs["two_collections"]}
    assert set(fake.documents) == {docs["one_chunk"], docs["many_chunks"], docs["recent"]}
    assert summary["counts"]["deleted"] == 3
    assert (summary["removed_memberships"], summary["affected_collections"]) == (3, 2)
    assert summary["collections_check"] == {"affected_collections": 2, "missing_collections": 0,
                                            "still_listing_deleted": 0, "count_matches": 2, "count_differs": 0,
                                            "count_unknown": 0}
    assert fake.user_collections == {uid(1001), uid(1002)}  # collections are kept
    assert (summary["done"], summary["to_retry"], delete_exit_code(summary)) == (True, 0, 0)
    log = read_lines(delete_paths(tmp_path / "audit.json")[1])
    assert log[str(docs["two_collections"])]["collection_ids"] == [str(uid(1001)), str(uid(1002))]

    again = await run_delete(tmp_path)  # finished: nothing more happens
    assert again["counts"]["deleted"] == 3 and len(fake.deleted) == 3


async def test_delete_rechecks_each_document(fake, tmp_path):
    gains_chunk, gains_link, gone, recreated, ok = (fake.add_document(n) for n in range(1, 6))
    fake.add_document(9, chunks=2)
    await run_audit(tmp_path)
    # a chunk now references it (moved, so the total chunk count, checked first, stays the same)
    fake.chunks[next(iter(fake.chunks))] = gains_chunk
    fake.documents[gains_link]["collections"].add(uid(1003))  # a new collection link: still removed
    fake.user_collections.add(uid(1003))
    del fake.documents[gone]
    fake.documents[recreated]["created"] = datetime.now(timezone.utc)  # newer than the backup

    summary = await run_delete(tmp_path)

    assert fake.deleted == [gains_link, ok]
    assert {k: v for k, v in summary["counts"].items() if v} == {
        "deleted": 2, "already_absent": 1, "skipped_has_chunks": 1, "skipped_not_in_backup": 1}
    assert summary["collections_check"]["count_unknown"] == 1  # the new link had no count before
    assert summary["collections_check"]["still_listing_deleted"] == 0
    assert delete_exit_code(summary) == 0


async def test_chunk_appearing_during_deletion_is_reported(fake, tmp_path):
    racing = fake.add_document(1)
    fake.add_document(2, chunks=1)
    await run_audit(tmp_path)
    fake.on_delete = lambda i: fake.chunks.__setitem__(uuid4(), i)

    summary = await run_delete(tmp_path)

    assert summary["chunk_appeared"] == [str(racing)]


async def test_broken_collection_reference_is_removed_with_the_document(fake, tmp_path):
    dangling = fake.add_document(1, collections=[uid(1009)])
    fake.add_document(2, chunks=1)
    fake.user_collections.discard(uid(1009))  # the collection no longer exists

    audited = await run_audit(tmp_path)
    summary = await run_delete(tmp_path)

    assert audited["collection_memberships"]["missing_collections"] == 1
    assert fake.deleted == [dangling]
    assert summary["collections_check"]["missing_collections"] == 1


async def test_failed_deletions_are_retried_on_resume(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(document_cleanup, "PAGE_SIZE", 2)
    ids = [fake.add_document(n) for n in range(1, 6)]
    fake.add_document(9, chunks=1)
    await run_audit(tmp_path)
    fake.fail[("delete", ids[0])] = 1     # uncertain: retried
    fake.fail[("read", ids[1])] = 99      # lookup failure: skipped, retried

    first = await run_delete(tmp_path, limit=3)
    assert (first["position"], first["done"], first["to_retry"]) == (3, False, 2)
    assert delete_exit_code(first) == 1
    fake.fail.clear()

    resumed = await run_delete(tmp_path)

    assert set(fake.deleted) >= set(ids) and not set(ids) & set(fake.documents)
    assert {k: v for k, v in resumed["counts"].items() if v} == {"deleted": 5}
    assert (resumed["done"], resumed["to_retry"], delete_exit_code(resumed)) == (True, 0, 0)
    outcomes = [json.loads(line)["outcome"] for line in
                delete_paths(tmp_path / "audit.json")[1].read_text().splitlines()]
    assert outcomes.count("deleted") == 5 and outcomes.count("failed") == 1 and outcomes.count("skipped_error") == 1


async def test_retry_pass_covers_more_than_one_batch(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(document_cleanup, "PAGE_SIZE", 3)
    ids = [fake.add_document(n) for n in range(1, 9)]
    fake.add_document(99, chunks=1)
    await run_audit(tmp_path)
    fake.fail[("delete", None)] = 7
    first = await run_delete(tmp_path)
    assert first["to_retry"] == 7
    resumed = await run_delete(tmp_path)
    assert resumed["counts"]["deleted"] == 8 and resumed["to_retry"] == 0
    assert not set(ids) & set(fake.documents)


async def test_delete_preconditions(fake, tmp_path):
    fake.add_document(1)
    fake.add_document(2, chunks=1)
    with pytest.raises(FileNotFoundError):
        await run_delete(tmp_path)
    await run_audit(tmp_path, limit=1)
    with pytest.raises(LookupError, match="not a finished audit"):
        await run_delete(tmp_path)
    await run_audit(tmp_path)

    with pytest.raises(LookupError, match="endpoint"):
        await delete(None, NAMES, audit_checkpoint=tmp_path / "audit.json", endpoint="localhost:8080",
                     backup_id="before-cleanup", progress=lambda line: None)
    with pytest.raises(LookupError, match="No successful"):
        await run_delete(tmp_path, backup_id="missing")
    fake.backups.append(Backup("partial", "SUCCESS", (DOCUMENTS,), OLD, OLD))
    with pytest.raises(LookupError, match="does not hold"):
        await run_delete(tmp_path, backup_id="partial")
    fake.fail[("backups", None)] = 1
    with pytest.raises(LookupError, match="Cannot list"):
        await run_delete(tmp_path)
    fake.chunks[uuid4()] = uid(2)
    with pytest.raises(LookupError, match="since the audit"):
        await run_delete(tmp_path)
    assert fake.deleted == []


async def test_ingestion_during_deletion_stops_the_run(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(document_cleanup, "PAGE_SIZE", 2)
    for n in range(1, 6):
        fake.add_document(n)
    fake.add_document(9, chunks=1)
    await run_audit(tmp_path)
    fake.on_delete = lambda i: len(fake.deleted) == 1 and fake.chunks.__setitem__(uuid4(), uid(9))  # 2nd deletion

    summary = await run_delete(tmp_path)

    assert summary["stopped"] and not summary["done"] and delete_exit_code(summary) == 1
    assert summary["position"] == 2 and len(fake.deleted) == 2


async def test_cli_refuses_unconfirmed_deletion(monkeypatch, tmp_path, capsys):
    for name in ("WEAVIATE_HOST", "WEAVIATE_REST_PORT"):
        monkeypatch.delenv(name, raising=False)
    audit_path = str(tmp_path / "audit.json")
    assert await document_cleanup._main(["--delete", audit_path, "--backup-id", "b"]) == 2
    assert await document_cleanup._main(["--delete", audit_path, "--backup-id", "b",
                                         "--confirm-endpoint", "elsewhere:8080"]) == 2
    assert await document_cleanup._main(["--delete", audit_path, "--confirm-endpoint", "x"]) == 2
    assert "Refusing to delete" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        await document_cleanup._main([])
