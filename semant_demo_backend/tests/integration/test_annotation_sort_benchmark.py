"""Latency of the annotation sorts of #666 on a tenant the size of production's largest.

Run on a throwaway store of the deployed Weaviate version::

    scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && \\
        ../.venv/bin/python -m pytest -m benchmark tests/integration/test_annotation_sort_benchmark.py -s'

A disposable tenant gets ``SPANS`` (28,000) synthetic annotations in 18 documents (the
largest production tenant, 2026-11-14: 28.1k annotations in 18 documents), with Czech words,
sort keys and values of a 12-value multi-valued attribute. For every sort it times, through
``service.query_annotations``, the first page and the deepest page Weaviate can sort to
(rows 9,950-10,000 for the text and context sorts; the last page for the document-ordered
ones), and the time of the sort key backfill of 1,000 spans. It prints one JSON report of the
median and maximum in milliseconds (``SEMANT_SORT_BENCHMARK_REPORT`` also writes it to that
file). Times depend on the machine and are not limits.
"""
import json
import os
import random
import statistics
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from weaviate.classes.data import DataObject

from semant_demo.adapters.weaviate.spans import SpanRepository, tenant_name
from semant_demo.features.annotations import attribute_codec as codec
from semant_demo.features.annotations import backfill, service
from semant_demo.features.annotations.collation import sort_keys
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.features.annotations.schemas import AnnotationSort
from semant_demo.features.annotations.service import AnnotationStore

pytestmark = pytest.mark.benchmark

SPANS = 28_000
DOCUMENTS = 18
VALUES = 12
REPEAT = 5
BACKFILLED = 1_000
WORDS = ("čas cesta chata hrad Hrad hrát dub řeka rak šašek žena zima Praha Brno obec kostel pole les voda "
         "hejtman rychtář sedlák kněz farář mlýn statek pán paní dům").split()
USER = SimpleNamespace(id=uuid4(), is_superuser=False)


class Access:
    def __init__(self, collection_id):
        self.collection_id = collection_id

    async def read_access_record(self, cid):
        return (USER.id, set()) if cid == self.collection_id else None


class Definitions:
    def __init__(self, attribute):
        self.attribute = attribute

    async def read(self, collection_id, attribute_id):
        return self.attribute if attribute_id == self.attribute.id else None


def _phrase(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n))


async def _timed(call) -> tuple[float, object]:
    start = time.perf_counter()
    result = await call
    return (time.perf_counter() - start) * 1000, result


async def test_sort_latency_on_a_production_sized_tenant(seeded_store, collection_names, documents):
    rng = random.Random(666)
    cid = uuid4()
    spans = SpanRepository(seeded_store, collection_names, attributes=True, sort_keys=True)
    store = AnnotationStore(collections=Access(cid), tags=None, spans=spans, documents=documents,
                            enrichment=Enrichment(derived=True, sort_keys=True))
    attribute = SimpleNamespace(id=uuid4(), values=[SimpleNamespace(id=uuid4(), retired=i == VALUES - 1)
                                                    for i in range(VALUES)])
    document_ids = [uuid4() for _ in range(DOCUMENTS)]
    tag, chunk = uuid4(), uuid4()
    await spans.ensure_tenant(cid)
    tenant = seeded_store.collections.get(collection_names.annotation_collection_name).with_tenant(tenant_name(cid))
    try:
        objects = []
        for i in range(SPANS):
            text, left, right = _phrase(rng, rng.randint(1, 3)), _phrase(rng, 30) + " ", " " + _phrase(rng, 30)
            held = rng.random()
            values = (rng.sample(attribute.values, 2) if held < 0.1 else [rng.choice(attribute.values)] if held < 0.8
                      else [])
            start = i * 10
            objects.append(DataObject(properties={
                "tagId": tag, "chunkId": chunk, "documentId": document_ids[i % DOCUMENTS], "start": 0, "end": len(text),
                "type": "pos" if rng.random() < 0.8 else "auto", "revision": 1, "enrichedRevision": 1,
                "enrichmentStatus": "ready", "derivationVersion": DERIVATION_VERSION, "text": text,
                "leftContext": left, "rightContext": right, "documentStartChar": start,
                "documentEndChar": start + len(text), "documentStartWord": i, "documentEndWord": i + 1,
                "attributeValues": sorted(codec.encode(attribute.id, v.id) for v in values), "attributeVersion": 1,
                # The first BACKFILLED spans lack keys: the backfill measurement computes theirs.
                **(sort_keys(text, left, right).properties(1) if i >= BACKFILLED else {})}))
        for first in range(0, SPANS, 1000):
            result = await tenant.data.insert_many(objects[first:first + 1000])
            assert not result.errors

        report: dict = {"spans": SPANS, "documents": DOCUMENTS, "attribute_values": VALUES, "pages": {}}
        definitions = Definitions(attribute)
        cases = [(sort, {}) for sort in (AnnotationSort.text, AnnotationSort.left, AnnotationSort.right)]
        cases += [(AnnotationSort.document, {}),
                  (AnnotationSort.attribute, {"sort_attribute": attribute.id, "attributes": definitions})]
        for sort, extra in cases:
            first_page = await service.query_annotations(store, USER, cid, sort=sort, limit=50, **extra)
            deep = 9_950 if sort in (AnnotationSort.text, AnnotationSort.left, AnnotationSort.right) \
                else first_page.total - 50
            for name, offset in (("first", 0), ("deep", deep)):
                for descending in (False, True):
                    times = []
                    for _ in range(REPEAT):
                        ms, page = await _timed(service.query_annotations(
                            store, USER, cid, sort=sort, descending=descending, limit=50, offset=offset, **extra))
                        assert len(page.rows) == 50
                        times.append(ms)
                    report["pages"][f"{sort.value}/{name}/{'desc' if descending else 'asc'}"] = {
                        "offset": offset, "median_ms": round(statistics.median(times), 1),
                        "max_ms": round(max(times), 1)}

        ms, result = await _timed(backfill.backfill(store, [cid], limit=BACKFILLED))
        assert (result.sort_keys_written, result.failed) == (BACKFILLED, [])
        report["backfill_sort_keys"] = {"spans": BACKFILLED, "total_ms": round(ms), "per_span_ms": round(ms / BACKFILLED, 2)}
        text = json.dumps(report, indent=2)
        print(text)
        if os.environ.get("SEMANT_SORT_BENCHMARK_REPORT"):
            with open(os.environ["SEMANT_SORT_BENCHMARK_REPORT"], "w", encoding="utf-8") as f:
                f.write(text)
    finally:
        await spans.remove_tenant(cid)
        assert isinstance(cid, UUID)
