"""The document access rule (#279, ADR 0007) over HTTP against the real test store.

``Documents.public`` true: readable by anyone without a collection. ``false`` (restricted) and
no value (unknown): readable only through a collection the user can read that holds the
document, also for signed-in users; then with all its chunks. Each test makes ``letters``
restricted and ``gazette`` unknown (``rights``); ``chronicle`` stays public. Fixture membership:
``chronicles`` (owner, shared with annotator) holds chronicle and letters; ``newspapers``
(owner) holds chronicle and gazette; ``outsider_notes`` (outsider) holds gazette.
"""
import pytest

from semant_demo.adapters.weaviate.search import ChunkSearchRepository

pytestmark = pytest.mark.integration

EVERY_WORD = "Novák Požár Prahy rodinu Slavia trh"
"""A text query each fixture chunk matches some word of."""


@pytest.fixture
async def rights(seeded_store, collection_names, ids):
    """letters restricted (``public`` false), gazette unknown (no value)."""
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    await documents.data.update(uuid=ids.doc["letters"], properties={"public": False})
    await documents.data.update(uuid=ids.doc["gazette"], properties={"public": None})
    stored = {key: (await documents.query.fetch_object_by_id(ids.doc[key], return_properties=["public"]))
              .properties.get("public") for key in ("chronicle", "letters", "gazette")}
    assert stored == {"chronicle": True, "letters": False, "gazette": None}


def _keys(ids, values):
    by_id = {v: k for section in (ids.doc, ids.chunk) for k, v in section.items()}
    return {by_id[v] for v in values}


async def _passages(api_client, headers, collection=None, text=EVERY_WORD):
    body = {"criteria": {"text_query": text}, "type": "text", "limit": 50}
    if collection:
        body["user_collection_id"] = collection
    response = await api_client.post("/api/search/passages", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _documents(api_client, headers, collection=None, text=None):
    body = {"criteria": {"text_query": text} if text else {}, "type": "text", "limit": 50}
    if collection:
        body["user_collection_id"] = collection
    response = await api_client.post("/api/search/documents", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _document_reads(ids, key, collection=None):
    """Every document read surface for document ``key`` (its first chunk as the anchor)."""
    d, c = ids.doc[key], ids.chunk[f"{key}_1"]
    scope = f"collection_id={collection}&" if collection else ""
    return [f"/api/document/{d}?{scope}",
            f"/api/documents/{d}/chunks/{c}/window?{scope}",
            f"/api/documents/{d}/chunks/{c}/adjacent?{scope}direction=after",
            f"/api/documents/{d}/chunks/by_page?{scope}page=1",
            f"/api/documents/{d}/pages?{scope}"]


@pytest.mark.parametrize("user", [None, "owner", "annotator", "outsider"])
async def test_without_a_collection_only_public_documents_are_readable(api_client, login, ids, rights, user):
    """Also for the owner of the collections that hold the restricted documents."""
    headers = await login(user)

    for key in ("letters", "gazette"):
        for path in _document_reads(ids, key):
            assert (await api_client.get(path, headers=headers)).status_code == 404, path
        count = await api_client.get(f"/api/documents/{ids.doc[key]}/chunks/count", headers=headers)
        assert count.json() == 0  # not confirmed: as for an unknown document
    for path in _document_reads(ids, "chronicle"):
        assert (await api_client.get(path, headers=headers)).status_code == 200, path

    browse = (await api_client.get("/api/documents/browse", headers=headers)).json()
    passages = await _passages(api_client, headers)
    documents = await _documents(api_client, headers)
    ranked = await _documents(api_client, headers, text=EVERY_WORD)
    legacy = await api_client.post("/api/search", headers=headers, json={
        "query": EVERY_WORD, "type": "text", "limit": 50, "search_title_generate": False,
        "search_summary_generate": False, "search_results_summary_generate": False})

    assert _keys(ids, [d["id"] for d in browse["items"]]) == {"chronicle"} and browse["total_count"] == 1
    assert _keys(ids, passages["ranked_ids"]) == {"chronicle_1", "chronicle_2", "chronicle_3"}
    assert _keys(ids, [h["document"]["id"] for h in documents["items"]]) == {"chronicle"}
    assert _keys(ids, [r["id"] for r in ranked["ranked"]]) == {"chronicle"} and ranked["eligible_count"] == 1
    assert _keys(ids, [h["id"] for h in legacy.json()["results"]]) == {"chronicle_1", "chronicle_2", "chronicle_3"}


@pytest.mark.parametrize("user", [None, "owner"])
async def test_unscoped_counts_cover_public_documents_only(api_client, login, seeded_store, collection_names, rights,
                                                           user):
    headers = await login(user)

    overview = (await api_client.get("/api/analytics/corpus/overview", headers=headers)).json()
    distributions = (await api_client.post("/api/analytics/corpus/distributions", headers=headers, json={})).json()
    # The search filters' year range and languages (read at startup) count public documents only.
    stats = await ChunkSearchRepository(seeded_store, collection_names).document_filter_stats()

    assert overview["total_documents"] == 1
    assert distributions["total_documents"] == 1
    assert stats[:2] == (1851, 1851)  # chronicle's year, not letters' 1902


async def test_client_ids_of_restricted_records_are_not_read_back(api_client, login, ids, rights):
    """Ranked readback, ranked-result analytics and the Search chat scope ignore forged ids."""
    headers = await login("owner")
    restricted = [ids.chunk["letters_1"], ids.chunk["gazette_1"]]

    read = await api_client.post("/api/search/passages/read", headers=headers, json={
        "ids": restricted, "criteria": {"text_query": EVERY_WORD}})
    documents = await api_client.post("/api/search/documents/read", headers=headers, json={
        "ranked": [{"id": ids.doc["letters"], "match": "text", "chunk_id": ids.chunk["letters_1"]}],
        "criteria": {"text_query": EVERY_WORD}})
    counted = await api_client.post("/api/analytics/results/distributions", headers=headers, json={
        "mode": "passages", "ids": restricted, "criteria": {"text_query": EVERY_WORD},
        "ranking": {"type": "text", "bounded": False}})
    # A collection that does not hold letters does not make it readable either.
    other = await api_client.post("/api/search/passages/read", headers=headers, json={
        "ids": [ids.chunk["letters_1"]], "criteria": {"text_query": EVERY_WORD},
        "user_collection_id": ids.col["newspapers"]})

    assert read.status_code == 200 and read.json()["items"] == []
    assert documents.status_code == 200 and documents.json()["items"] == []
    assert counted.status_code == 200 and (counted.json()["total_count"], counted.json()["missing_count"]) == (0, 2)
    assert other.status_code == 200 and other.json()["items"] == []


@pytest.mark.parametrize("user, key, collection", [
    ("owner", "letters", "chronicles"), ("annotator", "letters", "chronicles"),
    ("owner", "gazette", "newspapers"), ("outsider", "gazette", "outsider_notes"),
])
async def test_a_collection_that_holds_the_document_makes_it_readable(api_client, login, ids, rights, user, key,
                                                                      collection):
    headers = await login(user)
    c = ids.col[collection]

    for path in _document_reads(ids, key, c):
        assert (await api_client.get(path, headers=headers)).status_code == 200, path
    count = await api_client.get(f"/api/documents/{ids.doc[key]}/chunks/count?collection_id={c}", headers=headers)
    detail = await api_client.get(f"/api/user_collections/{c}/documents/{ids.doc[key]}", headers=headers)
    browse = (await api_client.get(f"/api/documents/browse?collection_id={c}", headers=headers)).json()
    passages = await _passages(api_client, headers, c)
    documents = await _documents(api_client, headers, c, text=EVERY_WORD)

    assert count.json() == 2
    # All its chunks, also those that are not in the collection themselves (ADR 0007).
    assert {ch["id"] for ch in detail.json()["chunks"]} == {ids.chunk[f"{key}_1"], ids.chunk[f"{key}_2"]}
    listed = next(item for item in browse["items"] if item["id"] == ids.doc[key])
    assert listed.get("public") == (False if key == "letters" else None)  # what the row label shows
    assert f"{key}_1" in _keys(ids, passages["ranked_ids"])
    assert key in _keys(ids, [r["id"] for r in documents["ranked"]])


@pytest.mark.parametrize("user, collection, status", [
    ("outsider", "chronicles", 404),   # cannot read the collection
    ("owner", "newspapers", 404),      # can read it, but it does not hold letters
    ("owner", "outsider_notes", 404),
    (None, "chronicles", 401),
])
async def test_a_collection_grants_nothing_without_read_access_and_membership(api_client, login, ids, rights, user,
                                                                              collection, status):
    headers = await login(user)

    for path in _document_reads(ids, "letters", ids.col[collection]):
        assert (await api_client.get(path, headers=headers)).status_code == status, path


@pytest.mark.parametrize("change", ["unshare", "remove document"])
async def test_revoking_the_collection_route_denies_the_next_read(api_client, login, ids, store, rights, change):
    owner, annotator = await login("owner"), await login("annotator")
    c, letters = ids.col["chronicles"], ids.doc["letters"]
    reader = annotator if change == "unshare" else owner
    path = f"/api/document/{letters}?collection_id={c}"
    assert (await api_client.get(path, headers=reader)).status_code == 200
    chronicle_links = await store.collections_of_document(ids.doc["chronicle"])

    if change == "unshare":
        response = await api_client.delete(f"/api/user_collections/{c}/share/{ids.user['annotator']}", headers=owner)
    else:
        response = await api_client.delete(f"/api/user_collections/{c}/documents/{letters}", headers=owner)
    assert response.status_code == 200, response.text

    assert (await api_client.get(path, headers=reader)).status_code in (401, 404)
    assert (await api_client.get(f"/api/document/{letters}", headers=reader)).status_code == 404
    if change == "remove document":
        assert ids.chunk["letters_1"] not in (await _passages(api_client, reader, c))["ranked_ids"]
    # Only the revoked route changed: the other memberships are as they were.
    assert await store.collections_of_document(ids.doc["chronicle"]) == chronicle_links


async def test_existing_memberships_and_annotations_are_unchanged(api_client, login, ids, store, rights):
    """The rule only reads; restricted documents keep their collections and annotations."""
    headers = await login("owner")

    spans = await api_client.get(f"/api/tag_spans?collection_id={ids.col['chronicles']}", headers=headers)

    assert set(await store.collections_of_document(ids.doc["letters"])) == {ids.col["chronicles"]}
    assert set(await store.collections_of_document(ids.doc["gazette"])) == {ids.col["newspapers"],
                                                                             ids.col["outsider_notes"]}
    assert spans.status_code == 200 and spans.json()


@pytest.mark.parametrize("user, key, target, status", [
    ("outsider", "letters", "outsider_notes", 404),    # restricted, in no collection outsider can read
    ("outsider", "gazette", "outsider_notes", 200),    # unknown, but already in outsider's collection
    ("owner", "letters", "newspapers", 200),           # restricted, readable through chronicles
    ("owner", "chronicle", "newspapers", 200),         # public
])
async def test_only_documents_the_owner_can_read_are_added(api_client, login, ids, store, rights, user, key,
                                                           target, status):
    headers = await login(user)
    c = ids.col[target]
    before = await store.collections_of_document(ids.doc[key])

    document = await api_client.post(f"/api/user_collections/{c}/documents/{ids.doc[key]}", headers=headers)
    chunk = await api_client.post(f"/api/user_collections/{c}/chunks/{ids.chunk[f'{key}_2']}", headers=headers)

    assert (document.status_code, chunk.status_code) == (status, status), document.text
    if status == 404:
        assert await store.collections_of_document(ids.doc[key]) == before
        assert c not in await store.collections_of_chunk(ids.chunk[f"{key}_2"])
