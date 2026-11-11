"""Distinct-document text retrieval on a large synthetic store (#607): a controlled measurement.

Run on a throwaway store of the deployed Weaviate version::

    scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && \\
        ../.venv/bin/python -m pytest -m benchmark tests/integration/test_document_search_benchmark.py -s'

Recreates the application collections empty and adds ``SEMANT_DOCSEARCH_BENCHMARK_DOCUMENTS``
documents (default 2,000) of ``SEMANT_DOCSEARCH_BENCHMARK_CHUNKS`` chunks each (default 50), with
Zipf-distributed words, a chunk language (Hungarian rare: about one document in twenty has a
Hungarian chunk) and random ``SEMANT_DOCSEARCH_BENCHMARK_DIMENSIONS``-dimensional vectors
(default 384), and computes the documents' chunk-value summaries (#529). Then, for BM25, vector
and hybrid queries, without filters and with a document-level chunk filter (a Hungarian chunk,
through the ``document`` reference), it times

* ``metadata``: BM25 over the documents' title, filtered on the documents themselves;
* ``ranked_<window>``: the ranked chunk ids with their document reference (no properties),
  deduplicated in rank order: the strategy of ``search_documents`` (#607);
* ``grouped_<groups>``: Weaviate's ``group_by`` on the ``document`` reference, one object per
  group, kept as the evidence for not using it: on 1.40.1 BM25 and hybrid return no groups at
  all, and vector search groups only the first ``limit`` chunks;

and prints one JSON report. The collections are dropped at the end. Times depend on the
machine and the synthetic data, and are not limits.
"""
import json
import os
import random
import time
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter, GroupBy, QueryReference

from semant_demo.maintenance import chunk_summaries, chunk_summary_schema
from tests.weaviate_store import create_app_schema, drop_app_collections

pytestmark = pytest.mark.benchmark

DOCUMENTS = int(os.environ.get("SEMANT_DOCSEARCH_BENCHMARK_DOCUMENTS", "2000"))
CHUNKS_PER_DOCUMENT = int(os.environ.get("SEMANT_DOCSEARCH_BENCHMARK_CHUNKS", "50"))
DIMENSIONS = int(os.environ.get("SEMANT_DOCSEARCH_BENCHMARK_DIMENSIONS", "384"))
WORDS_PER_CHUNK = 80
VOCABULARY = [f"w{n}" for n in range(20_000)]
LANGUAGES, LANGUAGE_WEIGHTS = ["ces", "deu", "lat", "hun"], [0.7, 0.25, 0.049, 0.001]
QUERIES = {"frequent": "w5 w40", "common": "w300", "rare pair": "w1200 w7000", "very rare": "w15000"}
WINDOWS = (1000, 9999)
GROUPS = 100


def _id(kind: int, n: int) -> UUID:
    return UUID(int=(0x6070 << 112) | (kind << 64) | n)


async def _insert(collection, objects) -> None:
    for start in range(0, len(objects), 1000):
        result = await collection.data.insert_many(objects[start:start + 1000])
        assert not result.errors, list(result.errors.values())[:1]


def _vector(rng: random.Random) -> list[float]:
    return [rng.gauss(0, 1) for _ in range(DIMENSIONS)]


async def _timed(call):
    started = time.perf_counter()
    result = await call
    return result, round(time.perf_counter() - started, 3)


async def _populate(client, names, rng: random.Random, tmp_path) -> None:
    weights = [1 / (rank + 1) for rank in range(len(VOCABULARY))]
    documents = client.collections.get(names.document_collection_name)
    chunks = client.collections.get(names.chunks_collection_name)
    await _insert(documents, [
        DataObject(uuid=_id(1, d), properties={"title": " ".join(rng.choices(VOCABULARY, weights, k=4))})
        for d in range(DOCUMENTS)])
    batch = []
    for d in range(DOCUMENTS):
        for c in range(CHUNKS_PER_DOCUMENT):
            batch.append(DataObject(
                uuid=_id(2, d * CHUNKS_PER_DOCUMENT + c), references={"document": _id(1, d)},
                vector={"default": _vector(rng)},
                properties={"text": " ".join(rng.choices(VOCABULARY, weights, k=WORDS_PER_CHUNK)), "order": c,
                            "language": rng.choices(LANGUAGES, LANGUAGE_WEIGHTS)[0]}))
        if len(batch) >= 5000:
            await _insert(chunks, batch)
            batch = []
    await _insert(chunks, batch)
    await chunk_summary_schema.update(client, names, apply=True)
    await chunk_summaries.run(client, names, report=tmp_path / "summaries.json", endpoint="test", write=True,
                              progress=lambda line: None)


async def test_distinct_document_retrieval(weaviate_client, collection_names, store_token, tmp_path):
    client, names = weaviate_client, collection_names
    rng = random.Random(607)
    await drop_app_collections(client, names, store_token)
    await create_app_schema(client, names)
    try:
        started = time.perf_counter()
        await _populate(client, names, rng, tmp_path)
        report = {"weaviate": (await client.get_meta())["version"], "documents": DOCUMENTS,
                  "chunks": DOCUMENTS * CHUNKS_PER_DOCUMENT, "dimensions": DIMENSIONS,
                  "populate_seconds": round(time.perf_counter() - started), "results": []}
        documents = client.collections.get(names.document_collection_name)
        chunks = client.collections.get(names.chunks_collection_name)
        hungarian = (await documents.aggregate.over_all(
            filters=Filter.by_property("chunk_language").contains_any(["hun"]), total_count=True)).total_count
        report["documents_with_a_hungarian_chunk"] = hungarian
        filters = {
            "none": (None, None),
            "chunk_language=hun": (Filter.by_property("chunk_language").contains_any(["hun"]),
                                   Filter.by_ref("document").by_property("chunk_language").contains_any(["hun"])),
        }
        reference = QueryReference(link_on="document", return_properties=[])
        for label, text in QUERIES.items():
            vector = _vector(rng)
            modes = {
                "bm25": lambda **kw: chunks.query.bm25(query=text, **kw),
                "vector": lambda **kw: chunks.query.near_vector(near_vector=vector, target_vector="default", **kw),
                "hybrid": lambda **kw: chunks.query.hybrid(query=text, vector=vector, target_vector="default",
                                                           alpha=0.5, **kw),
            }
            for name, (on_documents, on_chunks) in filters.items():
                result, seconds = await _timed(documents.query.bm25(
                    query=text, query_properties=["title"], limit=1000, filters=on_documents, return_properties=[]))
                report["results"].append({"query": label, "filter": name,
                                          "metadata": {"seconds": seconds, "documents": len(result.objects)}})
                for mode, run in modes.items():
                    row = {"query": label, "mode": mode, "filter": name}
                    for window in WINDOWS:
                        result, seconds = await _timed(run(limit=window, filters=on_chunks, return_properties=[],
                                                           return_references=[reference]))
                        distinct = dict.fromkeys(o.references["document"].objects[0].uuid for o in result.objects)
                        row[f"ranked_{window}"] = {"seconds": seconds, "chunks": len(result.objects),
                                                   "documents": len(distinct)}
                    result, seconds = await _timed(run(
                        limit=GROUPS, filters=on_chunks, return_properties=[],
                        group_by=GroupBy(prop="document", objects_per_group=1, number_of_groups=GROUPS)))
                    row[f"grouped_{GROUPS}"] = {"seconds": seconds, "groups": len(result.groups)}
                    report["results"].append(row)
        print(json.dumps(report, indent=1))
    finally:
        await drop_app_collections(client, names, store_token)
