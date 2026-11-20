"""Document counts of a user collection (#622, #768) against the real test store.

A collection's documents are those linked to it (``Documents.collection``), as its document
list, ``CollectionStats.documents_count`` and Explore's Documents Results read them: a linked
document counts even with no included passage, and an included passage whose document is not
linked does not make the document count. Every count (total, grouped by year, library and
language, and the heatmap's per-library rows) has the same restriction.

Fixture (tests/fixtures/corpus.json): "chronicles" links the chronicle (1851) and the letters
(1902), owned by owner and shared with the annotator; "newspapers" links the chronicle and the
gazette (no year), not shared. All three documents are "ces" without a library. The tests add
public metadata-only documents (no chunks) and links; corpus counts without a collection cover
only public documents (#279).
"""
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.maintenance import chunk_summaries, chunk_summary_schema

pytestmark = pytest.mark.integration

DISTRIBUTIONS = "/api/analytics/corpus/distributions"
LIBRARY_YEARS = "/api/analytics/corpus/library-years"
OVERVIEW = "/api/analytics/corpus/overview"
EXTRA = {f"extra{n}": UUID(f"5e3a0000-0000-4000-8000-0000000da1{n:02}") for n in range(1, 7)}
EXTRA_PROPERTIES = {
    "extra1": {"title": "Brněnské listy", "yearIssued": 1909, "library": "mzk", "language": "ces", "public": True},
    "extra2": {"title": "Brněnský týdeník", "yearIssued": 1910, "library": "mzk", "language": "deu", "public": True},
    "extra3": {"title": "Pražský kalendář", "yearIssued": 1910, "library": "nkp", "language": "ces", "public": True},
    "extra4": {"title": "Olomoucké noviny", "yearIssued": 1920, "library": "vkol", "language": "lat", "public": True},
    # Not linked to a collection: in the corpus only.
    "extra5": {"title": "Vídeňské noviny", "yearIssued": 1909, "library": "mzk", "language": "deu", "public": True},
    "extra6": {"title": "Jiný kalendář", "yearIssued": 1950, "library": "nkp", "language": "ces", "public": True},
}


@pytest.fixture
def post(api_client, login):
    async def run(path, body, user=None, status=200):
        response = await api_client.post(path, headers=await login(user), json=body)
        assert response.status_code == status, response.text
        return response.json()
    return run


@pytest.fixture
async def chronicles(seeded_store, collection_names, ids):
    """Adds the extra documents; links extra1..4 to "chronicles" (they have no passages at all) and
    includes the gazette's first passage in it without linking the gazette."""
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([DataObject(uuid=EXTRA[key], properties=properties)
                                                 for key, properties in EXTRA_PROPERTIES.items()])
    assert not inserted.errors
    collection = ids.col["chronicles"]
    for key in ("extra1", "extra2", "extra3", "extra4"):
        await documents.data.reference_add(from_uuid=EXTRA[key], from_property="collection", to=collection)
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    await chunks.data.reference_add(from_uuid=ids.chunk["gazette_1"],
                                    from_property=collection_names.user_collection_link_name, to=collection)
    return collection


def years(body) -> dict[int, int]:
    return {y["year"]: y["count"] for y in body["publication_year"]["years"]}


def values(distribution) -> dict[str, int]:
    return {v["value"]: v["count"] for v in distribution["values"]}


async def test_a_collection_counts_exactly_its_linked_documents(post, chronicles, api_client, login):
    body = await post(DISTRIBUTIONS, {"user_collection_id": chronicles}, user="owner")

    assert (body["scope"], body["user_collection_id"], body["data_source"]) == \
        ("user_collection", chronicles, "live_aggregation")
    # chronicle, letters and extra1..4; not the gazette (only a passage of it is included), not extra5/6.
    assert body["total_documents"] == 6
    assert years(body) == {1851: 1, 1902: 1, 1909: 1, 1910: 2, 1920: 1}
    assert body["publication_year"]["unknown_count"] == 0
    assert values(body["libraries"]) == {"mzk": 2, "nkp": 1, "vkol": 1}
    assert body["libraries"]["unknown_count"] == 2
    assert values(body["languages"]) == {"ces": 4, "deu": 1, "lat": 1}

    # The same documents as the collection's statistics and Explore's Documents Results.
    stats = await api_client.get(f"/api/user_collections/{chronicles}/stats", headers=await login("owner"))
    assert stats.json()["documents_count"] == 6
    browse = await post("/api/search/documents", {"type": "text", "criteria": {}, "user_collection_id": chronicles},
                        user="owner")
    assert browse["total_count"] == 6

    # A shared member reads the same counts.
    shared = await post(DISTRIBUTIONS, {"user_collection_id": chronicles}, user="annotator")
    assert shared["total_documents"] == 6


async def test_heatmap_rows_of_a_collection_add_up_to_its_documents(post, chronicles):
    body = await post(LIBRARY_YEARS, {"user_collection_id": chronicles}, user="owner")

    assert (body["scope"], body["user_collection_id"], body["available"]) == ("user_collection", chronicles, True)
    assert body["total_documents"] == 6
    rows = [(r["library"], r["kind"], r["total_documents"], {y["year"]: y["count"] for y in r["years"]})
            for r in body["rows"]]
    # mzk has extra5 (1909) in the corpus too: the per-library counts are of the collection only.
    assert rows == [("mzk", "value", 2, {1909: 1, 1910: 1}), ("nkp", "value", 1, {1910: 1}),
                    ("vkol", "value", 1, {1920: 1}), (None, "unknown", 2, {1851: 1, 1902: 1})]


async def test_a_document_without_included_passages_counts(post, seeded_store, collection_names, ids):
    # extra1 has no chunks at all; linked to "newspapers" besides the chronicle and the gazette.
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([DataObject(uuid=EXTRA["extra1"], properties=EXTRA_PROPERTIES["extra1"])])
    assert not inserted.errors
    await documents.data.reference_add(from_uuid=EXTRA["extra1"], from_property="collection", to=ids.col["newspapers"])

    body = await post(DISTRIBUTIONS, {"user_collection_id": ids.col["newspapers"]}, user="owner")

    assert body["total_documents"] == 3
    assert years(body) == {1851: 1, 1909: 1}
    assert body["publication_year"]["unknown_count"] == 1  # the gazette


async def test_filters_apply_within_the_collection(post, chronicles):
    body = await post(DISTRIBUTIONS, {"user_collection_id": chronicles,
                                      "filters": {"year_min": 1900, "year_max": 1915, "libraries": ["mzk", "nkp"]}},
                      user="owner")

    # extra1..3; extra5 (mzk, 1909) is not in the collection.
    assert body["total_documents"] == 3
    assert body["filters"]["libraries"] == ["mzk", "nkp"]
    heatmap = await post(LIBRARY_YEARS, {"user_collection_id": chronicles, "filters": {"libraries": ["mzk"]}},
                         user="owner")
    assert [(r["library"], r["total_documents"]) for r in heatmap["rows"]] == [("mzk", 2)]


async def test_chunk_filters_apply_within_the_collection(post, ids, seeded_store, collection_names, tmp_path):
    await chunk_summary_schema.update(seeded_store, collection_names, apply=True)
    await chunk_summaries.run(seeded_store, collection_names, report=tmp_path / "summaries.json",
                              endpoint="test", write=True, progress=lambda line: None)
    narration = {"classifications": {"communicative_mode": ["narration"]}}

    chronicles = await post(DISTRIBUTIONS, {"user_collection_id": ids.col["chronicles"], "chunk_filters": narration},
                            user="owner")
    corpus = await post(DISTRIBUTIONS, {"chunk_filters": narration})

    # Only chronicle_1 is narration: the chronicle, in both scopes (whole-document summaries).
    assert (chronicles["total_documents"], years(chronicles)) == (1, {1851: 1})
    assert chronicles["chunk_filters"]["classifications"] == {"communicative_mode": ["narration"]}
    assert corpus["total_documents"] == 1
    interaction = await post(DISTRIBUTIONS, {"user_collection_id": ids.col["newspapers"],
                                             "chunk_filters": {"classifications": {"communicative_mode": ["interaction"]}}},
                             user="owner")
    assert interaction["total_documents"] == 0  # the letters are not in "newspapers"


async def test_an_empty_collection_counts_zero(post, api_client, login):
    created = await api_client.post("/api/user_collections", headers=await login("owner"),
                                    json={"name": "Prázdná", "description": None, "color": "green"})
    assert created.status_code == 201, created.text
    empty = created.json()["id"]

    body = await post(DISTRIBUTIONS, {"user_collection_id": empty}, user="owner")
    heatmap = await post(LIBRARY_YEARS, {"user_collection_id": empty}, user="owner")

    assert (body["scope"], body["total_documents"], body["publication_year"]["years"]) == ("user_collection", 0, [])
    assert (heatmap["total_documents"], heatmap["rows"]) == (0, [])


async def test_a_collection_is_not_answered_from_the_warm_corpus_cache(post, chronicles, api_client):
    corpus = (await api_client.get(OVERVIEW)).json()
    assert corpus["total_documents"] == 9  # three fixture and six extra documents, now cached
    assert (await post(DISTRIBUTIONS, {}))["data_source"] == "cached_aggregation"

    body = await post(DISTRIBUTIONS, {"user_collection_id": chronicles}, user="owner")

    assert (body["scope"], body["total_documents"], body["data_source"]) == ("user_collection", 6, "live_aggregation")
    after = await post(DISTRIBUTIONS, {})
    assert (after["scope"], after["total_documents"], after["data_source"]) == \
        ("searchable_corpus", 9, "cached_aggregation")


@pytest.mark.parametrize("path", [DISTRIBUTIONS, LIBRARY_YEARS])
async def test_only_readers_of_the_collection_get_its_counts(post, api_client, login, ids, path):
    newspapers = {"user_collection_id": ids.col["newspapers"]}
    await post(path, newspapers, user="annotator", status=404)  # not shared: as if it did not exist
    await post(path, newspapers, user="outsider", status=404)
    await post(path, newspapers, status=401)  # anonymous callers read no collection
    await post(path, {"user_collection_id": "5e3a0000-0000-4000-8000-0000000c0fff"}, user="owner", status=404)

    chronicles = {"user_collection_id": ids.col["chronicles"]}
    await post(path, chronicles, user="annotator")
    revoked = await api_client.delete(f"/api/user_collections/{ids.col['chronicles']}/share/{ids.user['annotator']}",
                                      headers=await login("owner"))
    assert revoked.status_code == 200
    await post(path, chronicles, user="annotator", status=404)
