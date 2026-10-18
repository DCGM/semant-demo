"""Audit and deletion of documents without chunks against the real test store (#281).

The fixture corpus documents all have chunks; documents without chunks are added, alone, in
one or two of its collections, and with a reference to a collection deleted directly.
The test store has no backup module, so the backup listing is replaced.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.adapters.weaviate import document_cleanup as store
from semant_demo.maintenance.document_cleanup import (
    audit, audit_exit_code, candidates_path, delete, delete_exit_code, read_lines, resolve_targets)

pytestmark = pytest.mark.integration


async def annotation_count(client, names) -> int:
    """Spans in all annotation tenants."""
    annotations = client.collections.get(names.annotation_collection_name)
    return sum([(await annotations.with_tenant(t).aggregate.over_all(total_count=True)).total_count
                for t in await annotations.tenants.get()])

LONELY, MEMBER, TWO, DANGLING = (UUID(f"5e3a0000-0000-4000-8000-0000000de00{n}") for n in range(1, 5))
MISSING_COLLECTION = UUID("5e3a0000-0000-4000-8000-0000000c0099")


async def test_audit_and_delete_documents_without_chunks(seeded_store, collection_names, corpus, collections,
                                                         tmp_path, monkeypatch):
    c = {k: UUID(v["id"]) for k, v in corpus.collections.items()}
    user_collections = seeded_store.collections.get(collection_names.user_collection_name)
    await user_collections.data.insert(uuid=MISSING_COLLECTION, properties={"name": "Deleted later"})
    inserted = await seeded_store.collections.get(collection_names.document_collection_name).data.insert_many([
        DataObject(uuid=LONELY, properties={"title": "No text"}),
        DataObject(uuid=MEMBER, properties={"title": "Listed"}, references={"collection": [c["chronicles"]]}),
        DataObject(uuid=TWO, properties={"title": "Listed twice"},
                   references={"collection": [c["chronicles"], c["newspapers"]]}),
        DataObject(uuid=DANGLING, properties={"title": "Lost collection"}, references={"collection": [MISSING_COLLECTION]}),
    ])
    assert not inserted.errors
    await user_collections.data.delete_by_id(MISSING_COLLECTION)  # leaves the reference dangling
    before = {k: await collections.read_collection_stats(i) for k, i in c.items()}
    tags_before = await store.total_count(seeded_store, collection_names.tag_collection_name)
    spans_before = await annotation_count(seeded_store, collection_names)
    checkpoint = tmp_path / "audit.json"

    summary = await audit(seeded_store, collection_names, checkpoint=checkpoint, endpoint="test",
                          min_age=timedelta(0), progress=lambda line: None)

    assert summary["counts"] == {"has_chunks": 3, "no_chunks_unreferenced": 2, "no_chunks_collection_member": 2,
                                 "unknown_or_error": 0, "excluded_recent": 0, "excluded_other_reference": 0}
    assert summary["probe"]["documents_checked"] == 3 and summary["dependencies"] == []
    assert summary["collection_memberships"] == {
        "candidates_in_collections": 2, "memberships": 3, "candidates_in_several_collections": 1,
        "affected_collections": 2, "missing_collections": 0}
    lines = read_lines(candidates_path(checkpoint))
    # a reference to a missing collection is not resolved: the document reads as unreferenced
    assert lines[str(DANGLING)]["category"] == "no_chunks_unreferenced"
    assert lines[str(TWO)]["collection_ids"] == sorted(str(c[k]) for k in ("chronicles", "newspapers"))
    assert audit_exit_code(summary) == 0

    async def backups(client):
        return [store.Backup("b", "SUCCESS", (collection_names.document_collection_name,
                                              collection_names.chunks_collection_name,
                                              collection_names.user_collection_name),
                             datetime.now(timezone.utc) + timedelta(minutes=1), None)]
    monkeypatch.setattr(store, "filesystem_backups", backups)
    result = await delete(seeded_store, collection_names, audit_checkpoint=checkpoint, endpoint="test",
                          backup_id="b", progress=lambda line: None)

    assert result["counts"]["deleted"] == 4 and delete_exit_code(result) == 0
    assert result["collections_check"] == {"affected_collections": 2, "missing_collections": 0,
                                           "still_listing_deleted": 0, "count_matches": 2, "count_differs": 0,
                                           "count_unknown": 0}
    documents = collection_names.document_collection_name
    assert await store.existing_ids(seeded_store, documents, [LONELY, MEMBER, TWO, DANGLING]) == set()
    assert await store.total_count(seeded_store, documents) == 3
    for key, collection_id in c.items():
        stats = await collections.read_collection_stats(collection_id)
        removed = {"chronicles": 2, "newspapers": 1}.get(key, 0)
        assert stats.documents_count == before[key].documents_count - removed
        assert (stats.chunks_count, stats.annotations_count) == (before[key].chunks_count,
                                                                 before[key].annotations_count)
        listed = {d.id for d in await collections.read_all_documents(collection_id)}
        assert not listed & {LONELY, MEMBER, TWO, DANGLING}
    assert await store.total_count(seeded_store, collection_names.tag_collection_name) == tags_before
    assert await annotation_count(seeded_store, collection_names) == spans_before


async def test_aliases_are_resolved_like_the_deployment(seeded_store, collection_names):
    """Production serves ``Documents`` etc. as aliases of ``*_test`` collections."""
    aliased = collection_names.model_copy(update={
        "document_collection_name": "CleanupDocumentsAlias", "chunks_collection_name": "CleanupChunksAlias"})
    await seeded_store.alias.create(alias_name="CleanupDocumentsAlias",
                                    target_collection=collection_names.document_collection_name)
    await seeded_store.alias.create(alias_name="CleanupChunksAlias",
                                    target_collection=collection_names.chunks_collection_name)
    try:
        targets, _ = await resolve_targets(seeded_store, aliased)
    finally:
        await seeded_store.alias.delete(alias_name="CleanupDocumentsAlias")
        await seeded_store.alias.delete(alias_name="CleanupChunksAlias")
    assert (targets.documents, targets.chunks) == (collection_names.document_collection_name,
                                                   collection_names.chunks_collection_name)
