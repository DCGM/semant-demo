"""Corpus overview against the real test store (#254).

Documents are counted once however many chunks they have (the fixture chronicle has three).
Like the local snapshot, the fixture store declares no ``library`` property: the overview
reports it unavailable until it is added (``add_text_property``). Further documents cover
the decade boundary (1909/1910), invalid years and missing, empty and multi-word values.
"""
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository, Unavailable, ValueCounts
from semant_demo.adapters.weaviate.document_metadata import add_text_property

pytestmark = pytest.mark.integration

PATH = "/api/analytics/corpus/overview"
EXTRA = [UUID(f"5e3a0000-0000-4000-8000-0000000da0{n:02}") for n in range(1, 9)]


async def test_overview_counts_fixture_documents_once_and_reports_missing_library(api_client, corpus):
    response = await api_client.get(PATH)  # anonymous

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == len(corpus.documents) == 3
    # chronicle 1851 (three chunks), letters 1902, gazette without a year
    assert body["publication_year"]["bins"] == [
        {"start": start, "end_exclusive": start + 10, "count": 1 if start in (1850, 1900) else 0}
        for start in range(1850, 1910, 10)]
    assert body["publication_year"]["unknown_count"] == 1
    assert body["languages"]["values"] == [{"value": "ces", "count": 3}]
    assert (body["languages"]["other_count"], body["languages"]["unknown_count"]) == (0, 0)
    assert body["libraries"] == {"available": False, "unavailable_reason": "missing_property",
                                 "values": None, "other_count": None, "unknown_count": None}


async def test_overview_accounts_for_every_document(api_client, seeded_store, collection_names):
    await add_text_property(seeded_store, collection_names, "library")
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([DataObject(uuid=uuid, properties=properties) for uuid, properties in zip(EXTRA, [
        {"yearIssued": 1909, "library": "mzk", "language": "deu"},
        {"yearIssued": 1910, "library": "mzk", "language": "deu"},
        {"yearIssued": 1919, "library": "nkp", "language": "lat"},
        {"yearIssued": 0, "library": "", "language": ""},
        {"yearIssued": 1909.5, "library": "  ", "language": "Old Czech"},
        {"library": "mzk"},
        {"language": "ces"},
        {},
    ])])
    assert not inserted.errors

    body = (await api_client.get(PATH)).json()

    total = 3 + len(EXTRA)
    assert body["total_documents"] == total
    years = body["publication_year"]
    assert [(b["start"], b["count"]) for b in years["bins"]][-2:] == [(1900, 2), (1910, 2)]  # 1902, 1909 | 1910, 1919
    # gazette, 0, 1909.5 and three documents without a year
    assert years["unknown_count"] == 6
    assert body["libraries"]["values"] == [{"value": "mzk", "count": 3}, {"value": "nkp", "count": 1}]
    # three fixture documents and two extra without a library, two with an empty one
    assert body["libraries"]["unknown_count"] == 7
    assert body["languages"]["values"] == [{"value": "ces", "count": 4}, {"value": "deu", "count": 2},
                                           {"value": "Old Czech", "count": 1}, {"value": "lat", "count": 1}]
    assert body["languages"]["unknown_count"] == 3
    for name in ("libraries", "languages"):
        d = body[name]
        assert sum(v["count"] for v in d["values"]) + d["other_count"] + d["unknown_count"] == total
    assert sum(b["count"] for b in years["bins"]) + years["unknown_count"] == total


async def test_repository_reads_through_an_alias_and_rejects_list_properties(seeded_store, collection_names):
    # The deployment serves Documents as an alias of the collection.
    alias = "AnalyticsTestDocuments"
    await seeded_store.alias.create(alias_name=alias, target_collection=collection_names.document_collection_name)
    try:
        names = collection_names.model_copy(update={"document_collection_name": alias})
        counts = await CorpusAnalyticsRepository(seeded_store, names).count_documents(
            {"language": "text", "author": "text", "yearIssued": "text", "nothing": "number"}, group_limit=1)
    finally:
        await seeded_store.alias.delete(alias_name=alias)

    assert counts.total == 3
    assert counts.properties["language"] == ValueCounts(known=3, groups=[("ces", 3)], complete=False)
    assert counts.properties["author"] == Unavailable("unsupported_type")  # text[]: several per document
    assert counts.properties["yearIssued"] == Unavailable("unsupported_type")
    assert counts.properties["nothing"] == Unavailable("missing")
