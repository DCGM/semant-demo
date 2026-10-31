"""Recomputing the document chunk-value summaries on a large synthetic store (#529): a controlled measurement.

Run on a throwaway store of the deployed Weaviate version::

    scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && \\
        ../.venv/bin/python -m pytest -m benchmark tests/integration/test_chunk_summary_benchmark.py -s'

Adds ``SEMANT_SUMMARY_BENCHMARK_DOCUMENTS`` documents (default 5,000) of 30 chunks each, with a
language and a value of every classification but no text or vectors to speak of, then times a
dry run and a write and prints one JSON report (chunks and documents per second). Times depend
on the machine and are not limits; the production chunks also carry text and two vectors,
which the command does not read.
"""
import json
import os
import random
import time
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject

from semant_demo.features.search.filters import TASK_CLASSES
from semant_demo.maintenance import chunk_summaries, chunk_summary_schema

pytestmark = pytest.mark.benchmark

DOCUMENTS = int(os.environ.get("SEMANT_SUMMARY_BENCHMARK_DOCUMENTS", "5000"))
CHUNKS_PER_DOCUMENT = 30
LANGUAGES = ["ces", "deu", "lat", "hun"]


def _id(kind: int, n: int) -> UUID:
    return UUID(int=(0x5E3A << 112) | (kind << 64) | n)


async def _insert(collection, objects: list[DataObject]) -> None:
    for start in range(0, len(objects), 2000):
        result = await collection.data.insert_many(objects[start:start + 2000])
        assert not result.errors


async def test_recomputation_throughput(seeded_store, collection_names, tmp_path):
    rng = random.Random(529)
    documents = seeded_store.collections.get(collection_names.document_collection_name)
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    await _insert(documents, [DataObject(uuid=_id(1, d), properties={"title": f"Dokument {d}"})
                              for d in range(DOCUMENTS)])
    await _insert(chunks, [
        DataObject(uuid=_id(2, d * CHUNKS_PER_DOCUMENT + c), references={"document": _id(1, d)},
                   properties={"text": "x", "language": rng.choice(LANGUAGES),
                               **{name: [rng.choice(values)] for name, values in TASK_CLASSES.items()}})
        for d in range(DOCUMENTS) for c in range(CHUNKS_PER_DOCUMENT)])
    await chunk_summary_schema.update(seeded_store, collection_names, apply=True)

    report = {"documents": DOCUMENTS, "chunks": DOCUMENTS * CHUNKS_PER_DOCUMENT}
    for mode in ("dry_run", "write"):
        started = time.perf_counter()
        result = await chunk_summaries.run(seeded_store, collection_names, report=tmp_path / f"{mode}.json",
                                           endpoint="test", write=mode == "write", progress=lambda line: None)
        seconds = time.perf_counter() - started
        assert result["counts"]["chunks"]["no_document"] == 0
        report[mode] = {"seconds": round(seconds, 1), **result["seconds"],
                        "chunks_per_second": round(result["counts"]["chunks"]["examined"] / result["seconds"]["chunks"]),
                        "documents_per_second": round(result["counts"]["documents"]["examined"]
                                                      / max(result["seconds"]["documents"], 1e-3))}
    assert result["counts"]["documents"]["written"] == DOCUMENTS + 3  # with the fixture documents
    print(json.dumps(report, indent=2))
