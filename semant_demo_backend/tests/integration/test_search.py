"""Search against the real test store (#205): adapter filters and the HTTP search contract.

The fixture corpus (tests/fixtures/corpus.json):

* "chronicles" (owner, shared with annotator): chronicle_1, chronicle_2, letters_1, letters_2;
  tags person, place.
* "newspapers" (owner only): chronicle_3, gazette_1, gazette_2; tag event.
* "outsider_notes" (outsider): gazette_1; tag outsider_tag.
* chunk tags: chronicle_1 positive person / automatic place, chronicle_2 positive place /
  negative person, chronicle_3 positive event, letters_1 automatic place.
* documents: chronicle (1851), letters (1902), gazette (no year); every chunk is "ces".
* classifications: chronicle_1 (narration, moderate, formal, two subject domains),
  letters_1 (interaction, informal); no other chunk has any.

Every exclusion test first shows that the excluded chunk matches the same query without
the restriction, so its absence comes from the filter.
"""
import pytest

from semant_demo.adapters.embeddings.gemma import GemmaEmbeddings
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.search import service
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, SearchType, TagFilter
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration

# One word of every chunk: an unrestricted BM25 search returns all seven.
ALL_WORDS = "Novák Požár Prahy rodinu Slavia trh"
NO_SUMMARY = {"search_title_generate": False, "search_summary_generate": False,
              "search_results_summary_generate": False}


@pytest.fixture
def chunks(seeded_store, collection_names) -> ChunkSearchRepository:
    return ChunkSearchRepository(seeded_store, collection_names)


@pytest.fixture
def keys(corpus):
    by_id = {c["id"]: key for key, c in corpus.chunks.items()}

    def of(results):
        return {by_id[str(r.id) if hasattr(r, "id") else r["id"]] for r in results}
    return of


def query(**kwargs) -> ChunkQuery:
    return ChunkQuery(**{"text": ALL_WORDS, "mode": SearchType.text, "limit": 50, **kwargs})


def tag_filter(ids, *names, automatic=False, positive=False) -> TagFilter:
    return TagFilter(tuple(ids.tag[n] for n in names), automatic=automatic, positive=positive)


###########
# Adapter #
###########

async def test_unrestricted_query_matches_every_chunk(chunks, keys, corpus):
    assert keys(await chunks.search(query())) == set(corpus.chunks)


async def test_limit_is_applied(chunks):
    assert len(await chunks.search(query(limit=2))) == 2


async def test_collection_scope_excludes_other_chunks(chunks, keys, ids):
    assert keys(await chunks.search(query(collection_id=ids.col["newspapers"]))) == {"chronicle_3", "gazette_1", "gazette_2"}
    assert keys(await chunks.search(query(collection_id=ids.col["outsider_notes"]))) == {"gazette_1"}


@pytest.mark.parametrize("tags, automatic, positive, expected", [
    (["person"], False, True, {"chronicle_1"}),
    (["person"], True, False, set()),                     # chronicle_2 has person only as negative
    (["person"], True, True, {"chronicle_1"}),
    (["place"], True, False, {"chronicle_1", "letters_1"}),
    (["place"], False, True, {"chronicle_2"}),
    (["place"], True, True, {"chronicle_1", "chronicle_2", "letters_1"}),
    (["person", "event"], False, True, {"chronicle_1", "chronicle_3"}),
    (["outsider_tag"], True, True, set()),
])
async def test_tag_filter_matches_the_requested_kinds_only(chunks, keys, ids, tags, automatic, positive, expected):
    found = await chunks.search(query(tags=tag_filter(ids, *tags, automatic=automatic, positive=positive)))
    assert keys(found) == expected


@pytest.mark.parametrize("condition, expected", [
    (FieldCondition("yearIssued", Op.greater_or_equal, 1900), {"letters_1", "letters_2"}),
    (FieldCondition("yearIssued", Op.less_or_equal, 1860), {"chronicle_1", "chronicle_2", "chronicle_3"}),
    (FieldCondition("language", Op.equal, "ces"), {"chronicle_1", "chronicle_2", "chronicle_3", "letters_1",
                                                   "letters_2", "gazette_1", "gazette_2"}),
    (FieldCondition("language", Op.contains_any, ["deu", "ces"]), {"chronicle_1", "chronicle_2", "chronicle_3",
                                                                   "letters_1", "letters_2", "gazette_1", "gazette_2"}),
    (FieldCondition("language", Op.contains_any, ["deu"]), set()),
])
async def test_document_and_chunk_conditions(chunks, keys, condition, expected):
    assert keys(await chunks.search(query(conditions=(condition,)))) == expected


async def test_collection_tag_and_metadata_filters_compose(chunks, keys, ids):
    combined = query(
        collection_id=ids.col["chronicles"],
        tags=tag_filter(ids, "place", automatic=True, positive=True),
        conditions=(FieldCondition("yearIssued", Op.less_or_equal, 1860),
                    FieldCondition("language", Op.contains_any, ["ces"])),
    )
    # letters_1 has the place tag but is from 1902; chronicle_3 is from 1851 but in newspapers.
    assert keys(await chunks.search(combined)) == {"chronicle_1", "chronicle_2"}


@pytest.mark.parametrize("mode", [SearchType.vector, SearchType.hybrid])
async def test_vector_modes_apply_the_same_restrictions(chunks, keys, ids, corpus, mode):
    text = corpus.chunks["gazette_1"]["text"]
    vector_query = query(text=text, mode=mode, vector=fake_embedding(text), limit=3)

    unrestricted = await chunks.search(vector_query)
    assert keys(unrestricted[:1]) == {"gazette_1"}

    scoped = await chunks.search(query(text=text, mode=mode, vector=fake_embedding(text), limit=3,
                                       collection_id=ids.col["chronicles"]))
    tagged = await chunks.search(query(text=text, mode=mode, vector=fake_embedding(text), limit=3,
                                       tags=tag_filter(ids, "place", automatic=True)))
    assert len(scoped) == 3 and "gazette_1" not in keys(scoped)
    assert keys(scoped) <= {"chronicle_1", "chronicle_2", "letters_1", "letters_2"}
    assert keys(tagged) == {"chronicle_1", "letters_1"}


async def test_results_map_chunk_and_document(chunks, corpus):
    [hit] = await chunks.search(query(text="Slavia"))
    gazette = corpus.documents["gazette"]

    assert str(hit.id) == corpus.chunks["gazette_1"]["id"]
    assert hit.text == corpus.chunks["gazette_1"]["text"]
    assert str(hit.document) == gazette["id"] == str(hit.document_object.id)
    assert hit.document_object.title == gazette["properties"]["title"]
    assert hit.document_object.library == "mzk"  # missing library defaults as before


async def test_results_map_document_authors(chunks, corpus):
    [hit] = await chunks.search(query(text="Prahy"))

    assert str(hit.document) == corpus.documents["letters"]["id"]
    assert hit.document_object.author == ["Karel Pisatel", "Marie Pisatelová"]
    assert hit.document_object.yearIssued == 1902


@pytest.mark.parametrize("mode", list(SearchType))
async def test_results_carry_the_stored_classifications(chunks, corpus, mode):
    found = await chunks.search(query(mode=mode, vector=fake_embedding(ALL_WORDS)))

    assert len(found) == len(corpus.chunks)
    by_id = {str(hit.id): hit.metadata for hit in found}
    for chunk in corpus.chunks.values():
        assert by_id[chunk["id"]] == corpus.chunk_classifications.get(chunk["key"], {})
    # Stored values keep their order, properties follow the filter definitions.
    assert list(by_id[corpus.chunks["chronicle_1"]["id"]]) == ["communicative_mode", "complexity", "style",
                                                                "subject_domain"]
    assert list(by_id[corpus.chunks["letters_1"]["id"]]) == ["communicative_mode", "style"]


@pytest.mark.parametrize("condition, expected", [
    (FieldCondition("communicative_mode", Op.contains_any, ["narration"]), {"chronicle_1"}),
    (FieldCondition("communicative_mode", Op.contains_any, ["narration", "interaction"]), {"chronicle_1", "letters_1"}),
    (FieldCondition("subject_domain", Op.contains_any, ["news_and_current_affairs"]), {"chronicle_1"}),
    (FieldCondition("style", Op.contains_any, ["formal"]), {"chronicle_1"}),
    (FieldCondition("style", Op.contains_any, ["literary"]), set()),
])
async def test_classification_conditions(chunks, keys, condition, expected):
    assert keys(await chunks.search(query(conditions=(condition,)))) == expected


async def test_document_filter_stats(chunks):
    assert await chunks.document_filter_stats() == (1851, 1902, ["ces"])


########
# HTTP #
########

@pytest.fixture
def post_search(api_client, login, ids):
    async def run(user, *, tags=(), collection=None, automatic=True, positive=True, **extra):
        body = {"query": ALL_WORDS, "type": "text", "limit": 50, "tag_uuids": [ids.tag.get(t, t) for t in tags],
                "automatic": automatic, "positive": positive, **NO_SUMMARY, **extra}
        if collection is not None:
            body["user_collection_id"] = ids.col.get(collection, collection)
        return await api_client.post("/api/search", headers=await login(user), json=body)
    return run


@pytest.fixture
def retrievals(monkeypatch):
    """Records every query that reaches the search adapter."""
    calls = []
    original = ChunkSearchRepository.search

    async def recording(self, q):
        calls.append(q)
        return await original(self, q)
    monkeypatch.setattr(ChunkSearchRepository, "search", recording)
    return calls


async def test_anonymous_public_search_covers_the_corpus(post_search, keys, corpus):
    response = await post_search(None)

    assert response.status_code == 200, response.text
    assert keys(response.json()["results"]) == set(corpus.chunks)
    assert response.json()["warnings"] == []


@pytest.mark.parametrize("user, tags, collection, expected", [
    ("owner", ["person"], None, {"chronicle_1"}),
    ("owner", ["person", "event"], None, {"chronicle_1", "chronicle_3"}),   # tags of two own collections
    ("owner", ["place"], "chronicles", {"chronicle_1", "chronicle_2", "letters_1"}),
    ("annotator", ["place"], None, {"chronicle_1", "chronicle_2", "letters_1"}),  # shared collection
    ("annotator", ["place"], "chronicles", {"chronicle_1", "chronicle_2", "letters_1"}),
    ("outsider", ["outsider_tag"], None, set()),
    ("outsider", [], "outsider_notes", {"gazette_1"}),
])
async def test_permitted_tag_filters(post_search, keys, user, tags, collection, expected):
    response = await post_search(user, tags=tags, collection=collection)

    assert response.status_code == 200, response.text
    assert keys(response.json()["results"]) == expected


UNKNOWN_TAG = "5e3a0000-0000-4000-8000-0000000eafff"


@pytest.mark.parametrize("user, tags, collection", [
    ("owner", ["outsider_tag"], None),                 # another user's tag
    ("owner", ["person", "outsider_tag"], None),       # permitted mixed with inaccessible
    ("owner", [UNKNOWN_TAG], None),
    ("owner", ["not-a-uuid"], None),
    ("owner", ["event"], "chronicles"),                # own tag, but not of the searched collection
    ("owner", ["person", "outsider_tag"], "chronicles"),
    ("annotator", ["event"], None),                    # owner's collection not shared with annotator
    ("annotator", ["place", "event"], "chronicles"),
    ("outsider", ["person"], None),
    ("outsider", ["outsider_tag", "person"], None),
    ("admin", ["person"], None),                       # no admin bypass
])
async def test_inaccessible_tags_are_refused_before_retrieval(post_search, retrievals, user, tags, collection):
    response = await post_search(user, tags=tags, collection=collection)

    assert response.status_code == 404, response.text
    # Unknown and other users' tags get the same answer.
    assert response.json() == {"detail": "Tag not found"}
    assert retrievals == []


async def test_tags_are_authorized_even_when_no_tag_kind_is_selected(post_search, retrievals):
    response = await post_search("owner", tags=["outsider_tag"], automatic=False, positive=False)

    assert response.status_code == 404
    assert retrievals == []


@pytest.mark.parametrize("tags", [["person"], ["not-a-uuid"], [UNKNOWN_TAG]])
async def test_anonymous_tag_filter_needs_login(post_search, retrievals, tags):
    response = await post_search(None, tags=tags)

    assert response.status_code == 401
    assert retrievals == []


@pytest.mark.parametrize("user, collection, expected", [
    ("outsider", "chronicles", 404), (None, "chronicles", 401), ("owner", UNKNOWN_TAG, 404),
])
async def test_unreadable_collection_is_refused_before_retrieval(post_search, retrievals, user, collection, expected):
    response = await post_search(user, collection=collection)

    assert response.status_code == expected
    assert retrievals == []


async def test_configured_filters_and_legacy_fields(post_search, keys):
    filtered = await post_search("owner", filters=[{"id": "year_range", "min_value": 1900, "max_value": 1950},
                                                  {"id": "language", "values": ["Czech"]}])
    legacy = await post_search("owner", min_year=1900, max_year=1950, language="ces")
    # Requested filters replace the legacy fields.
    both = await post_search("owner", min_year=1800, filters=[{"id": "year_range", "min_value": 1900}])

    for response in (filtered, legacy, both):
        assert response.status_code == 200, response.text
        assert keys(response.json()["results"]) == {"letters_1", "letters_2"}


async def test_invalid_filter_is_a_bad_request(post_search, retrievals):
    response = await post_search("owner", filters=[{"id": "language", "values": ["Klingon"]}])

    assert response.status_code == 400
    assert "Klingon" in response.json()["detail"]
    assert retrievals == []


@pytest.mark.parametrize("search_type, is_hyde", [("vector", False), ("hybrid", False), ("hybrid", True)])
async def test_vector_search_uses_the_injected_embeddings(post_search, keys, monkeypatch, corpus, search_type, is_hyde):
    calls = []

    async def embed_query(self, text):
        calls.append("query")
        return fake_embedding(text)

    async def embed_document(self, text):
        calls.append("document")
        return fake_embedding(text)
    monkeypatch.setattr(GemmaEmbeddings, "embed_query", embed_query)
    monkeypatch.setattr(GemmaEmbeddings, "embed_document", embed_document)
    text = corpus.chunks["gazette_1"]["text"]

    unscoped = await post_search("owner", query=text, type=search_type, is_hyde=is_hyde, limit=3)
    scoped = await post_search("owner", query=text, type=search_type, is_hyde=is_hyde, limit=3, collection="chronicles")

    assert unscoped.status_code == scoped.status_code == 200
    assert unscoped.json()["results"][0]["id"] == corpus.chunks["gazette_1"]["id"]
    assert "gazette_1" not in keys(scoped.json()["results"])
    assert calls == ["document" if is_hyde else "query"] * 2


async def test_summary_failure_returns_the_results_with_a_warning(post_search, keys, monkeypatch, corpus):
    from semant_demo.summarization.templated import TemplatedSearchResultsSummarizer

    async def failing(self, query, text, prompt=None, model=None, brevity=None):
        raise ConnectionError("summary provider down")
    monkeypatch.setattr(TemplatedSearchResultsSummarizer, "gen_title", failing)

    response = await post_search("owner", search_title_generate=True)

    assert response.status_code == 200, response.text
    assert keys(response.json()["results"]) == set(corpus.chunks)
    assert response.json()["warnings"] == [service.SUMMARY_FAILED_WARNING]


async def test_classification_filter_and_hit_metadata(post_search, keys, corpus):
    response = await post_search("owner", filters=[{"id": "style", "values": ["Informal"]}])

    assert response.status_code == 200, response.text
    [hit] = response.json()["results"]
    assert keys([hit]) == {"letters_1"}
    assert hit["metadata"] == {"communicative_mode": ["interaction"], "style": ["informal"]}

    unfiltered = await post_search("owner")
    assert {r["id"]: r["metadata"] for r in unfiltered.json()["results"]}[corpus.chunks["gazette_1"]["id"]] == {}
