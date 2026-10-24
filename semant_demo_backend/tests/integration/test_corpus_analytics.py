"""Corpus overview against the real test store (#254).

Documents are counted once however many chunks they have (the fixture chronicle has three).
The fixture store declares the documents as production does (#496): ``library`` with
``field`` tokenization, ``yearIssued`` as ``int``. Older stores (``legacy_documents``) lack
``library`` and store ``number`` years such as 1909.5: the overview reports
the library unavailable and a fractional year as invalid. Further documents cover the decade
boundary (1909/1910), invalid years and missing, empty and multi-word values.

Filtered distributions (#361): every filter is checked against the documents it must match,
which pins down the store's matching (title words ignore case but not diacritics, ``word``
language values ignore case, ``field`` library codes only surrounding whitespace).
"""
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.adapters.weaviate.analytics import (
    AnyOf, CorpusAnalyticsRepository, NumberRange, Unavailable, UnavailableFilter, ValueCounts)

pytestmark = pytest.mark.integration

PATH = "/api/analytics/corpus/overview"
DISTRIBUTIONS = "/api/analytics/corpus/distributions"
EXTRA = [UUID(f"5e3a0000-0000-4000-8000-0000000da0{n:02}") for n in range(1, 9)]

# Fixture documents: chronicle "Kronika obce Lhota" 1851, letters "Dopisy z Prahy" 1902,
# gazette "Pražský věstník" without a year; all ces, no library.
FILTERED = {
    "skola": {"title": "Škola a život", "yearIssued": 1909, "library": "mzk", "language": "ces"},
    "skolni": {"title": "ŠKOLNÍ věstník", "yearIssued": 1910, "library": "nkp", "language": "CES"},
    "listy": {"title": "Listy z Brna", "yearIssued": 1908, "library": " mzk", "language": "Old Czech"},
    "plain": {"title": "Skola bez diakritiky", "yearIssued": 1920, "library": "MZK", "language": "deu"},
    "prazske": {"title": "Pražské listy", "language": "lat"},
}
FIXTURE_YEARS = {"chronicle": 1851, "letters": 1902, "gazette": None}


async def test_overview_counts_fixture_documents_once(api_client, corpus):
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
    assert body["libraries"] == {"available": True, "unavailable_reason": None,
                                 "values": [], "other_count": 0, "unknown_count": 3}


async def test_overview_of_a_legacy_store_reports_the_missing_library_and_fractional_years(
        legacy_documents, api_client, collection_names):
    documents = legacy_documents.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([DataObject(uuid=uuid, properties={"yearIssued": year})
                                                 for uuid, year in zip(EXTRA, [1909.0, 1909.5])])
    assert not inserted.errors

    body = (await api_client.get(PATH)).json()

    assert body["total_documents"] == 5
    # chronicle 1851; letters 1902 and 1909.0 | gazette without a year and 1909.5
    assert [(b["start"], b["count"]) for b in body["publication_year"]["bins"]][-1] == (1900, 2)
    assert body["publication_year"]["unknown_count"] == 2
    assert body["libraries"] == {"available": False, "unavailable_reason": "missing_property",
                                 "values": None, "other_count": None, "unknown_count": None}


async def test_overview_accounts_for_every_document(api_client, seeded_store, collection_names):
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([DataObject(uuid=uuid, properties=properties) for uuid, properties in zip(EXTRA, [
        {"yearIssued": 1909, "library": "mzk", "language": "deu"},
        {"yearIssued": 1910, "library": "mzk", "language": "deu"},
        {"yearIssued": 1919, "library": "nkp", "language": "lat"},
        {"yearIssued": 0, "library": "", "language": ""},
        {"yearIssued": -5, "library": "  ", "language": "Old Czech"},
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
    # gazette, 0, -5 and three documents without a year
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


async def _add_filtered_documents(store, collection_names):
    documents = store.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([
        DataObject(uuid=uuid, properties=properties) for uuid, properties in zip(EXTRA, FILTERED.values())])
    assert not inserted.errors


@pytest.mark.parametrize("filters, matching", [
    ({}, {"chronicle", "letters", "gazette", *FILTERED}),
    # Inclusive bounds.
    ({"year_min": 1909, "year_max": 1909}, {"skola"}),
    ({"year_min": 1910}, {"skolni", "plain"}),
    ({"year_min": 1900, "year_max": 1910}, {"letters", "skola", "skolni", "listy"}),
    # Title words: inside a title word, ignoring case, not diacritics; all words, any order.
    ({"title_contains": ["škol"]}, {"skola", "skolni"}),
    ({"title_contains": ["skol"]}, {"plain"}),
    ({"title_contains": ["listy-brn"]}, {"listy"}),  # "Listy z Brna"
    ({"title_contains": ["věstník pražský"]}, {"gazette"}),
    ({"title_contains": ["zzz"]}, set()),
    # Several titles: any of them.
    ({"title_contains": ["brn", "škol"]}, {"listy", "skola", "skolni"}),
    # library (field): exact apart from surrounding whitespace; several values: any of them.
    ({"libraries": ["mzk"]}, {"skola", "listy"}),
    ({"libraries": ["mzk", "nkp"]}, {"skola", "skolni", "listy"}),
    # language (word): ignoring case.
    ({"languages": ["ces"]}, {"chronicle", "letters", "gazette", "skola", "skolni"}),
    ({"languages": ["czech"]}, {"listy"}),
    ({"year_min": 1900, "year_max": 1920, "title_contains": ["škol"], "libraries": ["mzk", "nkp"],
      "languages": ["ces"]}, {"skola", "skolni"}),
])
async def test_filtered_counts_describe_exactly_the_matching_documents(
        api_client, seeded_store, collection_names, filters, matching):
    await _add_filtered_documents(seeded_store, collection_names)
    documents = {**{k: {"yearIssued": y, "language": "ces"} for k, y in FIXTURE_YEARS.items()}, **FILTERED}

    response = await api_client.post(DISTRIBUTIONS, json={"filters": filters})

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == len(matching)
    expected_years: dict[int, int] = {}
    for key in matching:
        year = documents[key].get("yearIssued")
        if year is not None and float(year).is_integer():
            expected_years[int(year)] = expected_years.get(int(year), 0) + 1
    assert body["publication_year"]["years"] == [{"year": y, "count": n} for y, n in sorted(expected_years.items())]
    assert body["publication_year"]["unknown_count"] == len(matching) - len([k for k in matching if
                                                                             documents[k].get("yearIssued") is not None
                                                                             and float(documents[k]["yearIssued"]).is_integer()])
    # Stored values stay apart: the language chart of "ces" shows ces and CES.
    expected_languages: dict[str, int] = {}
    for key in matching:
        expected_languages[documents[key]["language"]] = expected_languages.get(documents[key]["language"], 0) + 1
    assert {v["value"]: v["count"] for v in body["languages"]["values"]} == expected_languages
    for name in ("libraries", "languages"):
        d = body[name]
        assert sum(v["count"] for v in d["values"]) + d["other_count"] + d["unknown_count"] == len(matching)


async def test_a_library_filter_on_a_store_without_libraries_is_rejected(legacy_documents, api_client):
    response = await api_client.post(DISTRIBUTIONS, json={"filters": {"libraries": ["mzk"]}})

    assert response.status_code == 422
    assert "cannot be filtered by library" in response.json()["detail"]
    assert (await api_client.post(DISTRIBUTIONS, json={"filters": {"languages": ["ces"]}})).json()["total_documents"] == 3


async def test_repository_filters_a_legacy_store_through_an_alias(legacy_documents, collection_names):
    alias = "AnalyticsFilterDocuments"
    await legacy_documents.alias.create(alias_name=alias, target_collection=collection_names.document_collection_name)
    try:
        names = collection_names.model_copy(update={"document_collection_name": alias})
        repository = CorpusAnalyticsRepository(legacy_documents, names)
        counts = await repository.count_documents({"yearIssued": "number"}, group_limit=10,
                                                  conditions=[NumberRange("yearIssued", minimum=1900)])
        with pytest.raises(UnavailableFilter):
            await repository.count_documents({}, group_limit=10, conditions=[AnyOf("library", ("mzk",))])
    finally:
        await legacy_documents.alias.delete(alias_name=alias)

    assert counts.total == 1  # letters 1902
    assert counts.properties["yearIssued"] == ValueCounts(known=1, groups=[(1902.0, 1)], complete=True)


async def test_library_years_put_every_matching_document_in_one_row(api_client, seeded_store, collection_names):
    await _add_filtered_documents(seeded_store, collection_names)

    body = (await api_client.post("/api/analytics/corpus/library-years", json={})).json()

    assert (body["available"], body["total_documents"]) == (True, 8)
    rows = [(r["library"], r["kind"], r["total_documents"], [(y["year"], y["count"]) for y in r["years"]],
             r["unknown_year_count"]) for r in body["rows"]]
    assert rows == [
        # "mzk" and " mzk" are the same library (field tokenization).
        ("mzk", "value", 2, [(1908, 1), (1909, 1)], 0),
        # MZK is another stored code: library codes are case-sensitive.
        ("MZK", "value", 1, [(1920, 1)], 0),
        ("nkp", "value", 1, [(1910, 1)], 0),
        # The fixture documents and "Pražské listy" have no library.
        (None, "unknown", 4, [(1851, 1), (1902, 1)], 2)]

    filtered = (await api_client.post("/api/analytics/corpus/library-years",
                                      json={"filters": {"title_contains": ["škol"]}})).json()
    assert [(r["library"], r["total_documents"]) for r in filtered["rows"]] == [("mzk", 1), ("nkp", 1)]


async def test_library_years_count_fresh_totals_while_the_overview_is_cached(api_client, seeded_store,
                                                                            collection_names):
    # Review of #481: the unfiltered totals came from the overview cache while the libraries
    # were counted live, so documents added within CORPUS_OVERVIEW_MAX_AGE gave a 500.
    await _add_filtered_documents(seeded_store, collection_names)
    assert (await api_client.get(PATH)).json()["total_documents"] == 8  # now cached
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    inserted = await documents.data.insert_many([
        DataObject(uuid=uuid, properties={"title": "Nové listy", "yearIssued": 1910, "library": "nkp", "language": "ces"})
        for uuid in EXTRA[len(FILTERED):]])
    assert not inserted.errors

    response = await api_client.post("/api/analytics/corpus/library-years", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 11
    assert [(r["library"], r["total_documents"]) for r in body["rows"]] == \
        [("nkp", 4), ("mzk", 2), ("MZK", 1), (None, 4)]
    assert (await api_client.get(PATH)).json()["data_source"] == "cached_aggregation"
