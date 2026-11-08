"""Analytics of a ranked search result (#619) against the real test store: the counts describe
exactly the ids Documents or Passages Results hold, read under the search's access and
eligibility again, never the corpus and never another ranking.

Fixture documents (tests/fixtures/corpus.json): chronicle "Kronika obce Lhota" (1851; chunks
chronicle_1..3), letters "Dopisy z Prahy" (1902; letters_1, letters_2) and gazette "Pražský věstník"
(no year; gazette_1, gazette_2); every document and chunk "ces", no library. Classifications:
chronicle_1 (narration), letters_1 (interaction). Collections: "chronicles" (documents chronicle and
letters; chunks chronicle_1, chronicle_2 and the letters'; shared with the annotator) and
"newspapers" (documents chronicle and gazette; not shared). The tests write the chunk texts they
rank (``update``).
"""
from uuid import UUID

import pytest

from semant_demo.maintenance import chunk_summaries, chunk_summary_schema

pytestmark = pytest.mark.integration

PATH = "/api/analytics/results/distributions"
TEXT = {"type": "text", "vector": None, "bounded": False}
UNKNOWN_ID = "5e3a0000-0000-4000-8000-0000000fffff"


@pytest.fixture
def update(seeded_store, collection_names, corpus):
    """Changes stored properties of a fixture chunk or document, by key."""
    async def run(key, **properties):
        if key in corpus.chunks:
            uuid, name = corpus.chunks[key]["id"], collection_names.chunks_collection_name
        else:
            uuid, name = corpus.documents[key]["id"], collection_names.document_collection_name
        await seeded_store.collections.get(name).data.update(uuid=uuid, properties=properties)
    return run


@pytest.fixture
def summarize(seeded_store, collection_names, tmp_path):
    """Declares and recomputes the documents' chunk-value summaries (#529); needed by chunk filters."""
    async def run():
        await chunk_summary_schema.update(seeded_store, collection_names, apply=True)
        await chunk_summaries.run(seeded_store, collection_names, report=tmp_path / "summaries.json",
                                  endpoint="test", write=True, progress=lambda line: None)
    return run


@pytest.fixture
def post(api_client, login):
    async def run(path, body, user=None, status=200):
        response = await api_client.post(path, headers=await login(user), json=body)
        assert response.status_code == status, response.text
        return response.json()
    return run


@pytest.fixture
def lhota(update):
    """Every document has chunks matching "Lhota": the chronicle three, the gazette two, the letters one."""
    async def run():
        await update("chronicle_1", text="Lhota a hejtman.")
        await update("chronicle_2", text="Slavnost v obci Lhota.")
        await update("gazette_1", text="Lhota, Lhota, Lhota.")
        await update("gazette_2", text="O obci Lhota.")
        await update("letters_2", text="Z dopisu o obci Lhota.")
    return run


def years(body) -> dict[int, int]:
    return {y["year"]: y["count"] for y in body["publication_year"]["years"]}


async def test_documents_results_are_counted_as_the_distinct_documents_of_the_ranking(post, lhota, ids):
    await lhota()
    search = await post("/api/search/documents", {"type": "text", "criteria": {"text_query": "Lhota"}})
    ranked = [r["id"] for r in search["ranked"]]
    assert set(ranked) == set(ids.doc.values())

    body = await post(PATH, {"mode": "documents", "ids": ranked, "criteria": search["criteria"],
                             "ranking": {"type": "text", "bounded": search["bounded"]}, "members": True})

    # Each document once, however many of its chunks matched (the chronicle three).
    assert {k: body[k] for k in ("scope", "mode", "unit", "input_count", "total_count", "missing_count",
                                 "distinct_documents")} == {
        "scope": "ranked_results", "mode": "documents", "unit": "documents", "input_count": 3, "total_count": 3,
        "missing_count": 0, "distinct_documents": 3}
    assert years(body) == {1851: 1, 1902: 1} and body["publication_year"]["unknown_count"] == 1
    assert body["languages"]["values"] == [{"value": "ces", "count": 3}]
    assert (body["libraries"]["available"], body["libraries"]["unknown_count"]) == (True, 3)
    assert body["ranking"] == {"type": "text", "vector": None, "bounded": False, "retrieval_limit": 3000}
    # The counted results in ranking order, with the values they are counted under.
    assert [m["id"] for m in body["members"]] == ranked
    assert {m["id"]: m["year"] for m in body["members"]} == {
        ids.doc["chronicle"]: 1851, ids.doc["letters"]: 1902, ids.doc["gazette"]: None}


async def test_passage_results_count_passages_and_their_distinct_source_documents(post, lhota, ids):
    await lhota()
    search = await post("/api/search/passages", {"type": "text", "limit": 2, "criteria": {"text_query": "Lhota"}})
    assert len(search["ranked_ids"]) == 6 and search["read_count"] == 2  # counted beyond the first page

    body = await post(PATH, {"mode": "passages", "ids": search["ranked_ids"], "criteria": search["criteria"],
                             "ranking": TEXT, "members": True})

    assert (body["unit"], body["total_count"], body["distinct_documents"]) == ("passages", 6, 3)
    # chronicle_1..3 count three times under 1851; the gazette's two passages have no year.
    assert years(body) == {1851: 3, 1902: 1} and body["publication_year"]["unknown_count"] == 2
    assert body["languages"]["values"] == [{"value": "ces", "count": 6}]
    assert [m["id"] for m in body["members"]] == search["ranked_ids"]
    assert {m["id"]: m["document_id"] for m in body["members"]}[ids.chunk["gazette_2"]] == ids.doc["gazette"]


async def test_documents_count_per_dimension_and_passages_only_same_chunk_matches(post, update, summarize, ids):
    # The letters are an eligible document (letters_1 is interaction), but letters_2 is no passage
    # of the filter: it is not interaction itself.
    await update("letters_2", text="Lhota Lhota")
    await summarize()
    criteria = {"text_query": "Lhota", "chunk_filters": {"classifications": {"communicative_mode": ["interaction"]}}}

    documents = await post(PATH, {"mode": "documents", "ids": [ids.doc["letters"], ids.doc["gazette"]],
                                  "criteria": criteria, "ranking": TEXT, "members": True})
    passages = await post(PATH, {"mode": "passages", "ids": [ids.chunk["letters_2"], ids.chunk["letters_1"]],
                                 "criteria": criteria, "ranking": TEXT, "members": True})

    # The gazette has no interaction chunk: named, not counted.
    assert [m["id"] for m in documents["members"]] == [ids.doc["letters"]]
    assert (documents["total_count"], documents["missing_count"]) == (1, 1)
    # A client naming letters_2 does not get it counted under the same-chunk filter.
    assert [m["id"] for m in passages["members"]] == [ids.chunk["letters_1"]]
    assert (passages["total_count"], passages["missing_count"]) == (1, 1)
    assert passages["criteria"]["chunk_filters"] == {"languages": [], "classifications": {
        "communicative_mode": ["interaction"]}}


async def test_unknown_stale_and_out_of_scope_ids_are_left_out_and_reported(post, update, ids):
    criteria = {"text_query": "Lhota", "document_filters": {"year_max": 1900}}
    # A document of another kind's id, a made-up id, and the letters (1902) outside the filters.
    named = [ids.doc["chronicle"], ids.chunk["chronicle_1"], UNKNOWN_ID, ids.doc["letters"]]
    body = await post(PATH, {"mode": "documents", "ids": named, "criteria": criteria, "ranking": TEXT})
    assert (body["input_count"], body["total_count"], body["missing_count"]) == (4, 1, 3)
    assert years(body) == {1851: 1}

    # A result that changed since its ranking: counted as it is now, or not at all.
    await update("chronicle", yearIssued=1950)
    stale = await post(PATH, {"mode": "documents", "ids": named, "criteria": criteria, "ranking": TEXT})
    assert (stale["total_count"], stale["missing_count"]) == (0, 4)
    assert stale["publication_year"] == {"available": True, "unavailable_reason": None, "years": [], "unknown_count": 0}

    # Passage mode reads chunks: document ids are not passages.
    passages = await post(PATH, {"mode": "passages", "ids": [ids.doc["gazette"], ids.chunk["gazette_1"]],
                                 "criteria": {"text_query": "Lhota"}, "ranking": TEXT})
    assert (passages["total_count"], passages["missing_count"]) == (1, 1)


async def test_a_collection_scope_is_checked_again_and_restricts_the_counted_ids(post, ids):
    every_document = list(ids.doc.values())
    body = {"mode": "documents", "ids": every_document, "criteria": {"text_query": "Lhota"}, "ranking": TEXT,
            "user_collection_id": ids.col["newspapers"], "members": True}
    owned = await post(PATH, body, user="owner")
    assert {m["id"] for m in owned["members"]} == {ids.doc["chronicle"], ids.doc["gazette"]}

    # Not shared with the annotator; anonymous callers read no collection.
    await post(PATH, body, user="annotator", status=404)  # as for a collection that does not exist
    await post(PATH, body, status=401)

    # Passages of a collection: the chunks linked to it (chronicle_3 is the newspapers' only one).
    passages = await post(PATH, {**body, "mode": "passages", "ids": [ids.chunk["chronicle_1"], ids.chunk["chronicle_3"]]},
                          user="owner")
    assert [m["id"] for m in passages["members"]] == [ids.chunk["chronicle_3"]]


async def test_requests_that_are_no_ranked_result_are_refused(post, api_app, ids):
    base = {"mode": "passages", "ids": [ids.chunk["chronicle_1"]], "criteria": {"text_query": "Lhota"},
            "ranking": TEXT}
    await post(PATH, {**base, "criteria": {"text_query": "  "}}, status=422)  # no text query: no ranking
    await post(PATH, {**base, "ids": [ids.chunk["chronicle_1"]] * 2}, status=422)
    await post(PATH, {**base, "ranking": {"type": "hybrid", "vector": "no-such-vector", "bounded": True}}, status=400)
    await post(PATH, {**base, "criteria": {"text_query": "Lhota", "chunk_filters": {"languages": ["xx"]}}},
               status=400)
    api_app.state.config.SEARCH_PASSAGES_LIMIT = 1
    await post(PATH, {**base, "ids": [ids.chunk["chronicle_1"], ids.chunk["chronicle_2"]]}, status=400)

    # An empty ranking is an empty population, not an error.
    empty = await post(PATH, {**base, "ids": []})
    assert (empty["total_count"], empty["distinct_documents"], empty["languages"]["values"]) == (0, 0, [])
    # A hybrid ranking without a named vector used the default one.
    hybrid = await post(PATH, {**base, "ranking": {"type": "hybrid", "bounded": True}})
    assert hybrid["ranking"]["vector"] is not None and hybrid["ranking"]["bounded"] is True


async def test_a_property_the_store_does_not_record_is_unavailable_not_zero(legacy_documents, post, ids):
    body = await post(PATH, {"mode": "passages", "ids": [ids.chunk["chronicle_1"], ids.chunk["letters_1"]],
                             "criteria": {"text_query": "Lhota"}, "ranking": TEXT, "members": True})
    assert body["libraries"] == {"available": False, "unavailable_reason": "missing_property",
                                 "values": None, "other_count": None, "unknown_count": None}
    assert years(body) == {1851: 1, 1902: 1}
    assert [m["library"] for m in body["members"]] == [None, None]


async def test_ids_beyond_one_read_batch_are_all_counted(post, lhota, monkeypatch, ids):
    from semant_demo.adapters.weaviate import analytics, search
    monkeypatch.setattr(analytics, "READ_BATCH", 2)
    monkeypatch.setattr(search, "READ_BATCH", 2)
    await lhota()
    passages = [ids.chunk[k] for k in ("chronicle_1", "chronicle_2", "chronicle_3", "gazette_1", "gazette_2")]
    body = await post(PATH, {"mode": "passages", "ids": passages, "criteria": {"text_query": "Lhota"},
                             "ranking": TEXT, "members": True})
    assert [m["id"] for m in body["members"]] == passages
    documents = await post(PATH, {"mode": "documents", "ids": list(ids.doc.values()),
                                  "criteria": {"text_query": "Lhota"}, "ranking": TEXT})
    assert documents["total_count"] == 3
    assert UUID(body["members"][0]["document_id"]) == UUID(ids.doc["chronicle"])
