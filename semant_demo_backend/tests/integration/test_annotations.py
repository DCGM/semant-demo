"""Annotations feature against real Weaviate (#206).

Offsets (cross-chunk, Unicode, gaps) and reload of persisted spans, the tag-creation
failure policy, and tag and collection deletion that stops part way. Faults are injected into real Weaviate writes
(``fail_writes``); every test checks the stored state as well as the response.
"""
import pytest
from weaviate.classes.query import Filter
from weaviate.exceptions import WeaviateTimeoutError

from semant_demo.features.annotations.offsets import text_length

pytestmark = pytest.mark.integration


def span_body(ids, chunk, start, end, tag="person", type_="pos"):
    return {"chunkId": ids.chunk[chunk], "tagId": ids.tag[tag], "start": start, "end": end, "type": type_}


async def spans_of(api_client, headers, ids, chunk, collection="chronicles"):
    response = await api_client.get("/api/tag_spans", headers=headers,
                                    params={"collection_id": ids.col[collection], "chunk_id": ids.chunk[chunk]})
    assert response.status_code == 200, response.text
    return {s["id"]: s for s in response.json()}


async def count(seeded_store, name):
    return (await seeded_store.collections.get(name).aggregate.over_all(total_count=True)).total_count


# ── Offsets and reload ────────────────────────────────────────────────────

async def test_cross_chunk_span_is_saved_and_reloads_with_its_offsets(api_client, login, ids, corpus):
    owner = await login("owner")
    first = len(corpus.chunks["chronicle_1"]["text"])  # 86, ASCII and precomposed letters only

    response = await api_client.post("/api/tag_spans", headers=owner, json=span_body(ids, "chronicle_1", 80, first + 8))

    assert response.status_code == 200, response.text
    created = response.json()
    assert created["outcome"] == "complete"
    reloaded = (await spans_of(api_client, owner, ids, "chronicle_1"))[created["id"]]
    assert (reloaded["start"], reloaded["end"], reloaded["type"]) == (80, first + 8, "pos")


async def test_span_may_continue_into_a_chunk_outside_the_collection(api_client, login, ids, corpus):
    # chronicle_3 is not in "chronicles", but it follows chronicle_2 in the document.
    total = sum(len(corpus.chunks[k]["text"]) for k in ("chronicle_1", "chronicle_2", "chronicle_3"))
    owner = await login("owner")

    inside = await api_client.post("/api/tag_spans", headers=owner, json=span_body(ids, "chronicle_1", 80, total))
    beyond = await api_client.post("/api/tag_spans", headers=owner, json=span_body(ids, "chronicle_1", 80, total + 1))

    assert inside.status_code == 200, inside.text
    assert beyond.status_code == 400
    assert beyond.json()["detail"] == "Span ends after the end of the document's text"


async def test_offsets_are_utf16_units(api_client, login, ids, corpus, store):
    # "… Tvůj Karel 😀": the emoji is one code point but two UTF-16 units.
    text = corpus.chunks["letters_2"]["text"]
    start, units = text.index("Karel"), text_length(text)
    assert units == len(text) + 1
    owner, spans_before = await login("owner"), await store.span_count()

    ok = await api_client.post("/api/tag_spans", headers=owner, json=span_body(ids, "letters_2", start, units))
    too_long = await api_client.post("/api/tag_spans", headers=owner,
                                     json=span_body(ids, "letters_2", start, units + 1))

    assert ok.status_code == 200, ok.text
    assert too_long.status_code == 400
    assert await store.span_count() == spans_before + 1


async def test_span_cannot_cross_a_gap_in_chunk_order(api_client, login, ids, corpus, seeded_store,
                                                      collection_names, store):
    # A later chunk of "letters" with order 3: order 2 is missing.
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    template = corpus.chunks["letters_2"]
    await chunks.data.insert(
        properties={"text": "Dodatek.", "title": "", "order": 3, "language": "ces",
                    "start_page_id": template["start_page_id"], "from_page": 3, "to_page": 3},
        references={"document": corpus.documents["letters"]["id"]})
    owner, spans_before = await login("owner"), await store.span_count()
    end = text_length(template["text"]) + 2

    response = await api_client.post("/api/tag_spans", headers=owner, json=span_body(ids, "letters_2", 0, end))

    assert response.status_code == 400
    assert response.json()["detail"] == "Span crosses a gap between the document's chunks"
    assert await store.span_count() == spans_before


@pytest.mark.parametrize("start, end", [(-1, 4), (5, 5), (86, 90)], ids=["negative", "empty", "start-after-chunk"])
async def test_invalid_offsets_are_rejected(api_client, login, ids, store, start, end):
    spans_before = await store.span_count()

    response = await api_client.post("/api/tag_spans", headers=await login("annotator"),
                                     json=span_body(ids, "chronicle_1", start, end))

    assert response.status_code == 400
    assert await store.span_count() == spans_before


async def test_invalid_offset_patch_leaves_the_span_unchanged(api_client, login, ids, store):
    novak = ids.span["novak_manual"]
    before = await store.span(novak)

    response = await api_client.patch(f"/api/tag_spans/{novak}", headers=await login("owner"),
                                      params={"collection_id": ids.col["chronicles"]}, json={"end": 1000})

    assert response.status_code == 400
    assert await store.span(novak) == before


async def test_approval_and_rejection_reload_from_storage(api_client, login, ids):
    annotator = await login("annotator")
    c = {"collection_id": ids.col["chronicles"]}
    lhota = ids.span["lhota_automatic"]
    approve = await api_client.patch(f"/api/tag_spans/{lhota}", headers=annotator, params=c, json={"type": "pos"})
    praha = ids.span["praha_automatic"]
    reject = await api_client.patch(f"/api/tag_spans/{praha}", headers=annotator, params=c, json={"type": "neg"})

    assert (approve.status_code, reject.status_code) == (200, 200)
    assert (await spans_of(api_client, annotator, ids, "chronicle_1"))[lhota]["type"] == "pos"
    reloaded = (await spans_of(api_client, annotator, ids, "letters_1"))[praha]
    # The AI reason is kept with a rejected suggestion.
    assert (reloaded["type"], reloaded["reason"]) == ("neg", "Název města.")


async def test_a_span_moved_to_another_chunk_keeps_its_id_and_both_chunks_follow(
        api_client, login, ids, seeded_store, collection_names):
    # "Jan Novák" on chronicle_1 moved to the same name on chronicle_2 (#436): one PATCH.
    novak, first, second = ids.span["novak_manual"], ids.chunk["chronicle_1"], ids.chunk["chronicle_2"]
    owner = await login("owner")
    c = {"collection_id": ids.col["chronicles"]}

    response = await api_client.patch(f"/api/tag_spans/{novak}", headers=owner, params=c,
                                      json={"chunkId": second, "start": 51, "end": 60})

    assert response.status_code == 200, response.text
    assert (response.json()["id"], response.json()["outcome"]) == (novak, "complete")
    assert novak not in await spans_of(api_client, owner, ids, "chronicle_1")
    moved = (await spans_of(api_client, owner, ids, "chronicle_2"))[novak]
    assert (moved["start"], moved["end"], moved["type"]) == (51, 60, "pos")
    # The statistics' collection filter follows the new anchor chunk.
    tenant = seeded_store.collections.get(collection_names.annotation_collection_name).with_tenant(ids.col["chronicles"])
    for chunk, expected in ((second, True), (first, False)):
        anchored = await tenant.query.fetch_objects(filters=Filter.by_ref("text_chunk").by_id().equal(chunk))
        assert (novak in {str(o.uuid) for o in anchored.objects}) is expected


# ── Tag creation: insert, then link to the collection ─────────────────────

NEW_TAG = {"name": "Instituce", "shorthand": "IN", "color": "#123456", "pictogram": "bank",
           "definition": "Úřad nebo spolek."}


async def test_collection_tags_are_listed_by_name(api_client, login, ids):
    owner = await login("owner")
    # Created out of name order: Weaviate alone would list them as written (#348).
    for name, shorthand in (("Zámek", "ZA"), ("archiv", "AR")):
        response = await api_client.post("/api/tags", headers=owner, params={"collection_id": ids.col["chronicles"]},
                                         json={**NEW_TAG, "name": name, "shorthand": shorthand})
        assert response.status_code == 201, response.text

    listed = await api_client.get(f"/api/user_collections/{ids.col['chronicles']}/tags", headers=owner)

    assert [t["name"] for t in listed.json()] == ["archiv", "Místo", "Osoba", "Zámek"]


async def test_tag_whose_collection_link_fails_is_removed(api_client, login, ids, seeded_store,
                                                          collection_names, fail_writes):
    tag_collection = collection_names.tag_collection_name
    tags_before = await count(seeded_store, tag_collection)
    fail_writes("reference_add", collection=tag_collection)

    response = await api_client.post("/api/tags", headers=await login("owner"),
                                     params={"collection_id": ids.col["chronicles"]}, json=NEW_TAG)

    assert response.status_code == 500
    body = response.json()
    assert (body["step"], body["completed"], body["uncertain"]) == ("link_collection", {}, False)
    assert "nothing was saved" in body["detail"]
    assert await count(seeded_store, tag_collection) == tags_before


async def test_tag_that_cannot_be_removed_after_a_failed_link_is_reported(
        api_client, login, ids, seeded_store, collection_names, fail_writes):
    tag_collection = collection_names.tag_collection_name
    tags_before = await count(seeded_store, tag_collection)
    fail_writes("reference_add", collection=tag_collection)
    fail_writes("delete_by_id", collection=tag_collection)

    response = await api_client.post("/api/tags", headers=await login("owner"),
                                     params={"collection_id": ids.col["chronicles"]}, json=NEW_TAG)

    assert response.status_code == 500
    body = response.json()
    assert (body["step"], body["completed"], body["uncertain"]) == ("delete_unlinked_tag", {"insert_tag": 1}, False)
    assert "may remain" in body["detail"]
    assert await count(seeded_store, tag_collection) == tags_before + 1


async def test_timed_out_cleanup_after_a_failed_link_is_reported_as_uncertain(
        api_client, login, ids, seeded_store, collection_names, fail_writes):
    tag_collection = collection_names.tag_collection_name
    tags_before = await count(seeded_store, tag_collection)
    fail_writes("reference_add", collection=tag_collection)
    fail_writes("delete_by_id", collection=tag_collection, error=WeaviateTimeoutError("timed out"))

    response = await api_client.post("/api/tags", headers=await login("owner"),
                                     params={"collection_id": ids.col["chronicles"]}, json=NEW_TAG)

    assert response.status_code == 500
    body = response.json()
    assert (body["step"], body["uncertain"], body["completed"]) == ("delete_unlinked_tag", True, {"insert_tag": 1})
    assert "could not be added to the collection" in body["detail"] and "link_collection failed" in body["detail"]
    assert "may remain" in body["detail"]
    assert await count(seeded_store, tag_collection) == tags_before + 1  # the injected timeout deleted nothing


async def test_creating_the_tag_again_after_a_failed_link_succeeds(api_client, login, ids, collection_names,
                                                                    fail_writes, monkeypatch):
    owner = await login("owner")
    fail_writes("reference_add", collection=collection_names.tag_collection_name)
    first = await api_client.post("/api/tags", headers=owner, params={"collection_id": ids.col["chronicles"]},
                                  json=NEW_TAG)
    monkeypatch.undo()

    second = await api_client.post("/api/tags", headers=owner, params={"collection_id": ids.col["chronicles"]},
                                   json=NEW_TAG)

    assert (first.status_code, second.status_code) == (500, 201)
    listed = await api_client.get(f"/api/user_collections/{ids.col['chronicles']}/tags", headers=owner)
    assert [t["name"] for t in listed.json()].count("Instituce") == 1


# ── Deletion that stops part way ──────────────────────────────────────────

async def test_tag_deletion_failing_part_way_keeps_completed_steps_and_can_be_repeated(
        api_client, login, ids, store, collection_names, fail_writes, monkeypatch):
    place, brno = ids.tag["place"], ids.span["brno_manual"]
    fail_writes("delete_many", collection=collection_names.annotation_collection_name)
    owner = await login("owner")

    response = await api_client.delete(f"/api/tags/{place}", headers=owner)

    assert response.status_code == 500
    body = response.json()
    assert body["step"] == "delete_span"
    # Chunks hold no tag references to unlink (#733, ADR 0013): the spans are the first step.
    assert "unlink_chunk_tag" not in body["completed"]
    assert "deleting the tag again continues" in body["detail"]
    assert await store.tag(place) is not None
    assert await store.span(brno) is not None

    monkeypatch.undo()
    retry = await api_client.delete(f"/api/tags/{place}", headers=owner)

    assert retry.status_code == 204
    assert await store.tag(place) is None
    assert await store.span(brno) is None


async def test_collection_deletion_failing_part_way_keeps_completed_steps_and_can_be_repeated(
        api_client, login, ids, store, collection_names, fail_writes, monkeypatch):
    newspapers, event = ids.col["newspapers"], ids.tag["event"]
    fail_writes("delete_by_id", [event], collection=collection_names.tag_collection_name)
    owner = await login("owner")

    response = await api_client.delete(f"/api/user_collections/{newspapers}", headers=owner)

    assert response.status_code == 500
    body = response.json()
    assert body["step"] == "delete_tag"
    assert body["completed"]["unlink_chunk"] >= 1 and "delete_annotation_tenant" not in body["completed"]
    assert await store.collection(newspapers) is not None
    assert newspapers not in await store.collections_of_chunk(ids.chunk["chronicle_3"])
    # The tenant (with the spans of all tags) is removed after the tags.
    assert await store.span(ids.span["pozar_manual"], newspapers) is not None

    monkeypatch.undo()
    retry = await api_client.delete(f"/api/user_collections/{newspapers}", headers=owner)

    assert retry.status_code == 204
    assert await store.collection(newspapers) is None
    assert await store.tag(event) is None
    assert newspapers not in await store.tenants()
