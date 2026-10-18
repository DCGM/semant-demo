"""The annotation migration (#327) against real Weaviate: legacy ``Span`` -> tenants.

The fixture corpus spans are written to the legacy collection, together with invalid
records of every kind the migration skips; the annotation tenants start empty. Tests run
the dry run, the backfill (also interrupted and resumed, and repeated), the verification
before and after application writes, and the refusals.
"""
import uuid
from uuid import UUID

import pytest
from weaviate.classes.backup import BackupStorage
from weaviate.classes.data import DataObject
from weaviate.classes.tenants import Tenant

from semant_demo.adapters.weaviate.annotation_migration import MigrationStore
from semant_demo.maintenance import annotation_migration as migration
from tests.seed import seed_legacy_spans

pytestmark = pytest.mark.integration

# Skip reason -> count in the fixture. Weaviate 1.40 does not return a reference whose
# target was deleted, so the spans of a deleted tag or chunk and the tag of a deleted
# collection are read as having no reference (``*_missing`` needs a lookup race).
SKIPPED = {"invalid_type": 1, "invalid_offsets": 1, "no_tag_reference": 2, "several_tag_references": 1,
           "tag_without_collection": 2, "tag_in_several_collections": 1, "no_chunk_reference": 2,
           "chunk_without_document": 1}


async def _insert(client, name, objects):
    result = await client.collections.get(name).data.insert_many(objects)
    assert not result.has_errors, result.errors
    return list(result.uuids.values())


@pytest.fixture
async def legacy(seeded_store, collection_names, corpus, ids):
    """The corpus spans and invalid records in the legacy collection; empty tenants.

    Returns the id of the valid span whose anchor chunk is not in its collection.
    """
    names = collection_names
    annotations = seeded_store.collections.get(names.annotation_collection_name)
    await annotations.tenants.remove(list((await annotations.tenants.get()).keys()))
    await seed_legacy_spans(seeded_store, names, corpus)

    chronicles, newspapers = ids.col["chronicles"], ids.col["newspapers"]
    [gone_collection] = await _insert(seeded_store, names.user_collection_name, [DataObject(properties={"name": "x"})])
    [orphan_tag, double_tag, lost_tag, gone_tag] = await _insert(seeded_store, names.tag_collection_name, [
        DataObject(properties={"tag_name": "orphan"}),
        DataObject(properties={"tag_name": "double"}, references={"userCollection": [chronicles, newspapers]}),
        DataObject(properties={"tag_name": "lost"}, references={"userCollection": gone_collection}),
        DataObject(properties={"tag_name": "gone"}, references={"userCollection": chronicles}),
    ])
    [loose_chunk, gone_chunk] = await _insert(seeded_store, names.chunks_collection_name, [
        DataObject(properties={"text": "no document", "order": 0}),
        DataObject(properties={"text": "deleted", "order": 0}),
    ])
    person, chunk = ids.tag["person"], ids.chunk["chronicle_1"]

    def span(tag=person, text_chunk=chunk, **properties):
        refs = {k: v for k, v in (("tag", tag), ("text_chunk", text_chunk)) if v is not None}
        return DataObject(properties={"start": 0, "end": 3, "type": "pos", **properties}, references=refs)

    [outside] = await _insert(seeded_store, names.span_collection_name, [
        span(text_chunk=ids.chunk["chronicle_3"])])  # valid; chronicle_3 is a newspapers chunk
    await _insert(seeded_store, names.span_collection_name, [
        span(type="maybe"), span(start=3, end=3), span(tag=None), span(tag=[person, ids.tag["place"]]),
        span(tag=gone_tag), span(tag=orphan_tag), span(tag=double_tag), span(tag=lost_tag), span(text_chunk=None),
        span(text_chunk=gone_chunk), span(text_chunk=loose_chunk),
    ])
    # Weaviate refuses references to missing objects, so the targets are deleted afterwards.
    await seeded_store.collections.get(names.user_collection_name).data.delete_by_id(gone_collection)
    await seeded_store.collections.get(names.tag_collection_name).data.delete_by_id(gone_tag)
    await seeded_store.collections.get(names.chunks_collection_name).data.delete_by_id(gone_chunk)
    return str(outside)


@pytest.fixture
def migration_store(seeded_store, collection_names):
    return MigrationStore(seeded_store, collection_names)


def new_state(execute, batch_size=4):
    return migration.new_state("test", "Span", "Annotation", execute, batch_size)


async def api_spans(api_client, headers, collection_id):
    response = await api_client.get("/api/tag_spans", headers=headers, params={"collection_id": collection_id})
    assert response.status_code == 200, response.text
    return {s["id"]: s for s in response.json()}


def corpus_span(corpus, key):
    s = corpus.spans[key]
    return {"id": s["id"], "chunkId": corpus.chunks[s["chunk"]]["id"], "tagId": corpus.tags[s["tag"]]["id"],
            "start": s["start"], "end": s["end"], "type": s["type"], "reason": s.get("reason"),
            "confidence": s.get("confidence")}


async def test_dry_run_reports_everything_and_writes_nothing(migration_store, legacy, ids, corpus, seeded_store,
                                                            collection_names, tmp_path):
    state_path = tmp_path / "dry.json"

    state = await migration.backfill(migration_store, new_state(False), state_path, execute=False)

    counts = state["counts"]
    assert counts["read"] == len(corpus.spans) + 12 == state["legacy_total"]
    assert {k.removeprefix("skipped:"): n for k, n in counts.items() if k.startswith("skipped:")} == SKIPPED
    assert counts["would_copy"] == len(corpus.spans) + 1 and not counts.get("copied")
    assert state["collections"][ids.col["chronicles"]] == {"would_copy": 6, "anchor_not_in_collection": 1}
    assert state["collections"][ids.col["newspapers"]] == {"would_copy": 1}
    assert len(state["tags"]["without_collection"]) == 2 and len(state["tags"]["several_collections"]) == 1
    assert len(state["skipped"]) == sum(SKIPPED.values())
    annotations = seeded_store.collections.get(collection_names.annotation_collection_name)
    assert await annotations.tenants.get() == {}
    assert state_path.exists() and state["done"]


async def test_backfill_copies_valid_spans_with_their_ids_and_verify_matches(
        migration_store, legacy, ids, corpus, api_client, login, tmp_path):
    state = await migration.backfill(migration_store, new_state(True), tmp_path / "run.json", execute=True)

    assert (state["counts"]["copied"], state["counts"].get("failed", 0), state["counts"].get("conflict", 0)) == (
        len(corpus.spans) + 1, 0, 0)
    report = await migration.verify(migration_store, batch_size=3)
    assert migration.verify_ok(report)
    assert report["counts"]["matched"] == len(corpus.spans) + 1

    owner = await login("owner")
    chronicles = await api_spans(api_client, owner, ids.col["chronicles"])
    for key in ("novak_manual", "lhota_automatic", "brno_manual", "kronikar_rejected", "praha_automatic"):
        assert {k: chronicles[corpus.spans[key]["id"]][k] for k in corpus_span(corpus, key)} == \
            corpus_span(corpus, key), key
    assert legacy in chronicles  # its anchor chunk left the collection; it is kept, as before
    newspapers = await api_spans(api_client, owner, ids.col["newspapers"])
    assert list(newspapers) == [corpus.spans["pozar_manual"]["id"]]
    # Statistics count only approved spans on member chunks, as before the migration.
    stats = await api_client.get(f"/api/user_collections/{ids.col['chronicles']}/stats", headers=owner)
    assert stats.json()["annotations_count"] == 2


async def test_an_interrupted_backfill_resumes_at_its_checkpoint(migration_store, legacy, corpus, tmp_path,
                                                                 monkeypatch):
    state_path = tmp_path / "run.json"
    original = MigrationStore.legacy_page
    pages = {"n": 0}

    async def failing_third_page(self, after, limit):
        pages["n"] += 1
        if pages["n"] == 3:
            raise ConnectionError("injected outage")
        return await original(self, after, limit)
    monkeypatch.setattr(MigrationStore, "legacy_page", failing_third_page)

    with pytest.raises(ConnectionError):
        await migration.backfill(migration_store, new_state(True, batch_size=3), state_path, execute=True)
    monkeypatch.undo()
    saved = migration.load_state(state_path, "test", "Span", "Annotation", True)
    assert (saved["batches"], saved["counts"]["read"], saved["done"]) == (2, 6, False)

    state = await migration.backfill(migration_store, saved, state_path, execute=True)

    assert state["done"] and state["counts"]["read"] == len(corpus.spans) + 12
    assert state["counts"]["copied"] == len(corpus.spans) + 1 and not state["counts"].get("already_present")
    assert migration.verify_ok(await migration.verify(migration_store))


async def test_repeating_a_backfill_copies_nothing_and_never_overwrites_a_different_copy(
        migration_store, legacy, ids, corpus, seeded_store, collection_names, tmp_path):
    await migration.backfill(migration_store, new_state(True), tmp_path / "first.json", execute=True)
    novak = corpus.spans["novak_manual"]["id"]
    tenant = seeded_store.collections.get(collection_names.annotation_collection_name).with_tenant(
        ids.col["chronicles"])
    await tenant.data.update(uuid=novak, properties={"type": "neg"})

    again = await migration.backfill(migration_store, new_state(True), tmp_path / "second.json", execute=True)

    assert again["counts"]["already_present"] == len(corpus.spans)
    assert (again["counts"]["conflict"], again["counts"].get("copied", 0)) == (1, 0)
    assert again["conflicts"] == [{"id": novak, "collection_id": ids.col["chronicles"]}]
    assert (await tenant.query.fetch_object_by_id(novak)).properties["type"] == "neg"


async def test_verify_lists_the_writes_made_after_the_cutover(migration_store, legacy, ids, corpus, api_client, login,
                                                              seeded_store, collection_names, tmp_path):
    await migration.backfill(migration_store, new_state(True), tmp_path / "run.json", execute=True)
    owner, c = await login("owner"), {"collection_id": ids.col["chronicles"]}
    created = await api_client.post("/api/tag_spans", headers=owner, json={
        "chunkId": ids.chunk["letters_1"], "tagId": ids.tag["person"], "start": 5, "end": 10, "type": "pos"})
    lhota = corpus.spans["lhota_automatic"]["id"]
    await api_client.patch(f"/api/tag_spans/{lhota}", headers=owner, params=c, json={"type": "pos"})
    orphan = str(uuid.uuid4())
    await seeded_store.collections.get(collection_names.annotation_collection_name).tenants.create(
        [Tenant(name=orphan)])

    report = await migration.verify(migration_store)

    assert not migration.verify_ok(report)
    assert report["target_only"] == [{"id": created.json()["id"], "collection_id": ids.col["chronicles"]}]
    assert report["different"] == [{"id": lhota, "collection_id": ids.col["chronicles"]}]
    assert report["orphan_tenants"] == [orphan] and report["counts"]["missing"] == 0


async def test_execute_creates_a_missing_annotation_collection(migration_store, legacy, seeded_store,
                                                               collection_names, corpus, tmp_path):
    await seeded_store.collections.delete(collection_names.annotation_collection_name)
    dry = await migration.backfill(migration_store, new_state(False), tmp_path / "dry.json", execute=False)
    assert dry["counts"]["would_copy"] == len(corpus.spans) + 1
    assert not await seeded_store.collections.exists(collection_names.annotation_collection_name)

    state = await migration.backfill(migration_store, new_state(True), tmp_path / "run.json", execute=True)

    assert state["counts"]["copied"] == len(corpus.spans) + 1
    assert await migration_store.target_is_multi_tenant()


async def test_a_target_without_multi_tenancy_is_refused(migration_store, legacy, seeded_store, collection_names,
                                                         tmp_path):
    await seeded_store.collections.delete(collection_names.annotation_collection_name)
    await seeded_store.collections.create(collection_names.annotation_collection_name)

    with pytest.raises(LookupError, match="without multi-tenancy"):
        await migration.backfill(migration_store, new_state(True), tmp_path / "run.json", execute=True)


async def test_a_state_of_another_run_is_refused(migration_store, legacy, tmp_path):
    state_path = tmp_path / "dry.json"
    await migration.backfill(migration_store, new_state(False), state_path, execute=False)

    with pytest.raises(LookupError, match="another run"):
        migration.load_state(state_path, "test", "Span", "Annotation", True)
    with pytest.raises(LookupError, match="another run"):
        migration.load_state(state_path, "elsewhere:8080", "Span", "Annotation", False)


async def test_the_backup_must_hold_the_source_collections(seeded_store, collection_names, legacy):
    names = collection_names
    partial, full = f"partial-{uuid.uuid4().hex[:8]}", f"full-{uuid.uuid4().hex[:8]}"
    await seeded_store.backup.create(backup_id=partial, backend=BackupStorage.FILESYSTEM,
                                     include_collections=[names.span_collection_name], wait_for_completion=True)
    await seeded_store.backup.create(backup_id=full, backend=BackupStorage.FILESYSTEM, wait_for_completion=True)

    with pytest.raises(LookupError, match="does not hold"):
        await migration.check_backup(seeded_store, names, partial)
    with pytest.raises(LookupError, match="No successful"):
        await migration.check_backup(seeded_store, names, "no-such-backup")
    await migration.check_backup(seeded_store, names, full)


async def test_tenant_ids_are_collection_uuids(migration_store, legacy, ids, seeded_store, collection_names,
                                               tmp_path):
    await migration.backfill(migration_store, new_state(True), tmp_path / "run.json", execute=True)

    tenants = await migration_store.target_tenants()

    assert tenants == sorted([ids.col["chronicles"], ids.col["newspapers"]])
    assert all(str(UUID(t)) == t for t in tenants)
