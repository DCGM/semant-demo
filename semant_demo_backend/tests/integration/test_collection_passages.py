"""Counts of the passages included in a user collection (#807) against the real test store.

A collection's included passages are the chunks linked to it (``Chunks.userCollection``), as
``CollectionStats.chunks_count`` counts them: not every chunk of its documents, and also a chunk
whose document is not linked. They are counted by the language detected in their text
(``Chunks.language``) or by the values of one classification (``text[]``: a passage counts once
per value it holds). The classifications have ``word`` tokenization (#533), so the grouping by
whole values and the "without a value" count are checked with values sharing words.

Fixture (tests/fixtures/corpus.json): "chronicles" includes chronicle_1, chronicle_2, letters_1
and letters_2 (owned by owner, shared with the annotator); "newspapers" includes chronicle_3,
gazette_1 and gazette_2 (not shared). Every fixture chunk is "ces"; chronicle_1 and letters_1
have classifications (chronicle_1: complexity ["moderate"], style ["formal"]; letters_1: style
["informal"]).
"""
import pytest

from semant_demo.features.documents.criteria import ChunkVocabulary
from semant_demo.routes.dependencies import get_chunk_vocabulary

pytestmark = pytest.mark.integration

PASSAGES = "/api/analytics/collection/passages"


@pytest.fixture
def post(api_client, login):
    async def run(body, user="owner", status=200):
        response = await api_client.post(PASSAGES, headers=await login(user), json=body)
        assert response.status_code == status, response.text
        return response.json()
    return run


@pytest.fixture
def update(seeded_store, collection_names, ids):
    """Changes stored properties of a fixture chunk, by key."""
    async def run(key, **properties):
        chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
        await chunks.data.update(uuid=ids.chunk[key], properties=properties)
    return run


def counted(classification) -> dict[str, int]:
    """The values some passage holds (configured values with no passage left out)."""
    return {v["value"]: v["count"] for v in classification["values"] if v["count"]}


def languages(body) -> dict[str, int]:
    return {v["value"]: v["count"] for v in body["languages"]["values"]}


async def test_the_total_is_the_collections_chunks_count_and_not_its_documents_chunks(post, api_client, login, ids,
                                                                                    seeded_store, collection_names):
    chronicles = ids.col["chronicles"]
    # A chunk included without linking its document counts; chronicle_3 of a linked document does not.
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    await chunks.data.reference_add(from_uuid=ids.chunk["gazette_1"],
                                    from_property=collection_names.user_collection_link_name, to=chronicles)

    body = await post({"user_collection_id": chronicles})
    stats = await api_client.get(f"/api/user_collections/{chronicles}/stats", headers=await login("owner"))

    assert (body["scope"], body["user_collection_id"], body["unit"], body["data_source"]) == \
        ("user_collection", chronicles, "passages", "live_aggregation")
    assert body["total_passages"] == stats.json()["chunks_count"] == 5
    assert body["classification"] is None
    assert languages(body) == {"ces": 5}
    assert (body["languages"]["other_count"], body["languages"]["unknown_count"]) == (0, 0)


async def test_a_passage_without_language_is_unknown_and_a_stored_und_is_a_value(post, update, ids):
    await update("chronicle_1", language="und")
    await update("letters_1", language=None)  # no language stored
    await update("letters_2", language="")

    body = await post({"user_collection_id": ids.col["chronicles"]})

    assert languages(body) == {"ces": 1, "und": 1}
    assert body["languages"]["unknown_count"] == 2


async def test_classification_values_are_counted_per_passage_in_vocabulary_order(post, update, ids):
    await update("chronicle_2", complexity=["easy", "moderate"])

    body = await post({"user_collection_id": ids.col["chronicles"], "dimension": "complexity"})

    assert (body["total_passages"], body["languages"]) == (4, None)
    classification = body["classification"]
    assert (classification["dimension"], classification["available"]) == ("complexity", True)
    assert [v["value"] for v in classification["values"]] == ["very_easy", "easy", "moderate", "advanced", "expert"]
    assert all(v["configured"] for v in classification["values"])
    # Multi-valued: 3 values on 2 passages; the other 2 passages hold none.
    assert counted(classification) == {"moderate": 2, "easy": 1}
    assert (classification["without_value_count"], classification["without_value_approximate"]) == (2, False)


async def test_values_sharing_words_are_kept_apart_and_without_value_is_exact(post, update, ids):
    # Word tokenization (#533): a filter for "easy" would also match "very_easy".
    await update("chronicle_1", complexity=["very_easy"])
    await update("chronicle_2", complexity=["easy", "very_easy"])

    classification = (await post({"user_collection_id": ids.col["chronicles"], "dimension": "complexity"}))[
        "classification"]

    assert counted(classification) == {"very_easy": 2, "easy": 1}
    assert classification["without_value_count"] == 2  # letters_1 and letters_2


async def test_a_value_outside_the_vocabulary_is_its_own_bar_and_without_value_is_approximate(post, update, ids):
    await update("letters_2", style=["unheard_of"])

    classification = (await post({"user_collection_id": ids.col["chronicles"], "dimension": "style"}))[
        "classification"]

    assert counted(classification) == {"formal": 1, "informal": 1, "unheard_of": 1}
    assert classification["values"][-1] == {"value": "unheard_of", "count": 1, "configured": False}
    assert classification["without_value_approximate"] is True


async def test_the_configured_values_come_from_the_search_filters(post, ids, api_app):
    # A deployment's filters configure "formal" and a value no passage holds, not "informal".
    api_app.dependency_overrides[get_chunk_vocabulary] = \
        lambda: ChunkVocabulary(classifications={"style": ("formal", "folksy")})

    classification = (await post({"user_collection_id": ids.col["chronicles"], "dimension": "style"}))[
        "classification"]
    unconfigured = await post({"user_collection_id": ids.col["chronicles"], "dimension": "complexity"}, status=400)

    assert [(v["value"], v["count"], v["configured"]) for v in classification["values"]] == \
        [("formal", 1, True), ("folksy", 0, True), ("informal", 1, False)]
    # letters_1 holds only "informal": not a configured value, so it may count as without one.
    assert (classification["without_value_count"], classification["without_value_approximate"]) == (3, True)
    assert "not a configured classification" in unconfigured["detail"]


async def test_another_collection_counts_only_its_own_passages(post, ids):
    newspapers = await post({"user_collection_id": ids.col["newspapers"], "dimension": "style"})

    assert newspapers["total_passages"] == 3
    assert counted(newspapers["classification"]) == {}  # chronicle_1 and letters_1 are in "chronicles"
    assert newspapers["classification"]["without_value_count"] == 3


async def test_an_empty_collection_counts_zero(post, api_client, login):
    created = await api_client.post("/api/user_collections", headers=await login("owner"),
                                    json={"name": "Prázdná", "description": None, "color": "green"})
    assert created.status_code == 201, created.text
    empty = created.json()["id"]

    body = await post({"user_collection_id": empty})
    dimension = await post({"user_collection_id": empty, "dimension": "subject_domain"})

    assert (body["total_passages"], body["languages"]["values"], body["languages"]["unknown_count"]) == (0, [], 0)
    assert dimension["classification"]["without_value_count"] == 0
    assert counted(dimension["classification"]) == {}


async def test_only_readers_of_the_collection_get_its_passage_counts(post, api_client, login, ids):
    newspapers = {"user_collection_id": ids.col["newspapers"]}
    await post(newspapers, user="annotator", status=404)  # not shared: as if it did not exist
    await post(newspapers, user="outsider", status=404)
    await post(newspapers, user=None, status=401)
    await post({"user_collection_id": "5e3a0000-0000-4000-8000-0000000c0fff"}, status=404)
    await post({**newspapers, "dimension": "not_a_classification"}, status=422)

    chronicles = {"user_collection_id": ids.col["chronicles"], "dimension": "style"}
    await post(chronicles, user="annotator")
    revoked = await api_client.delete(f"/api/user_collections/{ids.col['chronicles']}/share/{ids.user['annotator']}",
                                      headers=await login("owner"))
    assert revoked.status_code == 200
    await post(chronicles, user="annotator", status=404)
