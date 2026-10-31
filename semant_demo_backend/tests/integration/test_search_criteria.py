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

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.analytics import service as analytics
from semant_demo.features.documents.criteria import (
    ChunkFilters, DocumentFilters, chunk_conditions, document_conditions, validate_chunk_filters)
from semant_demo.features.search.filters import chunk_vocabulary, generate_default_filters
from semant_demo.features.search.schemas import ChunkQuery, SearchType

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

    for response in (searched, browsed):
        assert response.status_code == 422
        assert response.json()["detail"] == \
            "Documents cannot be filtered by library: this corpus database is not recorded."


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
