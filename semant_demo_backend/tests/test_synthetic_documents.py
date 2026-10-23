"""The synthetic development documents (#361): deterministic, recognizable and plausible."""
from collections import Counter

import pytest

from tests.corpus import load_corpus
from tests.synthetic_documents import MAX_COUNT, is_synthetic, synthetic_documents

LIBRARIES = {"mzk", "nkp", "svkhk", "vkol"}
LANGUAGES = {"ces", "deu", "lat", "slk", "cze"}


def test_a_larger_count_keeps_the_earlier_documents_unchanged():
    assert list(synthetic_documents(50, outliers=False)) == list(synthetic_documents(80, outliers=False))[:50]


def test_ids_are_unique_and_distinct_from_the_fixture_corpus():
    ids = [uuid for uuid, _ in synthetic_documents(500, outliers=True)]

    assert len(set(ids)) == len(ids) == 502
    assert all(is_synthetic(uuid) for uuid in ids)
    assert not any(is_synthetic(document["id"]) for document in load_corpus().documents.values())


def test_the_values_are_plausible_and_include_missing_metadata():
    documents = [properties for _, properties in synthetic_documents(2000, outliers=False)]

    years = [d["yearIssued"] for d in documents if "yearIssued" in d]
    assert all(isinstance(year, int) and 1600 <= year <= 2000 for year in years)
    assert 0.02 < 1 - len(years) / len(documents) < 0.09
    assert sum(1850 <= year <= 1940 for year in years) > len(years) / 2
    assert {1909, 1910} <= set(years)  # both sides of a decade boundary
    libraries = Counter(d.get("library") for d in documents)
    assert set(libraries) == LIBRARIES | {None}
    languages = Counter(d.get("language") for d in documents)
    assert set(languages) == LANGUAGES | {None}  # ces and cze share the display name Czech
    assert all(d["title"].strip() and d["public"] is True for d in documents)
    assert any(set(d["title"]) & set("ěščřžýáíéůú") for d in documents)


@pytest.mark.parametrize("outliers, expected", [(True, {311, 2879}), (False, set())])
def test_the_outlier_years_are_added_only_when_asked(outliers, expected):
    years = {d.get("yearIssued") for _, d in synthetic_documents(2000, outliers=outliers)}

    assert {year for year in years if year is not None and not 1600 <= year <= 2000} == expected


@pytest.mark.parametrize("count", [-1, MAX_COUNT + 1])
def test_a_count_out_of_range_is_rejected(count):
    with pytest.raises(ValueError):
        next(synthetic_documents(count, outliers=True))
