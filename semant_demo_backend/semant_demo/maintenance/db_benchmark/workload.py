"""Query inputs sampled from the target store, and one read-only request per scenario kind.

Inputs are drawn at run time with a seeded random generator (random cursors in a large
collection, the id list of a small one), so no corpus ids or texts are checked in. Query vectors are the stored vectors of sampled chunks ("document as query"),
which keeps embedding calls out of the timings; BM25 text is the longest words of the same
chunk. Neither texts, vectors nor ids are written to the results: only short (unsalted)
hashes of ids, used to compare result lists between runs.

The ``search``, ``context``, ``document_view`` and ``aggregate`` kinds call the application's
adapters/services (layer ``adapter``); ``direct`` and ``self_recall`` query Weaviate without
references (layer ``direct``).
"""
import hashlib
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.aggregate import GroupByAggregate
from weaviate.classes.query import Filter, QueryReference

from semant_demo.adapters.weaviate.analytics import CorpusAnalyticsRepository
from semant_demo.adapters.weaviate.documents import DocumentRepository
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.analytics.service import corpus_overview
from semant_demo.features.search.schemas import ChunkQuery, FieldCondition, Op, SearchType, TagFilter
from semant_demo.maintenance.db_benchmark.profile import Profile, Scenario

WORD = re.compile(r"\w{4,}", re.UNICODE)
SMALL_COLLECTION = 10_000
"""Up to this many chunks, inputs are drawn from the full id list instead of random cursors."""
LAYER = {"search": "adapter", "context": "adapter", "document_view": "adapter", "aggregate": "adapter",
         "direct": "direct", "self_recall": "direct", "mixed": "mixed"}

Request = Callable[[int], Awaitable[list[UUID]]]


def short_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


@dataclass
class SampledChunk:
    id: UUID
    vector: list[float] | None
    terms: str
    document_id: UUID | None
    order: int | None
    document_chunks: int | None = None


@dataclass
class Inputs:
    chunks: list[SampledChunk]
    tags: list[UUID] = field(default_factory=list)
    user_collections: list[UUID] = field(default_factory=list)
    document_types: list[str] = field(default_factory=list)
    vector_name: str | None = None
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        with_vector = [c for c in self.chunks if c.vector is not None]
        return {
            "sampled_chunks": len(self.chunks),
            "with_vector": len(with_vector),
            "vector_dimensions": len(with_vector[0].vector) if with_vector else None,
            "vector_name": self.vector_name,
            "with_terms": sum(bool(c.terms) for c in self.chunks),
            "documents": len({c.document_id for c in self.chunks if c.document_id}),
            "tags": len(self.tags),
            "user_collections": len(self.user_collections),
            "document_types": len(self.document_types),
            "notes": self.notes,
        }


def collection_names(profile: Profile, base: CollectionNames) -> CollectionNames:
    c = profile.collections
    return base.model_copy(update={k: v for k, v in {
        "chunks_collection_name": c.chunks, "document_collection_name": c.documents,
        "tag_collection_name": c.tags, "user_collection_name": c.user_collections,
        "span_collection_name": c.spans}.items() if v})


def terms(text: str, count: int) -> str:
    words = sorted({w.lower() for w in WORD.findall(text or "")}, key=lambda w: (-len(w), w))
    return " ".join(words[:count])


def _pick_vector(vector, name: str | None) -> tuple[list[float] | None, str | None]:
    if isinstance(vector, dict):
        if not vector:
            return None, name
        key = name if name in vector else sorted(vector)[0]
        return vector[key], key
    return vector, name


async def _sample_ids(collection, rnd: random.Random, count: int) -> list[UUID]:
    if count <= 0:
        return []
    response = await collection.query.fetch_objects(limit=1000, return_properties=[])
    ids = [o.uuid for o in response.objects]
    rnd.shuffle(ids)
    return ids[:count]


async def sample_inputs(client: WeaviateAsyncClient, names: CollectionNames, profile: Profile,
                        target_vector: str | None) -> Inputs:
    rnd = random.Random(profile.seed)
    q = profile.queries
    chunks = client.collections.get(names.chunks_collection_name)
    sampled: dict[UUID, SampledChunk] = {}
    vector_name = target_vector
    fetch = dict(include_vector=True, return_properties=["text", "order"],
                 return_references=[QueryReference(link_on="document", return_properties=[])])
    total = (await chunks.aggregate.over_all(total_count=True)).total_count or 0
    if total == 0:
        objects = []
    elif total <= SMALL_COLLECTION:
        # Draw from all ids: a random cursor is only uniform for random (v4) ids.
        ids = [o.uuid for o in (await chunks.query.fetch_objects(limit=total, return_properties=[])).objects]
        ids.sort()
        objects = [await chunks.query.fetch_object_by_id(i, **fetch)
                   for i in rnd.sample(ids, min(q.sample_objects, len(ids)))]
    else:
        objects = []
        for _ in range(q.sample_objects * 3):
            if len(objects) >= q.sample_objects:
                break
            response = await chunks.query.fetch_objects(limit=1, after=uuid.UUID(int=rnd.getrandbits(128)), **fetch)
            if response.objects and response.objects[0].uuid not in {o.uuid for o in objects}:
                objects.append(response.objects[0])
    for obj in objects:
        if obj is None:
            continue
        vector, vector_name = _pick_vector(obj.vector, vector_name)
        docs = (obj.references or {}).get("document")
        sampled[obj.uuid] = SampledChunk(
            id=obj.uuid, vector=vector, terms=terms(obj.properties.get("text") or "", q.terms_per_query),
            document_id=docs.objects[0].uuid if docs and docs.objects else None,
            order=obj.properties.get("order"))
    inputs = Inputs(chunks=list(sampled.values()), vector_name=vector_name)
    if not inputs.chunks:
        inputs.notes.append("no chunks could be sampled")

    needs = {s.filter for s in profile.scenarios} | {s.kind for s in profile.scenarios}
    if "tag" in needs:
        inputs.tags = await _sample_ids(client.collections.get(names.tag_collection_name), rnd, q.sample_tags)
    if "user_collection" in needs:
        inputs.user_collections = await _sample_ids(
            client.collections.get(names.user_collection_name), rnd, q.sample_user_collections)
    if "document_type" in needs:
        inputs.document_types = list(q.document_types)
        if not inputs.document_types:
            grouped = await client.collections.get(names.document_collection_name).aggregate.over_all(
                group_by=GroupByAggregate(prop="documentType", limit=10), total_count=True)
            inputs.document_types = sorted(str(g.grouped_by.value) for g in grouped.groups if g.grouped_by.value)
    if "document_view" in needs:
        documents = DocumentRepository(client, names)
        limit = max((s.max_document_chunks for s in profile.scenarios if s.kind == "document_view"), default=0)
        for chunk in inputs.chunks:
            if chunk.document_id is not None:
                chunk.document_chunks = await documents.count_chunks(chunk.document_id)
        skipped = sum(1 for c in inputs.chunks if (c.document_chunks or 0) > limit)
        if skipped:
            inputs.notes.append(f"document_view skips {skipped} sampled documents with more than {limit} chunks")
    return inputs


class Workload:
    """Builds the request function of each scenario over the sampled inputs."""

    def __init__(self, client: WeaviateAsyncClient, names: CollectionNames, profile: Profile, inputs: Inputs):
        self.client = client
        self.names = names
        self.profile = profile
        self.inputs = inputs
        self.search = ChunkSearchRepository(client, names)
        self.documents = DocumentRepository(client, names)
        self.analytics = CorpusAnalyticsRepository(client, names)
        self.chunks = client.collections.get(names.chunks_collection_name)
        self.by_name = {s.name: s for s in profile.scenarios}

    def input_count(self, scenario: Scenario) -> int:
        return max(1, len(self._usable(scenario)))

    def _usable(self, scenario: Scenario) -> list[SampledChunk]:
        chunks = self.inputs.chunks
        if scenario.kind in ("search", "direct") and scenario.mode != "text" or scenario.kind == "self_recall":
            chunks = [c for c in chunks if c.vector is not None]
        if scenario.kind in ("search", "direct") and scenario.mode != "vector":
            chunks = [c for c in chunks if c.terms]
        if scenario.kind == "context":
            chunks = [c for c in chunks if c.document_id is not None and c.order is not None]
        if scenario.kind == "document_view":
            chunks = [c for c in chunks if c.document_id is not None
                      and (c.document_chunks or 0) <= scenario.max_document_chunks]
        return chunks

    def skip_reason(self, scenario: Scenario) -> str | None:
        if scenario.kind == "mixed":
            return None
        if scenario.kind != "aggregate" and not self._usable(scenario):
            return "no usable sampled inputs"
        needed = {"tag": self.inputs.tags, "user_collection": self.inputs.user_collections,
                  "document_type": self.inputs.document_types}
        if scenario.filter in needed and not needed[scenario.filter]:
            return f"no {scenario.filter} values sampled"
        return None

    def fingerprint(self, scenario: Scenario, index: int) -> str:
        """Identifies the query of ``index`` (its input and filter value) without revealing it."""
        if scenario.kind in ("aggregate", "mixed"):
            return short_hash(index)
        chunk = self._usable(scenario)[index % self.input_count(scenario)]
        return short_hash((chunk.id, self._filter_value(scenario, index)))

    def _filter_value(self, scenario: Scenario, index: int):
        values = {
            "year_range": self.profile.queries.year_ranges, "language": self.profile.queries.languages,
            "document_type": self.inputs.document_types, "tag": self.inputs.tags,
            "user_collection": self.inputs.user_collections,
        }.get(scenario.filter or "")
        return values[index % len(values)] if values else None

    def request(self, scenario: Scenario) -> Request:
        if scenario.kind == "mixed":
            parts = [self.request(self.by_name[name]) for name in scenario.of]
            return lambda index: parts[index % len(parts)](index // len(parts))
        return {"search": self._search, "direct": self._direct, "context": self._context,
                "document_view": self._document_view, "aggregate": self._aggregate,
                "self_recall": self._self_recall}[scenario.kind](scenario)

    def _search(self, scenario: Scenario) -> Request:
        usable = self._usable(scenario)

        async def run(index: int) -> list[UUID]:
            chunk = usable[index % len(usable)]
            value = self._filter_value(scenario, index)
            conditions, tags, collection_id = (), None, None
            if scenario.filter == "year_range":
                conditions = (FieldCondition("yearIssued", Op.greater_or_equal, value[0]),
                              FieldCondition("yearIssued", Op.less_or_equal, value[1]))
            elif scenario.filter == "language":
                conditions = (FieldCondition("language", Op.contains_any, [value]),)
            elif scenario.filter == "document_type":
                conditions = (FieldCondition("documentType", Op.equal, value),)
            elif scenario.filter == "tag":
                tags = TagFilter((value,), automatic=True, positive=True)
            elif scenario.filter == "user_collection":
                collection_id = value
            hits = await self.search.search(ChunkQuery(
                text=chunk.terms, mode=SearchType(scenario.mode), limit=scenario.limit, alpha=scenario.alpha,
                vector=chunk.vector if scenario.mode != "text" else None,
                collection_id=collection_id, tags=tags, conditions=conditions))
            return [h.id for h in hits]
        return run

    def _direct(self, scenario: Scenario) -> Request:
        usable = self._usable(scenario)
        target = self.inputs.vector_name

        async def run(index: int) -> list[UUID]:
            chunk = usable[index % len(usable)]
            common = dict(limit=scenario.limit, return_properties=["order"])
            if scenario.mode == "text":
                result = await self.chunks.query.bm25(query=chunk.terms, **common)
            elif scenario.mode == "vector":
                result = await self.chunks.query.near_vector(near_vector=chunk.vector, target_vector=target, **common)
            else:
                result = await self.chunks.query.hybrid(query=chunk.terms, vector=chunk.vector, alpha=scenario.alpha,
                                                        target_vector=target, **common)
            return [o.uuid for o in result.objects]
        return run

    def _context(self, scenario: Scenario) -> Request:
        usable = self._usable(scenario)

        async def run(index: int) -> list[UUID]:
            chunk = usable[index % len(usable)]
            before = await self.documents.read_adjacent_chunks(chunk.document_id, chunk.order, "before",
                                                               scenario.context_chunks)
            after = await self.documents.read_adjacent_chunks(chunk.document_id, chunk.order, "after",
                                                              scenario.context_chunks)
            return [c.id for c in before + after]
        return run

    def _document_view(self, scenario: Scenario) -> Request:
        usable = self._usable(scenario)
        nil_collection = UUID(int=0)

        async def run(index: int) -> list[UUID]:
            detail = await self.documents.read_chunks(usable[index % len(usable)].document_id, nil_collection)
            return [c.id for c in detail.chunks] if detail else []
        return run

    def _aggregate(self, scenario: Scenario) -> Request:
        async def run(index: int) -> list[UUID]:
            await corpus_overview(self.analytics)
            return []
        return run

    def _self_recall(self, scenario: Scenario) -> Request:
        """Returns ``[id]`` when the chunk is among the top ``limit`` hits for its own vector, else ``[]``."""
        usable = self._usable(scenario)
        target = self.inputs.vector_name

        async def run(index: int) -> list[UUID]:
            chunk = usable[index % len(usable)]
            result = await self.chunks.query.near_vector(near_vector=chunk.vector, target_vector=target,
                                                         limit=scenario.limit, return_properties=[])
            return [chunk.id] if chunk.id in {o.uuid for o in result.objects} else []
        return run


async def id_filtered_self_hit(client: WeaviateAsyncClient, names: CollectionNames, chunk: SampledChunk,
                               target_vector: str | None) -> bool:
    """Whether a vector query restricted to the chunk's own id finds it (the vector is in the index)."""
    result = await client.collections.get(names.chunks_collection_name).query.near_vector(
        near_vector=chunk.vector, target_vector=target_vector, limit=1, return_properties=[],
        filters=Filter.by_id().equal(chunk.id))
    return any(o.uuid == chunk.id for o in result.objects)
