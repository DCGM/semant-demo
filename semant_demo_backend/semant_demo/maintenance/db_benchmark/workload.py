"""Query inputs sampled from the target store, and one read-only request per scenario kind.

Inputs are drawn at run time with a seeded random generator (random cursors in a large
collection, the id list of a small one), so no corpus ids or texts are checked in. Query vectors are the stored vectors of sampled chunks ("document as query"),
which keeps embedding calls out of the timings; BM25 text is the longest words of the same
chunk. Neither texts, vectors nor ids are written to the results: only short keyed hashes
of ids (``IdHasher``), used to compare result lists between runs made with the same key.

Tag and user-collection filter values are only those that match at least one chunk, and the
query of such a filtered search is taken from a chunk inside that tag or collection (a user
searching within it), so the search can return results. Each value is paired with one chunk.

The ``search``, ``context``, ``document_view`` and ``aggregate`` kinds call the application's
adapters/services (layer ``adapter``); ``direct`` and ``self_recall`` query Weaviate without
references (layer ``direct``).
"""
import hashlib
import hmac
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
    """Unkeyed 12-character hash; only an intermediate step, never written as is (see ``IdHasher``)."""
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


class IdHasher:
    """Keyed hashes of the result ids and query fingerprints written to results.

    An unkeyed hash of an object id can be reversed by anyone who can list the ids, so the
    ``short_hash`` of a value is hashed again with a secret key (HMAC-SHA256). Runs made with
    the same key can be compared; ``key_id`` identifies the key without revealing it.
    ``rekey`` also converts the unkeyed hashes of results written by tool version 1.
    """

    def __init__(self, key: bytes):
        if len(key) < 16:
            raise ValueError("the id hash key must have at least 16 bytes")
        self.key = key
        self.key_id = hashlib.sha256(b"db_benchmark key id:" + key).hexdigest()[:8]

    def rekey(self, unkeyed: str) -> str:
        return hmac.new(self.key, unkeyed.encode(), hashlib.sha256).hexdigest()[:12]

    def __call__(self, value: object) -> str:
        return self.rekey(short_hash(value))

    def describe(self) -> dict:
        return {"method": "hmac-sha256(key, sha256(id)[:12])[:12]", "key_id": self.key_id}


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
    filter_values_checked: dict[str, int] = field(default_factory=dict)
    """Tags / user collections checked for matching chunks while sampling."""
    scoped: dict[str, list[tuple[UUID, SampledChunk]]] = field(default_factory=dict)
    """``tag`` / ``user_collection``: each sampled value with a chunk inside it (the query source)."""

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
            "filter_values_checked": self.filter_values_checked,
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
    """The object's vector called ``name`` (None when it has none); without a name, the first by name.

    Another vector is never substituted for the requested one.
    """
    if not isinstance(vector, dict):
        vector = {"default": vector} if vector is not None else {}
    if name is None:
        if not vector:
            return None, None
        name = sorted(vector)[0]
    return vector.get(name), name


FILTER_CHECKS = 1000
"""At most this many tags / user collections are checked for matching chunks."""


async def _sample_matching_ids(collection, rnd: random.Random, count: int,
                               match: Callable[[UUID], Awaitable[object | None]]) -> tuple[list[tuple[UUID, object]], int]:
    """Up to ``count`` random ids of ``collection`` with what ``match`` returned for them (ids
    for which it returns None are skipped), and how many ids were checked."""
    if count <= 0:
        return [], 0
    response = await collection.query.fetch_objects(limit=FILTER_CHECKS, return_properties=[])
    ids = sorted(o.uuid for o in response.objects)
    rnd.shuffle(ids)
    found, checked = [], 0
    for candidate in ids:
        if len(found) >= count:
            break
        checked += 1
        matched = await match(candidate)
        if matched is not None:
            found.append((candidate, matched))
    return found, checked


def _sampled_chunk(obj, vector_name: str | None, terms_per_query: int) -> tuple[SampledChunk, str | None]:
    vector, vector_name = _pick_vector(obj.vector, vector_name)
    docs = (obj.references or {}).get("document")
    return SampledChunk(
        id=obj.uuid, vector=vector, terms=terms(obj.properties.get("text") or "", terms_per_query),
        document_id=docs.objects[0].uuid if docs and docs.objects else None,
        order=obj.properties.get("order")), vector_name


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
    available: set[str] = set()
    for obj in objects:
        if obj is None:
            continue
        available |= set(obj.vector) if isinstance(obj.vector, dict) else {"default"} if obj.vector else set()
        sampled[obj.uuid], vector_name = _sampled_chunk(obj, vector_name, q.terms_per_query)
    if target_vector is not None and sampled and not any(c.vector is not None for c in sampled.values()):
        raise ValueError(f"no sampled chunk has the named vector {target_vector!r}; "
                         f"available: {', '.join(sorted(available)) or 'none'}")
    inputs = Inputs(chunks=list(sampled.values()), vector_name=vector_name)
    if not inputs.chunks:
        inputs.notes.append("no chunks could be sampled")
    if target_vector is None and len(available) > 1:
        inputs.notes.append(f"named vectors {', '.join(sorted(available))}: using {vector_name!r} "
                            "(select one with --target-vector)")
    missing = sum(1 for c in inputs.chunks if c.vector is None)
    if missing:
        inputs.notes.append(f"{missing} sampled chunks have no {vector_name!r} vector")

    needs = {s.filter for s in profile.scenarios} | {s.kind for s in profile.scenarios}
    search = ChunkSearchRepository(client, names)

    async def chunk_inside(**query) -> SampledChunk | None:
        """A chunk the application's filter for ``query`` matches (the same filter the search uses)."""
        flt = search._filter(ChunkQuery(text="", mode=SearchType.text, limit=1, **query))
        found = (await chunks.query.fetch_objects(filters=flt, limit=1, **fetch)).objects
        return _sampled_chunk(found[0], vector_name, q.terms_per_query)[0] if found else None

    if "tag" in needs:
        inputs.scoped["tag"], inputs.filter_values_checked["tag"] = await _sample_matching_ids(
            client.collections.get(names.tag_collection_name), rnd, q.sample_tags,
            lambda i: chunk_inside(tags=TagFilter((i,), automatic=True, positive=True)))
        inputs.tags = [value for value, _ in inputs.scoped["tag"]]
    if "user_collection" in needs:
        inputs.scoped["user_collection"], inputs.filter_values_checked["user_collection"] = await _sample_matching_ids(
            client.collections.get(names.user_collection_name), rnd, q.sample_user_collections,
            lambda i: chunk_inside(collection_id=i))
        inputs.user_collections = [value for value, _ in inputs.scoped["user_collection"]]
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

    def _scoped(self, scenario: Scenario) -> list[tuple[UUID, SampledChunk]] | None:
        """Tag / user-collection searches: (value, chunk inside it) pairs usable for the scenario's mode."""
        if scenario.kind != "search" or scenario.filter not in self.inputs.scoped:
            return None
        return [(v, c) for v, c in self.inputs.scoped[scenario.filter]
                if (scenario.mode == "text" or c.vector is not None) and (scenario.mode == "vector" or c.terms)]

    def _usable(self, scenario: Scenario) -> list[SampledChunk]:
        scoped = self._scoped(scenario)
        if scoped is not None:
            return [c for _, c in scoped]
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
            return f"no {scenario.filter} value that matches any chunk"
        return None

    def fingerprint(self, scenario: Scenario, index: int) -> str:
        """Identifies the query of ``index`` (its input and filter value); keyed by ``IdHasher`` before it is written."""
        if scenario.kind in ("aggregate", "mixed"):
            return short_hash(index)
        chunk = self._usable(scenario)[index % self.input_count(scenario)]
        return short_hash((chunk.id, self._filter_value(scenario, index)))

    def _filter_value(self, scenario: Scenario, index: int):
        scoped = self._scoped(scenario)
        if scoped is not None:
            return scoped[index % len(scoped)][0] if scoped else None
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
                target_vector=self.inputs.vector_name if scenario.mode != "text" else None,
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
