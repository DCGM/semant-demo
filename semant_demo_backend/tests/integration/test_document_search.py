"""Documents ranked by a text query (#607) against the real test store: one metadata-first list of
distinct documents, the others by their best-matching chunk, eligibility decided by the filters
inside retrieval (never by discarding hits of a limited ranking), and later pages read by id.

Fixture documents (tests/fixtures/corpus.json): chronicle "Kronika obce Lhota" (1851, author
Václav Kronikář; chronicle_1..3), letters "Dopisy z Prahy" (1902, authors Karel Pisatel and Marie
Pisatelová; letters_1, letters_2) and gazette "Pražský věstník" (no year; gazette_1, gazette_2);
every chunk is "ces". Classifications: chronicle_1 (narration, moderate, formal), letters_1
(interaction, informal). Collections: "chronicles" (chronicle, letters; shared with the annotator)
and "newspapers" (chronicle, gazette). The tests write the chunk texts they rank (``update``);
"Lhota" is a word of the chronicle's title only.
"""
from uuid import UUID

import pytest

from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.documents.criteria import DocumentFilters, document_conditions
from semant_demo.features.search.schemas import ChunkQuery, SearchType
from semant_demo.maintenance import chunk_summaries, chunk_summary_schema
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

CHRONICLE, LETTERS, GAZETTE = "Kronika obce Lhota", "Dopisy z Prahy", "Pražský věstník"


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
    """Declares and recomputes the documents' chunk-value summaries (#529), as on a store
    initialized by #561; needed by chunk filters."""
    async def run():
        await chunk_summary_schema.update(seeded_store, collection_names, apply=True)
        await chunk_summaries.run(seeded_store, collection_names, report=tmp_path / "summaries.json",
                                  endpoint="test", write=True, progress=lambda line: None)
    return run


@pytest.fixture
def search(api_client, login):
    async def run(text, user=None, status=200, **body):
        response = await api_client.post("/api/search/documents", headers=await login(user), json={
            "type": "text", **body, "criteria": {"text_query": text, **body.get("criteria", {})}})
        assert response.status_code == status, response.text
        return response.json()
    return run


def titles(body) -> list[str]:
    return [item["document"]["title"] for item in body["items"]]


def ranked(body, ids) -> list[tuple[str, str, str | None]]:
    """The ranking as (document key, match, evidence chunk key)."""
    keys = {**{v: k for k, v in ids.doc.items()}, **{v: k for k, v in ids.chunk.items()}}
    return [(keys[r["id"]], r["match"], keys.get(r["chunk_id"])) for r in body["ranked"]]


async def test_one_metadata_first_list_of_distinct_documents_ranked_by_their_best_chunk(search, update, ids):
    await update("gazette_1", text="Lhota, Lhota, Lhota.")
    await update("gazette_2", text="O obci Lhota.")
    await update("letters_2", text="Z dopisu se dozvídáme mnoho o životě v obci Lhota a v okolních vesnicích.")

    body = await search("Lhota")

    # The chronicle by its title first, then the gazette by its best chunk (gazette_1, ahead of
    # gazette_2), then the letters; each document once.
    assert ranked(body, ids) == [("chronicle", "metadata", "chronicle_3"), ("gazette", "text", "gazette_1"),
                                 ("letters", "text", "letters_2")]
    assert titles(body) == [CHRONICLE, GAZETTE, LETTERS]
    evidence = body["items"][1]["chunk"]
    assert (evidence["id"], evidence["text"], evidence["document"]) == (
        ids.chunk["gazette_1"], "Lhota, Lhota, Lhota.", ids.doc["gazette"])
    assert {k: body[k] for k in ("total_count", "eligible_count", "bounded", "order", "read_count")} == {
        "total_count": 3, "eligible_count": 3, "bounded": False, "order": "metadata_then_text", "read_count": 3}
    assert {k: body["retrieval"][k] for k in ("metadata_bounded", "chunk_bounded", "ranked_chunks", "type")} == {
        "metadata_bounded": False, "chunk_bounded": False, "ranked_chunks": 4, "type": "text"}


async def test_metadata_matches_need_every_word_of_the_query_in_one_bibliographic_field(search, ids):
    assert ranked(await search("Dopisy Prahy"), ids)[0] == ("letters", "metadata", "letters_1")  # the title
    assert ranked(await search("Pisatel"), ids) == [("letters", "metadata", None)]  # an author
    # Weaviate's BM25 "and" holds per property: "Marie" (an author) and "Prahy" (the title) are no
    # metadata match together; the letters rank by text (letters_1). An accepted limitation.
    assert ranked(await search("Marie Prahy"), ids)[0] == ("letters", "text", "letters_1")
    # Words of two titles: no metadata match; the text decides (both chronicle_1 and letters_1 match).
    mixed = ranked(await search("Lhoty Prahy"), ids)
    assert {(d, m) for d, m, _ in mixed} == {("chronicle", "text"), ("letters", "text")}


async def test_a_document_filtered_in_by_one_chunk_ranks_by_another_chunk(search, update, summarize, ids, api_client):
    # letters_1 (interaction) makes the letters eligible; letters_2, not interaction, matches the text.
    await update("letters_2", text="Lhota Lhota")
    await update("gazette_1", text="Lhota Lhota Lhota")
    await summarize()
    interaction = {"chunk_filters": {"classifications": {"communicative_mode": ["interaction"]}}}

    body = await search("Lhota", criteria=interaction)

    # The chronicle (title) and the gazette (a better chunk) are not eligible: neither has an
    # interaction chunk. The letters rank by letters_2, which the filter would not admit itself.
    assert ranked(body, ids) == [("letters", "text", "letters_2")]
    assert (body["total_count"], body["eligible_count"]) == (1, 1)
    assert body["items"][0]["chunk"]["id"] == ids.chunk["letters_2"]
    # Passages hold the filter on the passage itself: letters_2 is no passage of this search.
    passages = await api_client.post("/api/search/passages", json={
        "type": "text", "criteria": {"text_query": "Lhota", **interaction}})
    assert passages.status_code == 200 and passages.json()["items"] == []


async def test_eligibility_restricts_the_ranking_before_its_limit(search, update, api_app, ids):
    # The gazette's and the chronicle's chunks rank above the letters' one; with room for one chunk
    # the ranking still finds the eligible letters: the filter is inside the query, not after it.
    for key in ("gazette_1", "gazette_2", "chronicle_3"):
        await update(key, text="Lhota Lhota Lhota")
    await update("letters_2", text="Lhota v dopise")
    api_app.state.config.SEARCH_DOCUMENTS_CHUNK_LIMIT = 1

    unfiltered = await search("Lhota")
    letters = await search("Lhota", criteria={"document_filters": {"year_min": 1900}})

    assert unfiltered["bounded"] is True and unfiltered["total_count"] is None
    assert unfiltered["retrieval"] == {**unfiltered["retrieval"], "chunk_limit": 1, "chunk_bounded": True,
                                       "ranked_chunks": 1}
    assert ranked(letters, ids) == [("letters", "text", "letters_2")]
    assert (letters["bounded"], letters["total_count"]) == (False, 1)


@pytest.mark.parametrize("mode", [SearchType.vector, SearchType.hybrid])
async def test_vector_and_hybrid_rank_every_eligible_document(seeded_store, collection_names, ids, mode):
    # Every chunk matches a vector query: unless a limit cuts the ranking, every eligible document
    # ranks, each by its best chunk. Repository level: the test app has no fake embedder.
    repository = ChunkSearchRepository(seeded_store, collection_names)

    def query(**scope) -> ChunkQuery:
        return ChunkQuery(text="Lhota", mode=mode, limit=50, alpha=0.5, vector=fake_embedding("Požár v obci"),
                          target_vector="default", **scope)

    pairs = await repository.ranked_documents(query())
    assert len(pairs) == 7 and {d for _, d in pairs} == {UUID(ids.doc[k]) for k in ("chronicle", "letters", "gazette")}
    chunk_of = {UUID(v): k for k, v in ids.chunk.items()}
    assert {chunk_of[c].split("_")[0] for c, d in pairs if d == UUID(ids.doc["letters"])} == {"letters"}
    # Scoped by the document's own collection and properties, through the reference.
    scoped = await repository.ranked_documents(query(
        document_collection_id=UUID(ids.col["newspapers"]),
        document_conditions=tuple(document_conditions(DocumentFilters(year_max=1900)))))
    assert {d for _, d in scoped} == {UUID(ids.doc["chronicle"])} and len(scoped) == 3


async def test_later_pages_are_read_by_their_ranking_entries_under_the_search_criteria(
        search, update, api_client, ids):
    await update("gazette_1", text="Lhota Lhota Lhota")
    await update("letters_2", text="Lhota v dopise")
    first = await search("Lhota", limit=1)
    assert (titles(first), first["read_count"], len(first["ranked"])) == ([CHRONICLE], 1, 3)

    async def read(entries, **criteria):
        response = await api_client.post("/api/search/documents/read", json={
            "ranked": entries, "criteria": {"text_query": "Lhota", **criteria}})
        assert response.status_code == 200, response.text
        return response.json()["items"]

    rest = await read(first["ranked"][1:])
    assert [(i["document"]["title"], i["match"], i["chunk"]["id"]) for i in rest] == [
        (GAZETTE, "text", ids.chunk["gazette_1"]), (LETTERS, "text", ids.chunk["letters_2"])]
    # The entries come from the client: no longer eligible documents are left out, and a chunk of
    # another document is never shown as evidence.
    assert [i["document"]["title"] for i in await read(first["ranked"], document_filters={"year_min": 1900})] == [
        LETTERS]
    forged = await read([{"id": ids.doc["gazette"], "match": "text", "chunk_id": ids.chunk["letters_2"]}])
    assert [(i["document"]["title"], i["chunk"]) for i in forged] == [(GAZETTE, None)]


async def test_documents_of_a_collection_rank_by_any_of_their_chunks_with_read_access(search, update, ids):
    await update("gazette_1", text="Lhota Lhota")
    await update("letters_2", text="Lhota")

    newspapers = await search("Lhota", user="owner", user_collection_id=ids.col["newspapers"])
    assert titles(newspapers) == [CHRONICLE, GAZETTE]
    chronicles = await search("Lhota", user="annotator", user_collection_id=ids.col["chronicles"])  # shared
    assert titles(chronicles) == [CHRONICLE, LETTERS]
    await search("Lhota", user="outsider", user_collection_id=ids.col["chronicles"], status=404)
    await search("Lhota", user_collection_id=ids.col["chronicles"], status=401)


async def test_chunk_filters_without_the_summaries_are_rejected_not_empty(search):
    body = await search("Lhota", status=422, criteria={"chunk_filters": {"languages": ["ces"]}})

    assert "has no chunk-value summaries" in body["detail"]
