"""Search criteria (#526) against the real test store: the same document filters select the same
documents in Search, document browsing and Analytics, and every chunk filter must hold on the
one returned chunk.

Fixture documents (tests/fixtures/corpus.json): chronicle "Kronika obce Lhota" (1851;
chronicle_1..3), letters "Dopisy z Prahy" (1902; letters_1, letters_2) and gazette "Pražský
věstník" (no year; gazette_1, gazette_2); every document and chunk is "ces", no library.
Classifications: chronicle_1 (narration, moderate, formal), letters_1 (interaction, informal).
Each test changes a few values of its own (``update``) and first shows that the chunks it
expects to exclude match without the filter. The store's chunk classifications are ``text[]``
with Weaviate's default ``word`` tokenization, as in production.
"""
import pytest

from semant_demo.config import MAX_PASSAGES_LIMIT, MAX_QUERY_RESULTS
from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.analytics import service as analytics
from semant_demo.features.documents.criteria import (
    ChunkFilters, DocumentFilters, chunk_conditions, document_conditions, validate_chunk_filters)
from semant_demo.features.search.filters import chunk_vocabulary, generate_default_filters
from semant_demo.features.search.schemas import ChunkQuery, SearchType
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

ALL_WORDS = "Novák Požár Prahy rodinu Slavia trh"
"""One word of every chunk: an unrestricted BM25 search returns all seven."""
VOCABULARY = chunk_vocabulary(generate_default_filters(languages=["ces", "deu"]))
CHRONICLE = {"chronicle_1", "chronicle_2", "chronicle_3"}
LETTERS = {"letters_1", "letters_2"}
GAZETTE = {"gazette_1", "gazette_2"}
EVERY_CHUNK = CHRONICLE | LETTERS | GAZETTE
NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}


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
def find(seeded_store, collection_names, corpus):
    """The keys of the chunks a BM25 search for ``ALL_WORDS`` returns under the filters."""
    by_id = {c["id"]: key for key, c in corpus.chunks.items()}

    async def run(document_filters=DocumentFilters(), chunk_filters=ChunkFilters()) -> set[str]:
        chunks = validate_chunk_filters(chunk_filters, VOCABULARY)
        hits = await ChunkSearchRepository(seeded_store, collection_names).search(ChunkQuery(
            text=ALL_WORDS, mode=SearchType.text, limit=50,
            document_conditions=tuple(document_conditions(document_filters)),
            chunk_conditions=tuple(chunk_conditions(chunks, VOCABULARY))))
        return {by_id[str(hit.id)] for hit in hits}
    return run


def classified(**values) -> ChunkFilters:
    return ChunkFilters(classifications=values)


async def test_every_chunk_filter_must_hold_on_the_returned_chunk(find, update):
    # chronicle_1 is narration and formal; chronicle_2 (same document) becomes informal.
    await update("chronicle_2", style=["informal"])
    assert await find(chunk_filters=classified(communicative_mode=["narration"])) == {"chronicle_1"}
    assert await find(chunk_filters=classified(style=["informal"])) == {"chronicle_2", "letters_1"}

    # One document satisfies both filters, but through different chunks: no passage does.
    assert await find(chunk_filters=classified(communicative_mode=["narration"], style=["informal"])) == set()
    assert await find(chunk_filters=classified(communicative_mode=["narration"], style=["formal"])) == {"chronicle_1"}


async def test_alternatives_of_one_chunk_filter_are_or(find):
    assert await find(chunk_filters=classified(communicative_mode=["narration", "interaction"])) == \
        {"chronicle_1", "letters_1"}


async def test_chunk_classifications_match_exactly(find, update, seeded_store, collection_names):
    config = await seeded_store.collections.get(collection_names.chunks_collection_name).config.get()
    assert next(p for p in config.properties if p.name == "complexity").tokenization.value == "word"
    await update("chronicle_2", complexity=["very_easy"])
    await update("chronicle_3", complexity=["easy"])

    # By word, "easy" is also in "very_easy"; the filter must not confuse them.
    assert await find(chunk_filters=classified(complexity=["easy"])) == {"chronicle_3"}
    assert await find(chunk_filters=classified(complexity=["very_easy"])) == {"chronicle_2"}
    assert await find(chunk_filters=classified(complexity=["easy", "very_easy"])) == {"chronicle_2", "chronicle_3"}
    assert await find(chunk_filters=classified(complexity=["moderate"])) == {"chronicle_1"}


async def test_document_language_and_chunk_language_are_separate_restrictions(find, update):
    await update("letters", language="deu")       # its chunks stay "ces"
    await update("chronicle_3", language="deu")   # its document stays "ces"

    assert await find(DocumentFilters(languages=["deu"])) == LETTERS
    assert await find(chunk_filters=ChunkFilters(languages=["deu"])) == {"chronicle_3"}
    assert await find(DocumentFilters(languages=["deu"]), ChunkFilters(languages=["ces"])) == LETTERS
    assert await find(DocumentFilters(languages=["deu"]), ChunkFilters(languages=["deu"])) == set()
    assert await find(DocumentFilters(languages=["ces"]), ChunkFilters(languages=["ces"])) == \
        EVERY_CHUNK - LETTERS - {"chronicle_3"}


@pytest.mark.parametrize("filters, expected", [
    (DocumentFilters(), EVERY_CHUNK),
    (DocumentFilters(year_min=1851, year_max=1851), CHRONICLE),          # both bounds inclusive
    (DocumentFilters(year_min=1852, year_max=1902), LETTERS),
    (DocumentFilters(year_max=1850), set()),
    (DocumentFilters(year_min=1), CHRONICLE | LETTERS),                  # no year never matches a range
    (DocumentFilters(title_contains=["kronika", "věstník"]), CHRONICLE | GAZETTE),   # alternatives
    (DocumentFilters(title_contains=["obce kron"]), CHRONICLE),          # every word, inside title words
    (DocumentFilters(title_contains=["prah"]), LETTERS),                 # diacritics-sensitive: not "Pražský"
    (DocumentFilters(libraries=["mzk", "nkp"]), CHRONICLE | LETTERS),
    (DocumentFilters(libraries=["nkp"], year_max=1900), set()),
])
async def test_document_filters_select_the_same_documents_in_search_browse_and_analytics(
        find, update, documents, seeded_store, collection_names, corpus, filters, expected):
    await update("chronicle", library="mzk")
    await update("letters", library="nkp")
    document_of = {key: chunk["document"] for key, chunk in corpus.chunks.items()}
    expected_documents = {document_of[key] for key in expected}
    key_of = {d["id"]: key for key, d in corpus.documents.items()}

    found = await find(filters)
    browsed = await documents.browse(conditions=document_conditions(filters), limit=50)
    counted = await analytics.corpus_distributions(CorpusAnalyticsRepository(seeded_store, collection_names), filters)

    assert found == expected
    assert {key_of[str(d.id)] for d in browsed.items} == expected_documents
    assert browsed.total_count == counted.total_documents == len(expected_documents)


########
# HTTP #
########

def search_body(**criteria) -> dict:
    return {"query": ALL_WORDS, "type": "text", "limit": 50, "tag_uuids": [], "positive": False,
            "automatic": False, **NO_SUMMARY, **criteria}


async def test_search_applies_criteria_filters_and_echoes_them_normalized(api_client, update, corpus):
    await update("chronicle_2", style=["informal"])
    by_id = {c["id"]: key for key, c in corpus.chunks.items()}

    response = await api_client.post("/api/search", json=search_body(  # anonymous
        document_filters={"year_max": 1900, "title_contains": ["Kronika"]},
        chunk_filters={"languages": ["CES"], "classifications": {"style": ["Informal"]}}))

    assert response.status_code == 200
    body = response.json()
    assert {by_id[r["id"]] for r in body["results"]} == {"chronicle_2"}
    assert body["search_request"]["chunk_filters"] == {"languages": ["ces"], "classifications": {"style": ["informal"]}}


@pytest.mark.parametrize("criteria, status, message", [
    ({"chunk_filters": {"classifications": {"style": ["casual"]}}}, 400, "'casual' is not a valid option"),
    ({"chunk_filters": {"classifications": {"title": ["x"]}}}, 400, "not a configured classification"),
    ({"document_filters": {"year_min": 1900}, "min_year": 1800}, 400, "not both"),
    ({"document_filters": {"year_min": 1901, "year_max": 1900}}, 422, "must not be after the last one"),
    ({"chunk_filters": {"year_min": 1900}}, 422, "Extra inputs are not permitted"),
])
async def test_invalid_search_criteria_are_rejected(api_client, criteria, status, message):
    response = await api_client.post("/api/search", json=search_body(**criteria))

    assert response.status_code == status
    assert message in str(response.json()["detail"])


async def test_a_filter_on_a_property_the_store_lacks_is_rejected_not_empty(legacy_documents, api_client):
    # Older stores have no Documents.library (#496).
    searched = await api_client.post("/api/search", json=search_body(document_filters={"libraries": ["mzk"]}))
    browsed = await api_client.get("/api/documents/browse", params={"libraries": "mzk"})
    explored = await api_client.post("/api/search/documents", json={"criteria": {"document_filters": {"libraries": ["mzk"]}}})
    ranked = await api_client.post("/api/search/documents", json={  # #607
        "criteria": {"text_query": "Prahy", "document_filters": {"libraries": ["mzk"]}}, "type": "text"})

    for response in (searched, browsed, explored, ranked):
        assert response.status_code == 422
        assert response.json()["detail"] == \
            "Documents cannot be filtered by library: this corpus database is not recorded."


def passages_body(limit=20, **criteria) -> dict:
    return {"criteria": {"text_query": ALL_WORDS, **criteria}, "type": "text", "limit": limit}


async def test_passages_hold_every_chunk_filter_on_the_returned_chunk(api_client, update, corpus):
    # #605: chronicle_1 is narration and formal; chronicle_2 (same document) becomes informal.
    await update("chronicle_2", style=["informal"])
    by_id = {c["id"]: key for key, c in corpus.chunks.items()}

    async def keys(**criteria):
        response = await api_client.post("/api/search/passages", json=passages_body(**criteria))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ranked_ids"] == [item["id"] for item in body["items"]]
        return {by_id[item["id"]] for item in body["items"]}

    assert await keys() == EVERY_CHUNK
    assert await keys(chunk_filters={"classifications": {"style": ["informal"]}}) == {"chronicle_2", "letters_1"}
    # The chronicle meets both through different chunks: no passage of it does.
    assert await keys(chunk_filters={"classifications": {"communicative_mode": ["narration"],
                                                         "style": ["informal"]}}) == set()
    assert await keys(document_filters={"year_max": 1900},
                      chunk_filters={"classifications": {"style": ["informal"]}}) == {"chronicle_2"}


async def test_later_passage_pages_read_the_ranked_ids_up_to_the_end(api_client):
    # #611: one ranking; Load more reads the next ranked ids instead of ranking again.
    whole = (await api_client.post("/api/search/passages", json=passages_body(limit=50))).json()
    assert (whole["bounded"], whole["total_count"], whole["read_count"]) == (False, len(EVERY_CHUNK), len(EVERY_CHUNK))

    first = (await api_client.post("/api/search/passages", json=passages_body(limit=3))).json()
    assert first["ranked_ids"] == whole["ranked_ids"] and first["read_count"] == 3
    pages, ranked, position = [first["items"]], first["ranked_ids"], first["read_count"]
    while position < len(ranked):
        response = await api_client.post("/api/search/passages/read", json={
            "ids": ranked[position:position + 3], "criteria": first["criteria"]})
        assert response.status_code == 200, response.text
        pages.append(response.json()["items"])
        position += 3

    assert [len(p) for p in pages] == [3, 3, 1]
    assert [item["id"] for p in pages for item in p] == [item["id"] for item in whole["items"]]


async def test_a_later_passage_page_answers_only_ids_the_search_could_return(api_client, login, ids, update):
    # #611: the ids come from the client; the collection, its access and the criteria are
    # applied again, so ids of other collections or no longer matching chunks are left out.
    every = [ids.chunk[key] for key in sorted(EVERY_CHUNK)]

    async def read(user=None, **body):
        response = await api_client.post("/api/search/passages/read", headers=await login(user), json={
            "ids": every, "criteria": {"text_query": ALL_WORDS}, **body})
        return response.status_code, response.json()

    by_id = {v: k for k, v in ids.chunk.items()}
    status, body = await read()
    assert status == 200 and {by_id[item["id"]] for item in body["items"]} == EVERY_CHUNK  # the public corpus
    status, body = await read("annotator", user_collection_id=ids.col["chronicles"])  # shared with the annotator
    assert status == 200 and {by_id[item["id"]] for item in body["items"]} == {"chronicle_1", "chronicle_2"} | LETTERS
    status, body = await read("owner", user_collection_id=ids.col["newspapers"],
                              criteria={"text_query": ALL_WORDS, "document_filters": {"year_max": 1900}})
    assert status == 200 and {by_id[item["id"]] for item in body["items"]} == {"chronicle_3"}
    assert (await read("outsider", user_collection_id=ids.col["chronicles"]))[0] == 404
    assert (await read(user_collection_id=ids.col["chronicles"]))[0] == 401

    await update("letters_1", style=["informal"])
    status, body = await read(criteria={"text_query": ALL_WORDS,
                                        "chunk_filters": {"classifications": {"style": ["informal"]}}})
    assert status == 200 and [by_id[item["id"]] for item in body["items"]] == ["letters_1"]


@pytest.mark.parametrize("mode", [SearchType.hybrid, SearchType.vector, SearchType.text])
async def test_a_ranking_read_by_id_keeps_the_order_and_the_hits_of_the_search(seeded_store, collection_names, mode):
    # #605: pages are slices of ranked ids read back in full (hybrid offset is unreliable).
    repository = ChunkSearchRepository(seeded_store, collection_names)
    query = ChunkQuery(text=ALL_WORDS, mode=mode, limit=50, alpha=0.5,
                       vector=None if mode == SearchType.text else fake_embedding("Požár v obci"),
                       target_vector=None if mode == SearchType.text else "default",
                       chunk_conditions=tuple(chunk_conditions(validate_chunk_filters(
                           ChunkFilters(languages=["ces"]), VOCABULARY), VOCABULARY)))

    searched = await repository.search(query)
    ranked = await repository.ranked_ids(query)

    assert ranked == [hit.id for hit in searched] and len(ranked) == len(EVERY_CHUNK)
    page = ranked[2:5]
    assert [hit.id for hit in await repository.read_hits(page, query)] == page
    assert await repository.read_hits([], query) == []


@pytest.mark.parametrize("mode", [SearchType.hybrid, SearchType.vector, SearchType.text])
async def test_the_largest_passage_ranking_is_within_the_query_maximum(seeded_store, collection_names, mode):
    # #608 review: at the largest SEARCH_PASSAGES_LIMIT the ranking asks for exactly
    # QUERY_MAXIMUM_RESULTS ids, which Weaviate answers; one more it refuses.
    repository = ChunkSearchRepository(seeded_store, collection_names)

    def query(limit: int) -> ChunkQuery:
        return ChunkQuery(text=ALL_WORDS, mode=mode, limit=limit, alpha=0.5,
                          vector=None if mode == SearchType.text else fake_embedding("Požár v obci"),
                          target_vector=None if mode == SearchType.text else "default")

    assert len(await repository.ranked_ids(query(MAX_PASSAGES_LIMIT + 1))) == len(EVERY_CHUNK)
    with pytest.raises(Exception, match="(?i)query maximum results"):
        await repository.ranked_ids(query(MAX_QUERY_RESULTS + 1))


async def test_browse_takes_the_document_filters_as_query_parameters(api_client, update):
    await update("chronicle", library="mzk")
    await update("letters", library=" nkp")

    response = await api_client.get("/api/documents/browse", params=[
        ("libraries", "mzk"), ("libraries", "nkp"), ("year_min", "1800"), ("title_contains", "obce")])
    unfiltered = await api_client.get("/api/documents/browse")

    assert response.status_code == 200
    assert [d["title"] for d in response.json()["items"]] == ["Kronika obce Lhota"]
    assert response.json()["total_count"] == 1
    assert unfiltered.json()["total_count"] == 3


@pytest.mark.parametrize("params, message", [
    ({"year_min": "1901", "year_max": "1900"}, "must not be after the last one"),
    ({"title_contains": "škol*"}, "does not support wildcards"),
    ({"libraries": " "}, "must be non-empty"),
])
async def test_browse_rejects_invalid_document_filters(api_client, params, message):
    response = await api_client.get("/api/documents/browse", params=params)

    assert response.status_code == 422
    assert message in str(response.json()["detail"])


#####################################
# Explore Documents (#606): paging  #
#####################################

async def _document_pages(api_client, limit, headers=None, **body) -> tuple[list[list[str]], dict]:
    """Every page of a documents search, following ``next_offset``; the titles and the last answer."""
    pages, offset = [], 0
    while offset is not None:
        response = await api_client.post("/api/search/documents", headers=headers,
                                         json={"criteria": {}, "limit": limit, "offset": offset, **body})
        assert response.status_code == 200, response.text
        answer = response.json()
        pages.append([d["document"]["title"] for d in answer["items"]])
        offset = answer["next_offset"]
    return pages, answer


async def test_documents_are_paged_by_year_then_id_with_the_undated_last(api_client, update):
    await update("letters", yearIssued=1851)  # the chronicle's year: the id decides (…d001 before …d002)

    pages, last = await _document_pages(api_client, limit=1)
    assert pages == [["Kronika obce Lhota"], ["Dopisy z Prahy"], ["Pražský věstník"]]
    assert (last["total_count"], last["bounded"], last["order"]) == (3, False, "year_asc")
    # A page across the last dated and the first undated document.
    straddling = await api_client.post("/api/search/documents", json={"criteria": {}, "limit": 2, "offset": 1})
    assert [d["document"]["title"] for d in straddling.json()["items"]] == ["Dopisy z Prahy", "Pražský věstník"]

    await update("chronicle", yearIssued=None)  # now undated too: the undated follow by id
    pages, _ = await _document_pages(api_client, limit=2)
    assert pages == [["Dopisy z Prahy", "Kronika obce Lhota"], ["Pražský věstník"]]


async def test_documents_of_a_collection_need_read_access(api_client, login, ids):
    async def titles(user, collection):
        response = await api_client.post("/api/search/documents", headers=await login(user), json={
            "criteria": {}, "user_collection_id": ids.col[collection]})
        return response.status_code, sorted(d["document"]["title"] for d in response.json().get("items", []))

    assert await titles("annotator", "chronicles") == (200, ["Dopisy z Prahy", "Kronika obce Lhota"])  # shared
    assert await titles("owner", "newspapers") == (200, ["Kronika obce Lhota", "Pražský věstník"])
    assert (await titles("outsider", "chronicles"))[0] == 404
    assert (await titles(None, "chronicles"))[0] == 401
