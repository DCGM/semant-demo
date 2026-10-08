"""Span mutations keep the chunk tag references used by tag-filtered search consistent (#204).

Contract (ADR 0004): a chunk references tag ``T`` through ``automaticTag`` /
``positiveTag`` / ``negativeTag`` exactly when at least one ``auto`` / ``pos`` / ``neg``
span with tag ``T`` is anchored on that chunk. Every test goes through the HTTP API and
checks the result with a real tag-filtered search and the stored references. The seeded
corpus satisfies the contract (see ``test_seeded_corpus_is_consistent``).
"""
import pytest
from weaviate.classes.query import QueryReference
from weaviate.collections.data.async_ import _DataCollectionAsync
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.adapters.weaviate import chunk_tags as chunk_tags_module
from semant_demo.adapters.weaviate.chunk_tags import ChunkTag, audit_chunk_tags, sync_chunk_tags
from semant_demo.maintenance.chunk_tag_audit import apply_report, build_report

pytestmark = pytest.mark.integration

NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}


@pytest.fixture
def search(api_client, login, ids):
    """Chunk ids a text search in "chronicles" returns for ``query`` filtered by ``tag``."""
    async def run(query, tag, *, positive=False, automatic=False):
        body = {"query": query, "type": "text", "user_collection_id": ids.col["chronicles"],
                "tag_uuids": [ids.tag[tag]], "positive": positive, "automatic": automatic, **NO_SUMMARY}
        response = await api_client.post("/api/search", headers=await login("owner"), json=body)
        assert response.status_code == 200, response.text
        return {r["id"] for r in response.json()["results"]}
    return run


@pytest.fixture
def chunk_refs(seeded_store, collection_names):
    """``{property: [tag ids]}`` of a chunk, duplicates kept."""
    async def read(chunk_id):
        obj = await seeded_store.collections.get(collection_names.chunks_collection_name).query.fetch_object_by_id(
            chunk_id, return_references=[QueryReference(link_on=p) for p in chunk_tags_module.CHUNK_TAG_REFS])
        out = {}
        for prop in chunk_tags_module.CHUNK_TAG_REFS:
            block = (obj.references or {}).get(prop)
            out[prop] = sorted(str(r.uuid) for r in (block.objects if block else []))
        return out
    return read


@pytest.fixture
def owner(login):
    async def headers():
        return await login("owner")
    return headers


async def create_span(api_client, headers, chunk, tag, start, end, type_="pos"):
    response = await api_client.post("/api/tag_spans", headers=headers, json={
        "chunkId": chunk, "tagId": tag, "start": start, "end": end, "type": type_})
    assert response.status_code == 200, response.text
    return response.json()


async def test_seeded_corpus_is_consistent(seeded_store, collection_names):
    assert await audit_chunk_tags(seeded_store, collection_names) == []


async def test_create_makes_the_chunk_findable_by_tag(api_client, owner, ids, search, chunk_refs):
    marie = ids.chunk["letters_1"]  # "Milá Marie, píši Ti z Prahy."
    assert await search("Marie", "person", positive=True) == set()

    result = await create_span(api_client, await owner(), marie, ids.tag["person"], 5, 10)

    assert result["outcome"] == "complete"
    assert result["succeeded"] == [result["id"]] and result["failed"] == []
    assert await search("Marie", "person", positive=True) == {marie}
    assert (await chunk_refs(marie))["positiveTag"] == [ids.tag["person"]]


async def test_created_suggestion_is_findable_as_automatic_only(api_client, owner, ids, search):
    marie = ids.chunk["letters_1"]
    await create_span(api_client, await owner(), marie, ids.tag["person"], 5, 10, "auto")

    assert await search("Marie", "person", automatic=True) == {marie}
    assert await search("Marie", "person", positive=True) == set()


async def test_approve_moves_the_chunk_from_automatic_to_positive(api_client, owner, ids, search, chunk_refs):
    chunk, lhota = ids.chunk["chronicle_1"], ids.span["lhota_automatic"]
    assert await search("Lhoty", "place", automatic=True) == {chunk}

    response = await api_client.patch(f"/api/tag_spans/{lhota}", headers=await owner(), json={"type": "pos"})

    assert response.status_code == 200 and response.json()["outcome"] == "complete"
    assert await search("Lhoty", "place", positive=True) == {chunk}
    assert await search("Lhoty", "place", automatic=True) == set()
    refs = await chunk_refs(chunk)
    assert (refs["positiveTag"], refs["automaticTag"]) == (sorted([ids.tag["person"], ids.tag["place"]]), [])


async def test_reject_removes_the_automatic_tag_and_records_the_negative(api_client, owner, ids, search, chunk_refs):
    chunk, praha = ids.chunk["letters_1"], ids.span["praha_automatic"]
    assert await search("Prahy", "place", automatic=True) == {chunk}

    response = await api_client.patch(f"/api/tag_spans/{praha}", headers=await owner(), json={"type": "neg"})

    assert response.json()["outcome"] == "complete"
    assert await search("Prahy", "place", automatic=True, positive=True) == set()
    assert await chunk_refs(chunk) == {"automaticTag": [], "positiveTag": [], "negativeTag": [ids.tag["place"]]}


async def test_delete_removes_the_searchable_tag(api_client, owner, ids, search, chunk_refs):
    chunk = ids.chunk["chronicle_1"]
    assert await search("Novák", "person", positive=True) == {chunk}

    response = await api_client.delete(f"/api/tag_spans/{ids.span['novak_manual']}", headers=await owner())

    assert response.status_code == 200
    assert response.json() == {"outcome": "complete", "succeeded": [ids.span["novak_manual"]],
                               "failed": [], "unattempted": []}
    assert await search("Novák", "person", positive=True) == set()
    assert (await chunk_refs(chunk))["positiveTag"] == []


async def test_tag_stays_while_another_span_backs_it_and_goes_with_the_last(api_client, owner, ids, search,
                                                                           chunk_refs):
    chunk, person = ids.chunk["chronicle_1"], ids.tag["person"]
    # A second approved "person" span on chronicle_1 ("hejtman"), next to novak_manual.
    second = await create_span(api_client, await owner(), chunk, person, 26, 33)
    assert (await chunk_refs(chunk))["positiveTag"] == [person]  # not added twice

    await api_client.delete(f"/api/tag_spans/{ids.span['novak_manual']}", headers=await owner())
    assert await search("Novák", "person", positive=True) == {chunk}
    assert (await chunk_refs(chunk))["positiveTag"] == [person]

    await api_client.delete(f"/api/tag_spans/{second['id']}", headers=await owner())
    assert await search("Novák", "person", positive=True) == set()
    assert (await chunk_refs(chunk))["positiveTag"] == []


async def test_approving_one_of_two_suggestions_keeps_the_automatic_tag(api_client, owner, ids, search):
    chunk, place = ids.chunk["chronicle_1"], ids.tag["place"]
    await create_span(api_client, await owner(), chunk, place, 69, 85, "auto")  # "U Zlatého jelena"

    await api_client.patch(f"/api/tag_spans/{ids.span['lhota_automatic']}", headers=await owner(), json={"type": "pos"})

    assert await search("Lhoty", "place", automatic=True) == {chunk}
    assert await search("Lhoty", "place", positive=True) == {chunk}


async def test_tag_reassignment_moves_the_chunk_tag(api_client, owner, ids, search, chunk_refs):
    chunk, novak = ids.chunk["chronicle_1"], ids.span["novak_manual"]

    response = await api_client.patch(f"/api/tag_spans/{novak}", headers=await owner(),
                                      json={"tagId": ids.tag["place"]})

    assert response.json()["outcome"] == "complete"
    assert await search("Novák", "person", positive=True) == set()
    # chronicle_2 also contains "Novák" and was already tagged "place" (brno_manual).
    assert await search("Novák", "place", positive=True) == {chunk, ids.chunk["chronicle_2"]}
    refs = await chunk_refs(chunk)
    assert (refs["positiveTag"], refs["automaticTag"]) == ([ids.tag["place"]], [ids.tag["place"]])


async def test_offset_change_keeps_the_chunk_tag(api_client, owner, ids, search):
    await api_client.patch(f"/api/tag_spans/{ids.span['novak_manual']}", headers=await owner(),
                           json={"start": 38})

    assert await search("Novák", "person", positive=True) == {ids.chunk["chronicle_1"]}


async def test_bulk_approve_updates_every_chunk(api_client, owner, ids, search, chunk_refs):
    spans = [ids.span["lhota_automatic"], ids.span["praha_automatic"]]

    result = (await api_client.post("/api/tag_spans/bulk_update", headers=await owner(),
                                    json={"span_ids": spans, "update": {"type": "pos"}})).json()

    assert result["outcome"] == "complete"
    assert await search("Lhoty Prahy", "place", automatic=True) == set()
    assert await search("Lhoty Prahy", "place", positive=True) == {ids.chunk["chronicle_1"], ids.chunk["letters_1"]}
    assert (await chunk_refs(ids.chunk["letters_1"]))["positiveTag"] == [ids.tag["place"]]


async def test_scoped_delete_of_approved_spans_removes_their_tags(api_client, owner, ids, search, chunk_refs):
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["chronicle"],
            "tag_ids": [ids.tag["place"]]}

    result = (await api_client.post("/api/tag_spans/in_document/delete", headers=await owner(), json=body)).json()

    assert result["outcome"] == "complete" and result["succeeded"] == [ids.span["brno_manual"]]
    assert await search("Brně", "place", positive=True) == set()
    # The unresolved suggestion on chronicle_1 is not deleted and keeps its tag.
    assert (await chunk_refs(ids.chunk["chronicle_1"]))["automaticTag"] == [ids.tag["place"]]


async def test_deleting_suggestions_removes_automatic_tags(api_client, owner, ids, search):
    body = {"collection_id": ids.col["chronicles"], "document_id": ids.doc["letters"],
            "tag_ids": [ids.tag["place"]]}

    result = (await api_client.post("/api/ai/auto_spans/delete", headers=await owner(), json=body)).json()

    assert result["outcome"] == "complete" and result["succeeded"] == [ids.span["praha_automatic"]]
    assert await search("Prahy", "place", automatic=True) == set()


# ── Failures of the chunk tag write (ADR 0002) ───────────────────────────


async def test_failed_chunk_tag_write_on_create_is_partial_and_a_resave_fixes_it(
        api_client, owner, ids, search, store, fail_writes, monkeypatch):
    marie = ids.chunk["letters_1"]
    fail_writes("reference_add", [marie], collection="Chunks")

    result = await create_span(api_client, await owner(), marie, ids.tag["person"], 5, 10)

    assert result["outcome"] == "partial"
    assert result["succeeded"] == [result["id"]]
    assert [(f["item_id"], f["step"]) for f in result["failed"]] == [
        (f"{marie}:{ids.tag['person']}", "update_chunk_tags")]
    assert await store.span(result["id"]) is not None  # the span is kept
    assert await search("Marie", "person", positive=True) == set()

    # Saving the span again re-derives its chunk tag.
    monkeypatch.undo()
    again = await api_client.patch(f"/api/tag_spans/{result['id']}", headers=await owner(), json={"type": "pos"})
    assert again.json()["outcome"] == "complete"
    assert await search("Marie", "person", positive=True) == {marie}


async def test_offset_only_resave_repairs_a_failed_chunk_tag_write(
        api_client, owner, ids, search, store, chunk_refs, fail_writes, monkeypatch):
    marie, person = ids.chunk["letters_1"], ids.tag["person"]
    fail_writes("reference_add", [marie], collection="Chunks")

    created = await create_span(api_client, await owner(), marie, person, 5, 10)
    assert created["outcome"] == "partial"
    assert await store.span(created["id"]) is not None
    assert await search("Marie", "person", positive=True) == set()

    # While the reference write still fails, an offset-only save reports it, not "complete".
    still_failing = (await api_client.patch(f"/api/tag_spans/{created['id']}", headers=await owner(),
                                            json={"end": 9})).json()
    assert still_failing["outcome"] == "partial"
    assert [f["step"] for f in still_failing["failed"]] == ["update_chunk_tags"]

    monkeypatch.undo()
    repaired = (await api_client.patch(f"/api/tag_spans/{created['id']}", headers=await owner(),
                                       json={"start": 4, "end": 10})).json()

    assert repaired["outcome"] == "complete" and repaired["failed"] == []
    assert (repaired["start"], repaired["end"], repaired["type"]) == (4, 10, "pos")
    assert (await chunk_refs(marie))["positiveTag"] == [person]
    assert await search("Marie", "person", positive=True) == {marie}


async def test_failed_chunk_tag_write_on_delete_is_partial(api_client, owner, ids, store, chunk_refs, fail_writes):
    chunk, novak = ids.chunk["chronicle_1"], ids.span["novak_manual"]
    fail_writes("reference_delete", [chunk], collection="Chunks")

    result = (await api_client.delete(f"/api/tag_spans/{novak}", headers=await owner())).json()

    assert result["outcome"] == "partial"
    assert result["succeeded"] == [novak]
    assert [f["step"] for f in result["failed"]] == ["update_chunk_tags"]
    assert await store.span(novak) is None
    # Left for the audit to report; it is not repaired in the background.
    assert ids.tag["person"] in (await chunk_refs(chunk))["positiveTag"]


async def test_chunk_tags_follow_a_timed_out_update_that_was_applied(api_client, owner, ids, search, store,
                                                                     monkeypatch):
    lhota = ids.span["lhota_automatic"]
    original = _DataCollectionAsync.update

    async def applied_then_timeout(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise WeaviateTimeoutError("timed out")
    monkeypatch.setattr(_DataCollectionAsync, "update", applied_then_timeout)

    response = await api_client.patch(f"/api/tag_spans/{lhota}", headers=await owner(), json={"type": "pos"})

    assert response.status_code == 500
    assert (await store.span(lhota))["type"] == "pos"
    assert await search("Lhoty", "place", positive=True) == {ids.chunk["chronicle_1"]}
    assert await search("Lhoty", "place", automatic=True) == set()


async def test_failed_span_read_is_a_failure_not_absence(seeded_store, collection_names, ids, chunk_refs, monkeypatch):
    async def unreadable(*args, **kwargs):
        raise RuntimeError("injected read failure")
    monkeypatch.setattr(chunk_tags_module, "required_refs", unreadable)
    pair = ChunkTag.of(ids.chunk["chronicle_1"], ids.tag["person"])

    done, failed = await sync_chunk_tags(seeded_store, collection_names, [pair])

    assert done == [] and [f.step for f in failed] == ["update_chunk_tags"]
    assert ids.tag["person"] in (await chunk_refs(ids.chunk["chronicle_1"]))["positiveTag"]


# ── Audit and cleanup of existing data ──────────────────────────────────


async def test_audit_reports_and_cleanup_removes_only_unbacked_references(
        seeded_store, collection_names, ids, chunk_refs):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name).data
    c1, c3 = ids.chunk["chronicle_1"], ids.chunk["chronicle_3"]
    # Unbacked: "event" on chronicle_1 (twice), "place" as negative on chronicle_3.
    for _ in range(2):
        await chunks.reference_add(from_uuid=c1, from_property="positiveTag", to=ids.tag["event"])
    await chunks.reference_add(from_uuid=c3, from_property="negativeTag", to=ids.tag["place"])
    # Missing: the reference of praha_automatic.
    await chunks.reference_delete(from_uuid=ids.chunk["letters_1"], from_property="automaticTag", to=ids.tag["place"])

    report = await build_report(seeded_store, collection_names, "test")

    assert report["counts"] == {"missing:automaticTag": 1, "unbacked:negativeTag": 1, "unbacked:positiveTag": 1}
    assert {(i["chunk_id"], i["tag_id"], i["kind"]) for i in report["issues"]} == {
        (c1, ids.tag["event"], "unbacked"), (c3, ids.tag["place"], "unbacked"),
        (ids.chunk["letters_1"], ids.tag["place"], "missing")}

    result = await apply_report(seeded_store, collection_names, report, remove_unbacked=True, add_missing=False)

    assert result == {"corrected_pairs": 2, "failed": []}
    assert await chunk_refs(c1) == {"positiveTag": [ids.tag["person"]], "automaticTag": [ids.tag["place"]],
                                    "negativeTag": []}
    assert await chunk_refs(c3) == {"positiveTag": [ids.tag["event"]], "automaticTag": [], "negativeTag": []}
    # Not selected: the missing reference is still missing.
    assert [i["kind"] for i in (await build_report(seeded_store, collection_names, "test"))["issues"]] == ["missing"]

    await apply_report(seeded_store, collection_names, report, remove_unbacked=False, add_missing=True)
    assert await audit_chunk_tags(seeded_store, collection_names) == []


async def test_cleanup_rechecks_and_keeps_a_reference_backed_since_the_audit(
        api_client, owner, seeded_store, collection_names, ids, chunk_refs):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name).data
    marie = ids.chunk["letters_1"]
    await chunks.reference_add(from_uuid=marie, from_property="positiveTag", to=ids.tag["person"])
    report = await build_report(seeded_store, collection_names, "test")
    assert report["counts"] == {"unbacked:positiveTag": 1}

    await create_span(api_client, await owner(), marie, ids.tag["person"], 5, 10)
    await apply_report(seeded_store, collection_names, report, remove_unbacked=True, add_missing=False)

    assert (await chunk_refs(marie))["positiveTag"] == [ids.tag["person"]]
