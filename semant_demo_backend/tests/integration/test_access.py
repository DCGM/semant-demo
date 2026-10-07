"""Collection access rules over HTTP against the real test store (ADR 0007, #201).

Owner: everything in their collection. Shared user: read, annotations (incl. AI) and tag
definitions, but not membership, metadata, deletion or sharing. Anyone else: "not found".
Admins have no bypass except the explicit change-owner action. Denied requests must not
write or call a provider; each denial test checks the stored state afterwards.
"""
import pytest

pytestmark = pytest.mark.integration

NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}


# ── Reads ──────────────────────────────────────────────────────────────────

READS = [
    ("GET", "/api/user_collections/{c}", None),
    ("GET", "/api/user_collection/{c}/stats", None),
    ("GET", "/api/user_collection/{c}/documents", None),
    ("GET", "/api/collections/{c}/tags", None),
    ("GET", "/api/collections/{c}/members", None),
    ("GET", "/api/collections/{c}/documents/{d}", None),
    ("GET", "/api/collections/{c}/documents/{d}/stats", None),
    ("GET", "/api/collections/{c}/documents/{d}/chunks", None),
    ("GET", "/api/collections/{c}/documents/{d}/neighbour?direction=next&boundary_order=0", None),
    ("GET", "/api/documents/{d}/{c}/chunks", None),
    ("GET", "/api/documents/browse?collection_id={c}", None),
    ("GET", "/api/tag_spans?collection_id={c}", None),
    ("POST", "/api/tag_spans/batch", lambda i: {"chunk_ids": [i.chunk["chronicle_1"]], "collection_id": i.col["chronicles"]}),
    ("GET", "/api/tags/{t}", None),
    ("POST", "/api/search", lambda i: {"query": "Novák", "type": "text", "user_collection_id": i.col["chronicles"],
                                       "tag_uuids": [], "positive": False, "automatic": False, **NO_SUMMARY}),
]


# Known defect, not an access result: schemas.Document.author is a string but the store
# holds a list, so this endpoint fails with 500 for documents with authors (see
# docs/REFACTOR_STATUS.md). Allowed users must still not be denied.
KNOWN_BROKEN_READS = {"/api/documents/{d}/{c}/chunks"}  # #215


@pytest.mark.parametrize("user, expected", [
    ("owner", 200), ("annotator", 200), ("outsider", 404), ("admin", 404), (None, 401),
])
async def test_collection_reads(api_client, login, ids, user, expected):
    headers = await login(user)
    results = {}
    for method, path, body in READS:
        url = path.format(c=ids.col["chronicles"], d=ids.doc["chronicle"], t=ids.tag["person"])
        response = await api_client.request(method, url, headers=headers, json=body(ids) if body else None)
        results[path] = response.status_code

    if expected == 200:
        assert all(results[p] not in (401, 403, 404) for p in KNOWN_BROKEN_READS), results
        results = {p: code for p, code in results.items() if p not in KNOWN_BROKEN_READS}
    assert results == {p: expected for p in results}


async def test_unknown_or_malformed_ids_are_not_found(api_client, login):
    headers = await login("owner")

    assert (await api_client.get("/api/user_collections/not-a-uuid", headers=headers)).status_code == 404
    assert (await api_client.get("/api/user_collections/5e3a0000-0000-4000-8000-0000000c0fff",
                                 headers=headers)).status_code == 404


async def test_public_corpus_reads_stay_public(api_client, ids):
    assert (await api_client.get(f"/api/document/{ids.doc['chronicle']}")).status_code == 200
    assert (await api_client.get(f"/api/documents/{ids.doc['chronicle']}/chunks/count")).status_code == 200
    assert (await api_client.get("/api/documents/browse")).status_code == 200


async def test_span_reads_require_a_collection(api_client, login, ids):
    response = await api_client.get(f"/api/tag_spans?chunk_id={ids.chunk['chronicle_1']}",
                                    headers=await login("owner"))

    assert response.status_code == 422


async def test_shared_document_shows_only_annotations_of_the_requested_collection(api_client, login, ids, corpus):
    headers = await login("owner")

    in_newspapers = await api_client.get(f"/api/tag_spans?collection_id={ids.col['newspapers']}", headers=headers)

    assert {s["id"] for s in in_newspapers.json()} == {ids.span["pozar_manual"]}


# ── Membership: owner only ─────────────────────────────────────────────────

@pytest.mark.parametrize("user, expected", [("annotator", 403), ("outsider", 404), ("admin", 404)])
async def test_membership_changes_are_owner_only(api_client, login, ids, store, user, expected):
    headers = await login(user)
    c, gazette, chronicle = ids.col["chronicles"], ids.doc["gazette"], ids.doc["chronicle"]
    before = {k: await store.collections_of_chunk(v) for k, v in ids.chunk.items()}

    responses = [
        await api_client.post(f"/api/collections/{c}/documents/{gazette}", headers=headers),
        await api_client.delete(f"/api/collections/{c}/documents/{chronicle}", headers=headers),
        await api_client.post(f"/api/user_collection/{c}/chunks/{ids.chunk['gazette_2']}", headers=headers),
        await api_client.delete(f"/api/user_collection/{c}/chunks/{ids.chunk['chronicle_1']}", headers=headers),
    ]

    assert [r.status_code for r in responses] == [expected] * 4
    assert {k: await store.collections_of_chunk(v) for k, v in ids.chunk.items()} == before


async def test_owner_adds_and_removes_a_document(api_client, login, ids, store):
    headers = await login("owner")
    c, gazette = ids.col["chronicles"], ids.doc["gazette"]

    added = await api_client.post(f"/api/collections/{c}/documents/{gazette}", headers=headers)

    assert added.status_code == 200, added.text
    assert added.json()["outcome"] == "complete"
    assert set(added.json()["succeeded"]) == {ids.chunk["gazette_1"], ids.chunk["gazette_2"], gazette}
    assert c in await store.collections_of_chunk(ids.chunk["gazette_2"])
    assert c in await store.collections_of_document(gazette)

    removed = await api_client.delete(f"/api/collections/{c}/documents/{gazette}", headers=headers)

    assert removed.json()["outcome"] == "complete"
    assert c not in await store.collections_of_chunk(ids.chunk["gazette_1"])
    assert c not in await store.collections_of_document(gazette)


async def test_adding_a_document_twice_does_not_duplicate_links(api_client, login, ids, store):
    headers = await login("owner")
    c, chronicle = ids.col["newspapers"], ids.doc["chronicle"]

    for _ in range(2):
        response = await api_client.post(f"/api/collections/{c}/documents/{chronicle}", headers=headers)
        assert response.json()["outcome"] == "complete"

    assert (await store.collections_of_document(chronicle)).count(c) == 1


async def test_owner_adds_a_chunk_and_its_document(api_client, login, ids, store):
    c = ids.col["chronicles"]

    response = await api_client.post(f"/api/user_collection/{c}/chunks/{ids.chunk['gazette_2']}",
                                     headers=await login("owner"))

    assert response.json() == {"outcome": "complete", "succeeded": [ids.chunk["gazette_2"], ids.doc["gazette"]],
                               "failed": [], "unattempted": []}
    assert c in await store.collections_of_document(ids.doc["gazette"])


# ── Annotations: owner and shared users ───────────────────────────────────

async def test_shared_user_edits_annotations_without_changing_membership(api_client, login, ids, store):
    headers = await login("annotator")
    membership_before = await store.collections_of_chunk(ids.chunk["chronicle_2"])

    created = await api_client.post("/api/tag_spans", headers=headers, json={
        "start": 0, "end": 8, "type": "pos", "chunkId": ids.chunk["chronicle_2"], "tagId": ids.tag["place"]})
    span_id = created.json()["id"]
    patched = await api_client.patch(f"/api/tag_spans/{span_id}", headers=headers,
                                     json={"tagId": ids.tag["person"], "end": 9})
    bulk = await api_client.post("/api/tag_spans/bulk_update", headers=headers, json={
        "span_ids": [ids.span["lhota_automatic"], span_id], "update": {"type": "pos"}})
    deleted = await api_client.delete(f"/api/tag_spans/{span_id}", headers=headers)

    assert [created.status_code, patched.status_code, bulk.status_code, deleted.status_code] == [200, 200, 200, 204]
    assert bulk.json()["outcome"] == "complete"
    assert (await store.span(ids.span["lhota_automatic"]))["type"] == "pos"
    assert await store.span(span_id) is None
    assert await store.collections_of_chunk(ids.chunk["chronicle_2"]) == membership_before


async def test_shared_user_edits_tag_definitions(api_client, login, ids, store):
    headers = await login("annotator")
    c = ids.col["chronicles"]

    created = await api_client.post(f"/api/tags?collection_id={c}", headers=headers, json={
        "name": "Datum", "shorthand": "DA", "color": "#000000", "pictogram": "event", "definition": "Datum."})
    renamed = await api_client.patch(f"/api/tags/{created.json()['id']}", headers=headers, json={"name": "Letopočet"})
    deleted = await api_client.delete(f"/api/tags/{created.json()['id']}", headers=headers)

    assert [created.status_code, renamed.status_code, deleted.status_code] == [201, 200, 204]
    assert renamed.json()["name"] == "Letopočet"


@pytest.mark.parametrize("user", ["outsider", "admin"])
async def test_unrelated_users_cannot_touch_annotations_or_tags(api_client, login, ids, store, user):
    headers = await login(user)
    c, novak = ids.col["chronicles"], ids.span["novak_manual"]
    spans_before, novak_before = await store.span_count(), await store.span(novak)
    person_before = await store.tag(ids.tag["person"])

    responses = [
        await api_client.post("/api/tag_spans", headers=headers, json={
            "start": 0, "end": 4, "type": "pos", "chunkId": ids.chunk["chronicle_1"], "tagId": ids.tag["person"]}),
        await api_client.patch(f"/api/tag_spans/{novak}", headers=headers, json={"type": "neg"}),
        await api_client.post("/api/tag_spans/bulk_update", headers=headers,
                              json={"span_ids": [novak], "update": {"type": "neg"}}),
        await api_client.delete(f"/api/tag_spans/{novak}", headers=headers),
        await api_client.post("/api/tag_spans/in_document/delete", headers=headers, json={
            "collection_id": c, "document_id": ids.doc["chronicle"], "tag_ids": [ids.tag["person"]]}),
        await api_client.post("/api/ai/auto_spans/delete", headers=headers, json={
            "collection_id": c, "document_id": ids.doc["chronicle"], "tag_ids": [ids.tag["place"]]}),
        await api_client.post(f"/api/tags?collection_id={c}", headers=headers, json={
            "name": "X", "shorthand": "X", "color": "#000", "pictogram": "x", "definition": "x"}),
        await api_client.patch(f"/api/tags/{ids.tag['person']}", headers=headers, json={"name": "X"}),
        await api_client.delete(f"/api/tags/{ids.tag['person']}", headers=headers),
    ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert await store.span_count() == spans_before
    assert await store.span(novak) == novak_before
    assert await store.tag(ids.tag["person"]) == person_before


async def test_mixed_scope_batches_are_rejected_without_writes(api_client, login, ids, store):
    # The owner can annotate both collections, but one request must stay in one collection.
    headers = await login("owner")
    novak, pozar = ids.span["novak_manual"], ids.span["pozar_manual"]

    bulk = await api_client.post("/api/tag_spans/bulk_update", headers=headers,
                                 json={"span_ids": [novak, pozar], "update": {"type": "neg"}})
    foreign_tag = await api_client.patch(f"/api/tag_spans/{novak}", headers=headers,
                                         json={"tagId": ids.tag["event"]})
    # chronicle_3 belongs to the newspapers collection, the tag to chronicles.
    foreign_chunk = await api_client.post("/api/tag_spans", headers=headers, json={
        "start": 0, "end": 5, "type": "pos", "chunkId": ids.chunk["chronicle_3"], "tagId": ids.tag["person"]})

    assert [bulk.status_code, foreign_tag.status_code, foreign_chunk.status_code] == [404, 404, 404]
    assert (await store.span(novak))["type"] == "pos"
    assert (await store.span(pozar))["type"] == "pos"


# ── Collection metadata, deletion and sharing: owner only ─────────────────

@pytest.mark.parametrize("user, expected", [("annotator", 403), ("outsider", 404), ("admin", 404)])
async def test_metadata_deletion_and_sharing_are_owner_only(api_client, login, ids, store, user, expected):
    headers = await login(user)
    c = ids.col["chronicles"]
    before = await store.collection(c)

    responses = [
        await api_client.patch(f"/api/user_collections/{c}", headers=headers, json={"name": "Renamed"}),
        await api_client.post(f"/api/collections/{c}/share", headers=headers, json={"user_id": ids.user["outsider"]}),
        await api_client.delete(f"/api/collections/{c}/share/{ids.user['annotator']}", headers=headers),
        await api_client.delete(f"/api/collections/{c}", headers=headers),
    ]

    assert [r.status_code for r in responses] == [expected] * 4
    assert await store.collection(c) == before


async def test_owner_revokes_a_share(api_client, login, ids):
    c = ids.col["chronicles"]

    revoked = await api_client.delete(f"/api/collections/{c}/share/{ids.user['annotator']}",
                                      headers=await login("owner"))
    after = await api_client.get(f"/api/user_collections/{c}", headers=await login("annotator"))

    assert revoked.status_code == 200
    assert after.status_code == 404


async def test_admin_changes_owner_but_owner_cannot(api_client, login, ids, store):
    c = ids.col["newspapers"]
    body = {"user_id": ids.user["outsider"]}

    by_owner = await api_client.patch(f"/api/collections/{c}/owner", headers=await login("owner"), json=body)
    by_admin = await api_client.patch(f"/api/collections/{c}/owner", headers=await login("admin"), json=body)

    assert by_owner.status_code == 403
    assert by_admin.status_code == 200
    assert (await store.collection(c))["user_id"] == ids.user["outsider"]


# ── AI assistance ──────────────────────────────────────────────────────────

def suggest_body(ids, collection="chronicles", tags=("person",)):
    return {"collection_id": ids.col[collection], "document_id": ids.doc["chronicle"],
            "tag_ids": [ids.tag[t] for t in tags]}


@pytest.mark.parametrize("user", ["outsider", "admin"])
async def test_denied_ai_requests_make_no_provider_call(api_client, login, ids, store, fake_topicer, user):
    headers = await login(user)
    spans_before = await store.span_count()

    responses = [
        await api_client.post("/api/ai/suggest_spans/thorough", headers=headers, json=suggest_body(ids)),
        await api_client.post("/api/ai/suggest_spans/optimized", headers=headers, json=suggest_body(ids)),
        await api_client.post("/api/ai/suggest_spans/selection", headers=headers, json={
            **suggest_body(ids), "chunk_ids": [ids.chunk["chronicle_1"]], "selection_start": 0, "selection_end": 20}),
        await api_client.post("/api/ai/discuss_span", headers=headers, json={
            "span_id": ids.span["novak_manual"], "messages": [{"role": "user", "content": "Fits?"}]}),
    ]

    assert [r.status_code for r in responses] == [404] * 4
    assert fake_topicer == []
    assert await store.span_count() == spans_before


async def test_ai_scope_must_match_the_collection(api_client, login, ids, fake_topicer):
    headers = await login("owner")

    foreign_tag = await api_client.post("/api/ai/suggest_spans/thorough", headers=headers,
                                        json=suggest_body(ids, tags=("event",)))
    foreign_chunk = await api_client.post("/api/ai/suggest_spans/selection", headers=headers, json={
        **suggest_body(ids), "chunk_ids": [ids.chunk["chronicle_3"]], "selection_start": 0, "selection_end": 5})

    assert [foreign_tag.status_code, foreign_chunk.status_code] == [404, 404]
    assert fake_topicer == []


async def test_shared_user_runs_ai_suggestions(api_client, login, ids, store, fake_topicer):
    spans_before = await store.span_count()

    response = await api_client.post("/api/ai/suggest_spans/thorough", headers=await login("annotator"),
                                     json=suggest_body(ids))

    events = [__import__("json").loads(line) for line in response.text.splitlines()]
    saved = [s for e in events for s in e["spans"]]
    assert response.status_code == 200
    assert fake_topicer == ["topicer"]
    # "Jan Novák" occurs once in each chronicle chunk of the collection.
    assert sorted(s["chunkId"] for s in saved) == sorted([ids.chunk["chronicle_1"], ids.chunk["chronicle_2"]])
    assert all(e["unsaved"] == 0 and e["error"] is None for e in events)
    assert await store.span_count() == spans_before + 2


async def test_owner_removes_a_chunk(api_client, login, ids, store):
    c, chunk = ids.col["chronicles"], ids.chunk["chronicle_2"]

    response = await api_client.delete(f"/api/user_collection/{c}/chunks/{chunk}", headers=await login("owner"))

    assert response.status_code == 200, response.text
    assert c not in await store.collections_of_chunk(chunk)
