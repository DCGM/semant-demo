"""Synthetic development documents (#361) in a real store: ``add_documents`` declares the
missing ``library`` property, adds only documents not stored yet, and the corpus overview
and ``verify`` of the development tooling account for them.

The test store stands in for the development store: the ownership checks of
``cmd_add_documents`` are covered without Weaviate (``tests/test_local_dev.py``).
"""
import pytest

from tests import local_dev
from tests.synthetic_documents import is_synthetic

pytestmark = pytest.mark.integration


async def test_documents_are_added_once_and_counted_by_the_overview(api_client, seeded_store, collection_names,
                                                                     corpus):
    documents = seeded_store.collections.get(collection_names.document_collection_name)

    assert await local_dev.add_documents(seeded_store, 30, outliers=True) == 32
    assert await local_dev.add_documents(seeded_store, 30, outliers=True) == 0
    assert await local_dev.add_documents(seeded_store, 40, outliers=False) == 10

    library = next(p for p in (await documents.config.get()).properties if p.name == "library")
    assert library.tokenization.value == "field"
    stored = [o async for o in documents.iterator()]
    assert sum(is_synthetic(o.uuid) for o in stored) == 42
    assert len(stored) == len(corpus.documents) + 42
    body = (await api_client.get("/api/analytics/corpus/overview")).json()
    assert body["total_documents"] == len(stored)
    years = body["publication_year"]
    assert (years["bins"][0]["start"], years["bins"][-1]["start"]) == (310, 2870)  # the outliers
    libraries = body["libraries"]
    assert libraries["available"] and libraries["values"]
    assert sum(v["count"] for v in libraries["values"]) + libraries["other_count"] + libraries["unknown_count"] \
        == len(stored)


async def test_verify_reports_the_synthetic_documents_as_one_difference(seeded_store, corpus, tmp_path):
    profile = local_dev.Profile(data_dir=tmp_path)
    await local_dev.create_sqlite(profile.sqlite_path, corpus, token="t")
    assert await local_dev.verify(seeded_store, profile) == []

    await local_dev.add_documents(seeded_store, 25, outliers=True)

    assert await local_dev.verify(seeded_store, profile) == [
        "documents: 27 synthetic documents added (make dev-add-documents)"]
