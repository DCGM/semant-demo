"""Annotation ADD/MOVE reads and derivation by document length (#463): a controlled measurement.

Run on a throwaway store of the deployed Weaviate version::

    scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && \\
        ../.venv/bin/python -m pytest -m benchmark tests/integration/test_chunk_position_benchmark.py -s'

Documents of 10, 500 and 7,000 chunks are added to the seeded store. For a short span in
the middle of each document and a span over three chunks, it times what a span create
reads and computes before #463 (the anchor, the following chunks sorted by Weaviate, the
whole document's chunk texts, the whole-text derivation) and after it (the anchor and
narrow order ranges, ``source.py``; the local derivation), the database and the derivation
separately, without the contextual embedding. It prints one JSON report of p50/p95 in
milliseconds, rows and text bytes read (``SEMANT_POSITION_BENCHMARK_REPORT`` also writes it
to that file). Results of both are asserted equal and the rows
read after #463 independent of the document length; times depend on the machine and are
not limits.
"""
import json
import os
import statistics
import time
from uuid import UUID

import pytest
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter

from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.paging import fetch_all
from semant_demo.features.annotations.derivation import derive
from semant_demo.features.annotations.offsets import check_span_range
from semant_demo.features.annotations.schemas import AnnotationChunk
from semant_demo.features.annotations.source import ChunkSource
from semant_demo.features.documents.positions import chunk_positions
from tests.seed import position_properties
from tests.test_annotation_derivation import _whole_document

pytestmark = pytest.mark.benchmark

SIZES = [10, 500, 7000]
REPEAT = 30
SENTENCE = "Roku 1848 přijel hejtman Jan Novák do Brna a ubytoval se v hostinci U Modrého lva. "


def _text(i: int) -> str:
    return f"Odstavec {i}. " + SENTENCE * 7  # about 600 characters, a typical chunk


class Counting:
    """A ``DocumentRepository`` that times its reads and counts rows and text bytes."""

    def __init__(self, inner: DocumentRepository):
        self.inner, self.seconds, self.rows, self.bytes = inner, 0.0, 0, 0

    async def _timed(self, call):
        start = time.perf_counter()
        result = await call
        self.seconds += time.perf_counter() - start
        chunks = result if isinstance(result, list) else [result] if result is not None else []
        self.rows += len(chunks)
        self.bytes += sum(len(c.text.encode()) for c in chunks)
        return result

    async def read_chunk_text(self, chunk_id):
        return await self._timed(self.inner.read_chunk_text(chunk_id))

    async def read_chunk_texts_in_range(self, document_id, first, last):
        return await self._timed(self.inner.read_chunk_texts_in_range(document_id, first, last))

    async def read_following_chunk_texts(self, document_id, after_order, limit):
        return await self._timed(self.inner.read_following_chunk_texts(document_id, after_order, limit))

    async def read_chunk_texts(self, document_id):
        """Every chunk of the document, as span writes read it before #463."""
        async def read():
            objects = await fetch_all(self.inner._chunks(), filters=Filter.by_ref("document").by_id().equal(document_id),
                                      page_size=500, return_properties=["order", "text"])
            return sorted((AnnotationChunk(id=o.uuid, document_id=document_id, order=o.properties["order"],
                                           text=o.properties.get("text") or "") for o in objects),
                          key=lambda c: c.order)
        return await self._timed(read())


async def _before(documents: Counting, chunk_id: UUID, start: int, end: int):
    """The reads and derivation of a span create before #463."""
    anchor = await documents.read_chunk_text(chunk_id)
    chunks = [anchor]
    while True:  # the range check: following chunks sorted by order on the server
        try:
            check_span_range(chunks, start, end)
            break
        except Exception:
            chunks += await documents.read_following_chunk_texts(anchor.document_id, chunks[-1].order, 20)
    whole = await documents.read_chunk_texts(anchor.document_id)
    began = time.perf_counter()
    derived = _whole_document(whole, next(i for i, c in enumerate(whole) if c.id == chunk_id), start, end)
    return derived, time.perf_counter() - began


async def _after(documents: Counting, chunk_id: UUID, start: int, end: int):
    """The reads and derivation of a span create after #463 (``service._check_range`` and
    ``derive_refresh`` sharing one ``ChunkSource``)."""
    source = ChunkSource(documents)
    anchor = await source.chunk(chunk_id)
    check_span_range(await source.covering(anchor, end), start, end)
    span = await source.span_source(anchor, start, end)
    began = time.perf_counter()
    return derive(span, start, end), time.perf_counter() - began


def _stats(values: list[float]) -> dict:
    ms = sorted(v * 1000 for v in values)
    return {"p50": round(statistics.median(ms), 2), "p95": round(ms[int(0.95 * (len(ms) - 1))], 2)}


async def test_span_reads_by_document_length(seeded_store, collection_names):
    chunks = seeded_store.collections.get(collection_names.chunks_collection_name)
    repository = DocumentRepository(seeded_store, collection_names)
    repository.positions = True
    report = {"weaviate": (await seeded_store.get_meta())["version"], "repeat": REPEAT, "results": []}
    rows_after: dict[str, set[int]] = {}
    for n, size in enumerate(SIZES):
        document = UUID(int=0xBE7C0000 + n)
        await seeded_store.collections.get(collection_names.document_collection_name).data.insert(
            uuid=document, properties={"title": f"Benchmark {size}"})
        texts = [_text(i) for i in range(size)]
        ids = [UUID(int=document.int * 100_000 + i) for i in range(size)]
        for first in range(0, size, 1000):
            result = await chunks.data.insert_many([
                DataObject(uuid=ids[i], properties={"text": texts[i], "order": i, **position_properties(p)},
                           references={"document": document})
                for i, p in zip(range(first, min(size, first + 1000)),
                                list(chunk_positions(texts))[first:first + 1000])])
            assert not result.errors
        middle = size // 2
        for label, start, end in (("short", 34, 43), ("three chunks", 34, len(texts[middle]) * 2 + 9)):
            if middle + 2 >= size and label != "short":
                continue
            timings = {"before": {"db": [], "derive": [], "rows": 0, "bytes": 0},
                       "after": {"db": [], "derive": [], "rows": 0, "bytes": 0}}
            for _ in range(REPEAT):
                for name, run in (("before", _before), ("after", _after)):
                    counting = Counting(repository)
                    derived, seconds = await run(counting, ids[middle], start, end)
                    timings[name]["db"].append(counting.seconds)
                    timings[name]["derive"].append(seconds)
                    timings[name]["rows"], timings[name]["bytes"] = counting.rows, counting.bytes
                    timings[name]["derived"] = derived
            assert timings["after"]["derived"] == timings["before"]["derived"]
            rows_after.setdefault(label, set()).add(timings["after"]["rows"])
            report["results"].append({"chunks": size, "span": label, **{
                name: {"db_ms": _stats(t["db"]), "derive_ms": _stats(t["derive"]), "rows": t["rows"],
                       "text_bytes": t["bytes"]} for name, t in timings.items()}})
    print(json.dumps(report, indent=2))
    if os.environ.get("SEMANT_POSITION_BENCHMARK_REPORT"):
        with open(os.environ["SEMANT_POSITION_BENCHMARK_REPORT"], "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    assert all(len(rows) == 1 for rows in rows_after.values()), rows_after
