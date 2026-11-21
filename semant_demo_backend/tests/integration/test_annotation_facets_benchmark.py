"""Facet counts of #667 on a disposable tenant: exact attribute counts, and latency at production size.

``test_attribute_facets_equal_the_totals_of_choosing_each_value`` (integration, in CI) seeds a small
tenant and checks, against real Weaviate, that an attribute facet's counts, ``missing`` and
``inapplicable`` equal what the filtered list returns, for an annotation holding two values.

``test_facet_latency_on_a_production_sized_tenant`` (benchmark) times all facets of one query on a
tenant the size of production's largest (28,000 annotations in 18 documents, 2026-11-14). Run it on a
throwaway store of the deployed Weaviate version::

    scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && \\
        ../.venv/bin/python -m pytest -m benchmark tests/integration/test_annotation_facets_benchmark.py -s'

It prints one JSON report of the median and maximum in milliseconds per query (``SEMANT_FACET_BENCHMARK_REPORT``
also writes it to that file). Times depend on the machine and are not limits; note the machine
when quoting them. Documents are synthetic (the metadata read of 18 documents is not what is measured).
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
from semant_demo.features.annotations import facets, service
from semant_demo.features.annotations.derivation import DERIVATION_VERSION
from semant_demo.features.annotations.enrichment import Enrichment
from semant_demo.features.annotations.schemas import AnnotationFacetsRequest, AnnotationFilters
from semant_demo.features.annotations.service import AnnotationStore
from semant_demo.features.documents.criteria import DocumentFilters, NumberRange
from semant_demo.features.documents.schemas import Document

SPANS = 28_000
DOCUMENTS = 18
VALUES = 12
REPEAT = 5
WORDS = ("čas cesta chata hrad hrát dub řeka rak žena zima Praha Brno obec kostel pole les voda "
         "hejtman rychtář sedlák kněz farář mlýn statek pán paní dům").split()
USER = SimpleNamespace(id=uuid4(), is_superuser=False)
ALL = ["tag", "type", "document", "year", "library", "language"]


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


class Documents:
    """Synthetic metadata: years 1800-1940, two libraries and languages, one document without a year."""

    def __init__(self, ids):
        self.documents = {d: Document(id=d, title=f"Dokument {i}", yearIssued=None if i == 0 else 1800 + 8 * i,
                                      library=("mzk", "nkp")[i % 2], language=("ces", "deu")[i % 3 == 0])
                          for i, d in enumerate(ids)}

    async def read_many(self, ids):
        return {i: self.documents[i] for i in ids if i in self.documents}

    async def read_eligible(self, ids, collection_id=None, conditions=(), include_restricted=False):
        # Every synthetic document is public, so ``include_restricted`` changes nothing here.
        def holds(document):
            return all(isinstance(c, NumberRange) and document.yearIssued is not None
                       and (c.minimum is None or document.yearIssued >= c.minimum)
                       and (c.maximum is None or document.yearIssued <= c.maximum) for c in conditions)
        return {i: self.documents[i] for i in ids if i in self.documents and holds(self.documents[i])}


def _phrase(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n))


async def _seed(seeded_store, collection_names, count: int, rng: random.Random):
    """A disposable tenant of ``count`` annotations; returns the store, its pieces and a cleanup."""
    cid = uuid4()
    spans = SpanRepository(seeded_store, collection_names, attributes=True, sort_keys=True)
    documents = Documents([uuid4() for _ in range(DOCUMENTS)])
    store = AnnotationStore(collections=Access(cid), tags=None, spans=spans, documents=documents,
                            enrichment=Enrichment(derived=True, sort_keys=True))
    tags = [uuid4() for _ in range(4)]
    # The attribute applies to the first two tags only: values on the others no longer apply (#500).
    attribute = SimpleNamespace(id=uuid4(), all_tags=False, tag_ids=tags[:2],
                                values=[SimpleNamespace(id=uuid4(), retired=i == VALUES - 1) for i in range(VALUES)])
    chunk, ids = uuid4(), list(documents.documents)
    await spans.ensure_tenant(cid)
    tenant = seeded_store.collections.get(collection_names.annotation_collection_name).with_tenant(tenant_name(cid))
    objects = []
    for i in range(count):
        text = _phrase(rng, rng.randint(1, 3))
        held = rng.random()
        values = (rng.sample(attribute.values, 2) if held < 0.1 else [rng.choice(attribute.values)] if held < 0.8
                  else [])
        kind = rng.random()
        objects.append(DataObject(properties={
            "tagId": rng.choice(tags), "chunkId": chunk, "documentId": ids[i % DOCUMENTS], "start": 0, "end": len(text),
            "type": "pos" if kind < 0.7 else "auto" if kind < 0.95 else "neg", "revision": 1, "enrichedRevision": 1,
            "enrichmentStatus": "ready", "derivationVersion": DERIVATION_VERSION, "text": text,
            "leftContext": _phrase(rng, 5) + " ", "rightContext": " " + _phrase(rng, 5),
            "documentStartChar": i * 10, "documentEndChar": i * 10 + len(text), "documentStartWord": i,
            "documentEndWord": i + 1, "attributeValues": sorted(codec.encode(attribute.id, v.id) for v in values),
            "attributeVersion": 1}))
    for first in range(0, count, 1000):
        result = await tenant.data.insert_many(objects[first:first + 1000])
        assert not result.errors
    return cid, store, spans, attribute, tags


@pytest.mark.integration
async def test_attribute_facets_equal_the_totals_of_choosing_each_value(seeded_store, collection_names):
    cid, store, spans, attribute, tags = await _seed(seeded_store, collection_names, 1_500, random.Random(667))
    try:
        facet_name = f"attribute:{attribute.id}"
        for filters in ({}, {"tag_ids": tags[:1]}, {"q": "hrad"}):
            request = AnnotationFacetsRequest(facets=[facet_name], **filters)
            facet = (await facets.annotation_facets(store, USER, cid, request, Definitions(attribute))).facets[0]
            assert facet.values, filters
            for value in facet.values:
                element = codec.encode(attribute.id, UUID(value.value))
                held = await service.query_annotations(
                    store, USER, cid, AnnotationFilters(attribute_values=[element], **filters), limit=1)
                assert held.total == value.count, (filters, value.value)
                # Of them, those on tags the attribute applies to; the others are marked inapplicable (#500).
                applicable = [t for t in attribute.tag_ids if not filters.get("tag_ids") or t in filters["tag_ids"]]
                applying = (await service.query_annotations(
                    store, USER, cid, AnnotationFilters(attribute_values=[element], **{**filters, "tag_ids": applicable}),
                    limit=1)).total if applicable else 0
                assert value.inapplicable == held.total - applying, (filters, value.value)
            unassigned = await service.query_annotations(
                store, USER, cid, AnnotationFilters(attribute_unassigned=[attribute.id], **filters), limit=1)
            assert unassigned.total == facet.missing, filters
            # An annotation holding two values counts under both: more value counts than annotations.
            assert sum(v.count for v in facet.values) >= facet.total - facet.missing
    finally:
        await spans.remove_tenant(cid)


@pytest.mark.benchmark
async def test_facet_latency_on_a_production_sized_tenant(seeded_store, collection_names):
    cid, store, spans, attribute, tags = await _seed(seeded_store, collection_names, SPANS, random.Random(667))
    try:
        facet_names = [*ALL, f"attribute:{attribute.id}"]
        queries = {
            "no filters": {},
            "one tag": {"tag_ids": tags[:1]},
            "words": {"q": "hrad"},
            "year range": {"document_filters": DocumentFilters(year_min=1850, year_max=1900)},
            "one document": {"document_ids": [next(iter(store.documents.documents))]},
            "attribute value": {"attribute_values": [codec.encode(attribute.id, attribute.values[0].id)]},
            "tag, words and years": {"tag_ids": tags[:2], "q": "hrad",
                                     "document_filters": DocumentFilters(year_min=1850)},
        }
        report: dict = {"spans": SPANS, "documents": DOCUMENTS, "attribute_values": VALUES, "facets": facet_names,
                        "queries": {}}
        for name, filters in queries.items():
            times = []
            for _ in range(REPEAT):
                start = time.perf_counter()
                result = await facets.annotation_facets(
                    store, USER, cid, AnnotationFacetsRequest(facets=facet_names, **filters), Definitions(attribute))
                times.append((time.perf_counter() - start) * 1000)
                assert len(result.facets) == len(facet_names)
            report["queries"][name] = {"median_ms": round(statistics.median(times), 1), "max_ms": round(max(times), 1),
                                       "total": result.facets[0].total}
        text = json.dumps(report, indent=2, ensure_ascii=False)
        print(text)
        if os.environ.get("SEMANT_FACET_BENCHMARK_REPORT"):
            with open(os.environ["SEMANT_FACET_BENCHMARK_REPORT"], "w", encoding="utf-8") as f:
                f.write(text)
    finally:
        await spans.remove_tenant(cid)
