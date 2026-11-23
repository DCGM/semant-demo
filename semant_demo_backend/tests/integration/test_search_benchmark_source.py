"""Sampling the search benchmark corpus from a real semANT store, read only (#726).

The fixture corpus: chronicle (3 chunks, 1851, BOOK), letters (2, 1902, LETTER) and gazette
(2, no year, PERIODICAL); every chunk's language is ``ces``.
"""
from collections import Counter
from uuid import UUID

import pytest

from semant_demo.benchmarks.search_relevance.config import GeneratorConfig
from semant_demo.benchmarks.search_relevance.sampling import sample_corpus
from semant_demo.benchmarks.search_relevance.source import WeaviateSource

pytestmark = pytest.mark.integration

FEATURES = ("search_benchmark_intents", "search_benchmark_translation", "search_benchmark_judge")


def config(**sample) -> GeneratorConfig:
    return GeneratorConfig.model_validate({
        "dataset_id": "it", "version": "v0", "languages": ["ces", "eng"],
        "models": {"tiers": {"tiny": {"provider": "ollama", "model": "fake", "price_basis": "local_rate",
                                      "input_price": 0, "output_price": 0}},
                   "features": {f: {"default": "tiny"} for f in FEATURES}},
        "sample": {"per_language": 5, "max_per_document": 2, "min_chars": 10, "scan_batch": 100, **sample},
        "pooling": {"methods": [{"id": "bm25", "mode": "text"}]}})


async def snapshot(client, names) -> dict:
    found = {}
    for name in (names.chunks_collection_name, names.document_collection_name):
        collection = client.collections.get(name)
        found[name] = sorted([(str(o.uuid), repr(sorted(o.properties.items())))
                              async for o in collection.iterator()])
    return found


async def test_sampling_reads_the_store_without_changing_it(seeded_store, collection_names, corpus):
    before = await snapshot(seeded_store, collection_names)
    source = WeaviateSource(seeded_store, collection_names, {"description": "fixture"})

    assert await source.languages() == {"ces": 7}
    chunks, report = await sample_corpus(source, config(context_fraction=1.0, context_neighbours=2))

    documents = {d["id"]: d for d in corpus.documents.values()}
    sampled = [c for c in chunks if c.attributes["sampled_by"] != "context"]
    assert len(sampled) == 5 and max(Counter(c.document_id for c in sampled).values()) == 2
    assert {c.chunk_id for c in chunks} <= {UUID(c["id"]) for c in corpus.chunks.values()}
    assert len(chunks) == 7  # the neighbours (two on each side) complete the documents
    for chunk in chunks:
        document = documents[str(chunk.document_id)]["properties"]
        assert chunk.document.title == document["title"]
        assert chunk.document.year == document.get("yearIssued")
        assert chunk.document.document_type == document["documentType"]
        assert chunk.language == "ces" and chunk.text
    assert report["short"] == {"eng": {"target": 5, "selected": 0}}
    context = [c for c in chunks if c.attributes["sampled_by"] == "context"]
    by_id = {c.chunk_id: c for c in chunks}
    assert all(by_id[UUID(c.attributes["context_of"])].document_id == c.document_id for c in context)

    scanned = [item async for item in source.scan(page=2)]  # pages of two: the cursor goes on across pages
    assert scanned == sorted(scanned, key=lambda item: item[0])  # in id order
    assert {(str(i), lang) for i, lang in scanned} == {(c["id"], "ces") for c in corpus.chunks.values()}
    assert report["scanned"] == 7 and report["excluded_languages"] == {}
    read = await source.read([chunks[0].chunk_id, UUID(int=1)])
    assert [c.id for c in read] == [chunks[0].chunk_id]

    assert await snapshot(seeded_store, collection_names) == before
