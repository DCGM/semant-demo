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


async def test_only_public_documents_are_read_unless_restricted_ones_are_included(seeded_store, collection_names,
                                                                                  corpus):
    """#883 review: the letters are restricted (``documentPublic`` false) and one gazette chunk has
    no visibility at all (unknown, which fails closed); the scan, ``read``, ``neighbours`` and the
    imported source chunks all leave them out, unless restricted documents are explicitly included."""
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    by_document: dict[str, list[dict]] = {}
    for chunk in corpus.chunks.values():
        by_document.setdefault(chunk["document"], []).append(chunk)
    letters = next(k for k, d in corpus.documents.items() if d["properties"]["title"] == "Dopisy z Prahy")
    gazette = next(k for k, d in corpus.documents.items() if d["properties"]["title"] == "Pražský věstník")
    restricted = {UUID(c["id"]) for c in by_document[letters]}
    for chunk_id in restricted:
        await chunks.data.update(uuid=chunk_id, properties={"documentPublic": False})
    unknown_chunk = sorted(by_document[gazette], key=lambda c: c["order"])[0]
    unknown = UUID(unknown_chunk["id"])
    stored = await chunks.query.fetch_object_by_id(unknown, include_vector=True)
    await chunks.data.delete_by_id(unknown)
    await chunks.data.insert(uuid=unknown, properties={k: v for k, v in stored.properties.items()
                                                       if k != "documentPublic" and v is not None},
                             references={"document": UUID(corpus.documents[gazette]["id"])},
                             vector=stored.vector)
    hidden = restricted | {unknown}
    every = {UUID(c["id"]) for c in corpus.chunks.values()}

    source = WeaviateSource(seeded_store, collection_names, {"description": "fixture"})
    scanned = {i async for i, _ in source.scan(page=2)}
    assert scanned == every - hidden
    assert source.describe()["documents"] == "public only"
    assert source.describe()["withheld_by_visibility"] == {"restricted": len(restricted), "unknown": 1}
    assert {c.id for c in await source.read(sorted(every))} == every - hidden
    letters_id = UUID(corpus.documents[letters]["id"])
    assert await source.neighbours(letters_id, [c["order"] for c in by_document[letters]]) == []
    gazette_id = UUID(corpus.documents[gazette]["id"])
    gazette_read = await source.neighbours(gazette_id, [c["order"] for c in by_document[gazette]])
    assert {c.id for c in gazette_read} == {UUID(c["id"]) for c in by_document[gazette]} - {unknown}

    corpus_chunks, report = await sample_corpus(source, config(context_fraction=1.0, context_neighbours=2),
                                                sorted(hidden))
    assert not {c.chunk_id for c in corpus_chunks} & hidden
    assert sorted(report["imported_sources_missing"]) == sorted(str(i) for i in hidden)

    everything = WeaviateSource(seeded_store, collection_names, {"description": "fixture"}, include_restricted=True)
    assert {i async for i, _ in everything.scan(page=2)} == every
    assert {c.id for c in await everything.read(sorted(every))} == every
    assert everything.describe()["documents"] == "all, including restricted"
