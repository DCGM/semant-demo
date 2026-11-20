"""The benchmark store (``store_api``): a Weaviate owned by the benchmark, holding one dataset's
corpus with named vectors per embedding model, searched with the application's passage search.

``open_store(spec)`` connects to ``spec.host`` or starts (reuses) the store's own container
(``container.py``), then verifies or establishes ownership:

* the token is read from ``spec.token_file`` (created with mode 0600 on first use); the
  instance's ``schema.MARKER`` collection holds its SHA-256, never the token;
* an instance with no collections at all is claimed (the marker is written, then the schema);
* an instance whose marker holds the token is reused with its data;
* anything else is refused (``StoreNotOwned``): data without the marker, as in the development
  stores, the automated-test stores or production, and a marker of another token.

Every write (``load``, ``ensure_vector``) verifies the marker again first. Nothing here deletes
a collection or an object.

The tests' throwaway Weaviate already holds the tests' own marker; they pass
``tolerated_collections`` to claim it beside that marker. Without it (the default) nothing
counts as empty but an instance without collections.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid5

import httpx
from weaviate import WeaviateAsyncClient
from weaviate.classes.config import Configure, VectorDistances
from weaviate.classes.data import DataObject
from weaviate.classes.query import HybridFusion

from semant_demo.adapters.embeddings.openai_compatible import OpenAICompatibleEmbeddings
from semant_demo.adapters.weaviate.chunk_visibility import PROPERTY as DOCUMENT_PUBLIC_FLAG
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.user_collections import UserCollectionRepository
from semant_demo.benchmarks.search_relevance import container, schema
from semant_demo.benchmarks.search_relevance.embeddings import BatchEmbeddings
from semant_demo.benchmarks.search_relevance.search import BenchmarkChunkSearch
from semant_demo.benchmarks.search_relevance.contracts import CorpusChunk, Dataset, RunConfiguration, VectorSpec
from semant_demo.benchmarks.search_relevance.embedding_cache import (
    EmbeddingCache, check_template, input_hash, render, valid_embedding)
from semant_demo.benchmarks.search_relevance.store_api import (
    EmbeddingEndpoint, LoadReport, SearchOutcome, Searcher, StoreSpec, VectorReport)
from semant_demo.config import Config
from semant_demo.features.documents.criteria import SearchCriteria
from semant_demo.features.search.schemas import PassageSearchRequest, SearchType
from semant_demo.features.search.service import SearchBackends, search_passages
from semant_demo.features.search.vectors import SearchVector, SearchVectors

logger = logging.getLogger(__name__)

PURPOSE = "semant-search-benchmark"
_RECORDS = UUID("6b1d6c55-6e3a-4c1e-9d0a-5e3b5e3b0726")
OWNER = uuid5(_RECORDS, "owner")
DATASET = uuid5(_RECORDS, "dataset")
PAGE = uuid5(_RECORDS, "page")
"""The namespace of the made-up page id of a document's chunks (a hit requires one)."""
INSERT_BATCH = 500
FIRST_PAGE = 20
"""Passages a search reads in full after ranking, as the application's first page of results."""
WRITE_CONCURRENCY = 16
EMBED_ATTEMPTS = 4
"""Tries of one embedding batch; transport errors, 429 and 5xx are retried."""
VECTOR_NAME = re.compile(r"^[_A-Za-z][_A-Za-z0-9]*$")
"""Weaviate builds GraphQL names from vector names (``VectorSettings.target_vector``, #385)."""
FUSIONS = {"relativeScore": HybridFusion.RELATIVE_SCORE, "ranked": HybridFusion.RANKED}


class StoreNotOwned(RuntimeError):
    """The instance is not this benchmark store's (no marker, another token, or not empty)."""


class StoreDatasetMismatch(RuntimeError):
    """The store holds another dataset (id, version or manifest) than the one loaded."""


class StoreVectorMismatch(RuntimeError):
    """The named vector exists with another model, template or dimensions, or not by this store."""


# ---- ownership ----------------------------------------------------------------------------

def read_or_create_token(path: Path) -> str:
    """The ownership token in ``path``; a new random one (mode 0600) when the file is missing."""
    path = Path(path).expanduser()
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if not token:
            raise StoreNotOwned(f"The token file {path} is empty.")
        return token
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token + "\n")
    return token


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def claim_decision(collections: Collection[str], owner_hash: str | None, token_hash: str,
                   tolerated: Collection[str] = ()) -> str:
    """``"owned"`` (the marker holds the token), ``"claim"`` (nothing there but ``tolerated``)
    or ``StoreNotOwned``. ``owner_hash`` is the marker's token hash, None without a marker."""
    if schema.MARKER in collections:
        if owner_hash is None or not secrets.compare_digest(owner_hash, token_hash):
            raise StoreNotOwned(f"This Weaviate holds another benchmark store's marker ({schema.MARKER}, a "
                                "different token). Use that store's token file or another instance.")
        return "owned"
    other = sorted(set(collections) - set(tolerated))
    if other:
        raise StoreNotOwned(
            "Refusing a Weaviate that holds data the benchmark did not create "
            f"(collections: {', '.join(other[:8])}{', …' if len(other) > 8 else ''}). The benchmark store "
            "claims only an empty instance: start its own container (StoreSpec.host unset).")
    return "claim"


async def _owner_hash(client: WeaviateAsyncClient) -> str | None:
    obj = await client.collections.get(schema.MARKER).query.fetch_object_by_id(OWNER)
    if obj is None or obj.properties.get("purpose") != PURPOSE:
        return None
    return obj.properties.get("token_sha256")


async def claim(client: WeaviateAsyncClient, token: str, tolerated: Collection[str] = ()) -> str:
    """Verify, or on an empty instance establish, ownership; ``"owned"`` or ``"claimed"``."""
    names = set((await client.collections.list_all(simple=True)).keys())
    owner = await _owner_hash(client) if schema.MARKER in names else None
    if claim_decision(names, owner, token_sha256(token), tolerated) == "owned":
        return "owned"
    await schema.create_marker(client)
    await client.collections.get(schema.MARKER).data.insert(
        {"kind": "owner", "name": "owner", "purpose": PURPOSE, "token_sha256": token_sha256(token),
         "state": "claimed", "info": json.dumps({"schema_version": schema.SCHEMA_VERSION}), "updated": _now()},
        uuid=OWNER)
    return "claimed"


async def verify(client: WeaviateAsyncClient, token: str) -> None:
    """Raise ``StoreNotOwned`` unless the marker holds ``token``: before every write."""
    names = set((await client.collections.list_all(simple=True)).keys())
    if schema.MARKER not in names:
        raise StoreNotOwned(f"The instance has no {schema.MARKER} marker (any more); refusing to write.")
    claim_decision(names, await _owner_hash(client), token_sha256(token))


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- search configuration -----------------------------------------------------------------

def bm25_properties(properties: dict[str, float] | None) -> list[str] | None:
    """Weaviate's ``query_properties`` of a configuration's BM25 properties and boosts."""
    if properties is None:
        return None
    return [name if boost == 1 else f"{name}^{boost:g}" for name, boost in properties.items()]


def hit_score(mode: SearchType, recorded: tuple[float | None, float | None] | None) -> float | None:
    """BM25 and hybrid: Weaviate's score; vector: the cosine similarity (1 - distance)."""
    if recorded is None:
        return None
    score, distance = recorded
    if mode == SearchType.vector:
        return None if distance is None else 1.0 - distance
    return score


class _TimedEmbedder:
    """Query embeddings through ``embedder``, timed."""

    def __init__(self, embedder: OpenAICompatibleEmbeddings):
        self.embedder = embedder
        self.ms = 0.0

    async def embed_query(self, text: str) -> list[float]:
        start = perf_counter()
        try:
            return await self.embedder.embed_query(text)
        finally:
            self.ms += (perf_counter() - start) * 1000

    async def embed_document(self, text: str) -> list[float]:
        raise NotImplementedError("the benchmark does not search with HyDE")


class _NoEmbedder:
    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("a text search does not embed its query")

    embed_document = embed_query


def _api_key(endpoint: EmbeddingEndpoint) -> str:
    return os.environ.get(endpoint.api_key_env, "") if endpoint.api_key_env else ""


def _embedding_client(model: str, endpoint: EmbeddingEndpoint, dimensions: int | None, query_prefix: str,
                      transport: httpx.AsyncBaseTransport | None) -> OpenAICompatibleEmbeddings:
    """The application's own client for a search's query embedding (embedded as the application does)."""
    return OpenAICompatibleEmbeddings(endpoint.base_url, model, api_key=_api_key(endpoint), query_prefix=query_prefix,
                                      document_prefix="", dimensions=dimensions, timeout=endpoint.timeout,
                                      transport=transport)


def _document_client(model: str, endpoint: EmbeddingEndpoint, dimensions: int | None,
                     transport: httpx.AsyncBaseTransport | None) -> BatchEmbeddings:
    """The benchmark's batched client for the corpus's document embeddings."""
    return BatchEmbeddings(endpoint.base_url, model, api_key=_api_key(endpoint), dimensions=dimensions,
                           timeout=endpoint.timeout, transport=transport)


def _failure_class(error: BaseException) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP{error.response.status_code}"
    return type(error).__name__


def _retryable(error: BaseException) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return isinstance(error, httpx.TransportError)


# ---- the store ----------------------------------------------------------------------------

@dataclass
class _Pending:
    chunk_id: UUID
    key: str
    text: str


class WeaviateBenchmarkStore:
    """``store_api.BenchmarkStore`` over a connected, owned Weaviate (``open_store``)."""

    def __init__(self, client: WeaviateAsyncClient, token: str, names: CollectionNames, *,
                 embedding_transport: httpx.AsyncBaseTransport | None = None, retry_delay: float = 1.0,
                 endpoint: str = ""):
        self.client = client
        self._token = token
        self.names = names
        self.embedding_transport = embedding_transport
        """The HTTP transport of embedding requests (tests: the fake providers); None: the network."""
        self.retry_delay = retry_delay
        self.endpoint = endpoint

    def _collection(self, name: str):
        return self.client.collections.get(name)

    async def _record(self, uuid: UUID) -> dict[str, Any] | None:
        obj = await self._collection(schema.MARKER).query.fetch_object_by_id(uuid)
        return None if obj is None else dict(obj.properties)

    async def _write_record(self, uuid: UUID, kind: str, name: str, state: str, info: dict[str, Any]) -> None:
        marker = self._collection(schema.MARKER)
        properties = {"kind": kind, "name": name, "state": state, "info": json.dumps(info, sort_keys=True),
                      "updated": _now()}
        if await marker.data.exists(uuid):
            await marker.data.update(uuid=uuid, properties=properties)
        else:
            await marker.data.insert(properties, uuid=uuid)

    async def _ids(self, collection: str) -> set[UUID]:
        return {UUID(str(obj.uuid)) async for obj in self._collection(collection).iterator(return_properties=[])}

    # ---- corpus ---------------------------------------------------------------------------

    async def load(self, dataset: Dataset) -> LoadReport:
        """Write the dataset's documents and chunks with their original ids; nothing when this
        dataset's corpus is loaded already. The identity is the dataset id, version and the
        SHA-256 of ``corpus.jsonl``: the generator loads a corpus-only dataset to pool in, and
        the final dataset with the same corpus is then already loaded. Refuses another dataset
        or corpus (``StoreDatasetMismatch``). An interrupted load is completed by loading the
        same dataset again."""
        await verify(self.client, self._token)
        identity = {"dataset_id": dataset.manifest.dataset_id, "version": dataset.manifest.version,
                    "corpus_sha256": dataset.manifest.files["corpus.jsonl"].sha256}
        report = LoadReport(dataset_id=identity["dataset_id"], version=identity["version"])
        record = await self._record(DATASET)
        if record is not None:
            loaded = json.loads(record["info"])
            held = {k: loaded.get(k) for k in identity}
            if held != identity:
                raise StoreDatasetMismatch(
                    f"The store holds dataset {held['dataset_id']} {held['version']} (corpus "
                    f"{str(held['corpus_sha256'])[:12]}…), not {identity['dataset_id']} {identity['version']} "
                    f"(corpus {identity['corpus_sha256'][:12]}…). A store holds one dataset: use another "
                    "store (StoreSpec.name) or recreate this one.")
            if record.get("state") == "loaded":
                count = (await self._collection(self.names.chunks_collection_name).aggregate.over_all(
                    total_count=True)).total_count
                if count != len(dataset.corpus):
                    raise StoreDatasetMismatch(f"The store holds {count} chunks, the dataset {len(dataset.corpus)}; "
                                               "it was changed since it was loaded. Recreate the store.")
                report.already_loaded = True
                return report
        await self._write_record(DATASET, "dataset", identity["dataset_id"], "loading", identity)

        documents: dict[UUID, CorpusChunk] = {}
        for chunk in dataset.corpus.values():
            documents.setdefault(chunk.document_id, chunk)
        have = await self._ids(self.names.document_collection_name)
        report.documents_written = await self._insert(self.names.document_collection_name, [
            DataObject(uuid=document_id, properties=_document_properties(chunk))
            for document_id, chunk in documents.items() if document_id not in have])
        have = await self._ids(self.names.chunks_collection_name)
        report.chunks_written = await self._insert(self.names.chunks_collection_name, [
            DataObject(uuid=chunk.chunk_id, properties=_chunk_properties(chunk),
                       references={"document": chunk.document_id})
            for chunk in dataset.corpus.values() if chunk.chunk_id not in have])
        await self._write_record(DATASET, "dataset", identity["dataset_id"], "loaded",
                                 {**identity, "chunks": len(dataset.corpus), "documents": len(documents)})
        return report

    async def _insert(self, collection: str, objects: list[DataObject]) -> int:
        target = self._collection(collection)
        for start in range(0, len(objects), INSERT_BATCH):
            result = await target.data.insert_many(objects[start:start + INSERT_BATCH])
            if result.errors:
                first = next(iter(result.errors.values()))
                raise RuntimeError(f"Writing {collection}: {len(result.errors)} objects failed, e.g. {first.message}")
        return len(objects)

    # ---- vectors --------------------------------------------------------------------------

    async def ensure_vector(self, spec: VectorSpec, endpoint: EmbeddingEndpoint, cache_dir: Path) -> VectorReport:
        """Add the named vector ``spec.target_vector`` (self-provided, HNSW, cosine) if missing
        and give every chunk without it its document embedding: from the cache, else embedded
        through ``endpoint`` in batches (``batch_size``, at most ``concurrency`` at a time,
        retried) and cached. A chunk whose embedding failed gets no vector and is counted by
        failure class; running again embeds only those."""
        check_template(spec.document_template)
        if not VECTOR_NAME.match(spec.target_vector):
            raise ValueError(f"Invalid named vector {spec.target_vector!r} (a GraphQL name is needed, #385)")
        await verify(self.client, self._token)
        dataset = await self._record(DATASET)
        if dataset is None or dataset.get("state") != "loaded":
            raise RuntimeError("Load a dataset before adding vectors.")
        await self._ensure_named_vector(spec)

        report = VectorReport(vector=spec.target_vector)
        chunks = self._collection(self.names.chunks_collection_name)
        pending: list[_Pending] = []
        async for obj in chunks.iterator(include_vector=[spec.target_vector], return_properties=["text", "title"]):
            if (obj.vector or {}).get(spec.target_vector):
                continue
            text = render(spec.document_template, obj.properties.get("text") or "", obj.properties.get("title"))
            pending.append(_Pending(UUID(str(obj.uuid)), input_hash(text), text))
        if not pending:
            return report

        cache = EmbeddingCache(cache_dir, spec.model, spec.document_template, spec.dimensions)
        embedder = _document_client(spec.model, endpoint, spec.dimensions, self.embedding_transport)
        dimensions = [spec.dimensions]
        window = max(1, endpoint.batch_size) * max(1, endpoint.concurrency) * 4
        for start in range(0, len(pending), window):
            await self._embed_window(pending[start:start + window], cache, embedder, endpoint, dimensions, report)
        if report.failed:
            logger.warning("Vector %s: %d chunks without an embedding (%s)", spec.target_vector,
                           sum(report.failed.values()), ", ".join(f"{k}: {v}" for k, v in report.failed.items()))
        return report

    async def _ensure_named_vector(self, spec: VectorSpec) -> None:
        chunks = self._collection(self.names.chunks_collection_name)
        record_id = uuid5(_RECORDS, f"vector:{spec.target_vector}")
        identity = {"model": spec.model, "document_template": spec.document_template, "dimensions": spec.dimensions}
        index = {"type": "hnsw", "distance": "cosine", "vectorizer": "none"}
        record = await self._record(record_id)
        config = await chunks.config.get()
        exists = spec.target_vector in (config.vector_config or {})
        if record is not None:
            held = json.loads(record["info"])
            if {k: held.get(k) for k in identity} != identity:
                raise StoreVectorMismatch(
                    f"Vector {spec.target_vector} holds {held.get('model')} (template {held.get('document_template')!r}, "
                    f"dimensions {held.get('dimensions')}), not {spec.model} (template {spec.document_template!r}, "
                    f"dimensions {spec.dimensions}). Use another target_vector.")
        elif exists:
            raise StoreVectorMismatch(f"Vector {spec.target_vector} exists but was not added by ensure_vector.")
        if not exists:
            await chunks.config.add_vector(vector_config=Configure.Vectors.self_provided(
                name=spec.target_vector,
                vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances.COSINE)))
        if record is None:
            await self._write_record(record_id, "vector", spec.target_vector, "ready",
                                     {**identity, "vector_spec_id": spec.id, "index": index})

    async def _embed_window(self, window: list[_Pending], cache: EmbeddingCache, embedder: BatchEmbeddings,
                            endpoint: EmbeddingEndpoint, dimensions: list[int | None], report: VectorReport) -> None:
        vectors: dict[str, list[float]] = {}
        cached_keys = set()
        missing: dict[str, str] = {}
        for item in window:
            embedding = cache.get(item.key)
            if embedding is not None:
                vectors[item.key] = embedding
                cached_keys.add(item.key)
            else:
                missing.setdefault(item.key, item.text)
        failed: dict[str, str] = {}
        keys = list(missing)
        batch_size = max(1, endpoint.batch_size)
        semaphore = asyncio.Semaphore(max(1, endpoint.concurrency))

        async def embed(batch: list[str]) -> None:
            async with semaphore:
                try:
                    embeddings = await self._embed_with_retries(embedder, [missing[k] for k in batch])
                except Exception as e:  # counted per chunk; the others go on
                    for key in batch:
                        failed[key] = _failure_class(e)
                    return
            good = {}
            for key, embedding in zip(batch, embeddings):
                if dimensions[0] is None and valid_embedding(embedding, None):
                    dimensions[0] = len(embedding)
                if valid_embedding(embedding, dimensions[0]):
                    good[key] = [float(x) for x in embedding]
                else:
                    failed[key] = "InvalidEmbedding"
            cache.put_many(good)
            vectors.update(good)

        await asyncio.gather(*(embed(keys[i:i + batch_size]) for i in range(0, len(keys), batch_size)))

        chunks = self._collection(self.names.chunks_collection_name)
        writes = asyncio.Semaphore(WRITE_CONCURRENCY)

        async def write(item: _Pending) -> None:
            async with writes:
                try:
                    await chunks.data.update(uuid=item.chunk_id, vector={report.vector: vectors[item.key]})
                except Exception as e:
                    report.failed[f"Write{type(e).__name__}"] = report.failed.get(f"Write{type(e).__name__}", 0) + 1
                    return
            report.written += 1

        for item in window:
            if item.key in failed:
                report.failed[failed[item.key]] = report.failed.get(failed[item.key], 0) + 1
            elif item.key in cached_keys:
                report.from_cache += 1
            else:
                report.embedded += 1
        await verify(self.client, self._token)
        await asyncio.gather(*(write(item) for item in window if item.key in vectors))

    async def _embed_with_retries(self, embedder: BatchEmbeddings, texts: list[str]) -> list[list[float]]:
        for attempt in range(1, EMBED_ATTEMPTS + 1):
            try:
                return await embedder.embed_documents(texts)
            except Exception as e:
                if attempt == EMBED_ATTEMPTS or not _retryable(e):
                    raise
                await asyncio.sleep(self.retry_delay * 2 ** (attempt - 1))
        raise AssertionError("unreachable")

    # ---- search ---------------------------------------------------------------------------

    def searcher(self, configuration: RunConfiguration, endpoint: EmbeddingEndpoint | None) -> Searcher:
        """The application's passage search (``search_passages``, anonymous, no filters) over
        this store in ``configuration``: its mode, alpha, fusion, BM25 properties and boosts,
        query prefix and depth (the ranking's ``retrieval_limit``; the first ``FIRST_PAGE``
        passages are read in full, as the application's first page). Query
        embeddings come from ``endpoint``. ``embed_ms`` is the query embedding's time (None for
        BM25), ``search_ms`` the rest of the search."""
        mode = SearchType(configuration.mode)
        vector = configuration.vector
        if mode != SearchType.text and endpoint is None:
            raise ValueError(f"{configuration.configuration_id}: a {mode.value} search needs an embedding endpoint")
        client = None
        if vector is not None and endpoint is not None and mode != SearchType.text:
            client = _embedding_client(vector.model, endpoint, vector.dimensions, vector.query_prefix,
                                       self.embedding_transport)
        fusion = FUSIONS[configuration.fusion] if configuration.fusion else None
        properties = bm25_properties(configuration.properties) if mode != SearchType.vector else None
        vector_id = vector.id if vector is not None else "bm25"
        target = vector.target_vector if vector is not None else "default"
        depth = configuration.depth

        async def search(query: str) -> SearchOutcome:
            embedder = _TimedEmbedder(client) if client is not None else _NoEmbedder()
            chunks = BenchmarkChunkSearch(self.client, self.names, fusion=fusion, query_properties=properties)
            backends = SearchBackends(
                chunks=chunks, collections=UserCollectionRepository(self.client, self.names, None),
                vectors=SearchVectors([SearchVector(vector_id, vector_id, "", target, embedder)], vector_id))
            request = PassageSearchRequest(
                criteria=SearchCriteria(text_query=query), limit=min(depth, FIRST_PAGE), type=mode,
                hybrid_search_alpha=configuration.alpha if configuration.alpha is not None else 0.5, vector=vector_id)
            start = perf_counter()
            response = await search_passages(backends, None, request, None, retrieval_limit=depth)
            total = (perf_counter() - start) * 1000
            embed_ms = embedder.ms if isinstance(embedder, _TimedEmbedder) else None
            ranked = [UUID(str(i)) for i in response.ranked_ids]
            return SearchOutcome(hits=[(i, hit_score(mode, chunks.scores.get(i))) for i in ranked], embed_ms=embed_ms,
                                 search_ms=max(0.0, total - (embed_ms or 0.0)))

        return search

    # ---- description ----------------------------------------------------------------------

    async def describe(self) -> dict[str, Any]:
        meta = await self.client.get_meta()
        dataset = await self._record(DATASET)
        marker = self._collection(schema.MARKER)
        vectors = {}
        async for obj in marker.iterator():
            if obj.properties.get("kind") == "vector":
                vectors[obj.properties["name"]] = json.loads(obj.properties["info"])
        return {
            "weaviate_version": meta.get("version"),
            "instance": self.endpoint,
            "schema_version": schema.SCHEMA_VERSION,
            "collections": await schema.describe_collections(self.client, self.names),
            "vectors": vectors,
            "dataset": None if dataset is None else {**json.loads(dataset["info"]), "state": dataset.get("state")},
        }

    async def close(self) -> None:
        await self.client.close()


def _document_properties(chunk: CorpusChunk) -> dict[str, Any]:
    info = chunk.document
    found: dict[str, Any] = {"public": True}
    if info.title is not None:
        found["title"] = info.title
    if info.year is not None:
        found["yearIssued"] = info.year
    if info.document_type is not None:
        found["documentType"] = info.document_type
    return found


def _chunk_properties(chunk: CorpusChunk) -> dict[str, Any]:
    """The stored chunk: its text, title, order, language and document year, public (anonymous
    search selects ``documentPublic``, #793; the documents are public), and the page properties
    a search hit requires, which the dataset does not have (``PAGE``, page 1)."""
    found: dict[str, Any] = {"text": chunk.text, "order": chunk.order, "language": chunk.language,
                             DOCUMENT_PUBLIC_FLAG: True,
                             "start_page_id": str(uuid5(PAGE, str(chunk.document_id))), "from_page": 1,
                             "to_page": 1, "end_paragraph": True}
    if chunk.title is not None:
        found["title"] = chunk.title
    if chunk.document.year is not None:
        found["yearIssued"] = chunk.document.year
    return found


async def open_store(spec: StoreSpec, *, embedding_transport: httpx.AsyncBaseTransport | None = None,
                     tolerated_collections: Collection[str] = ()) -> WeaviateBenchmarkStore:
    """``store_api.OpenStore``: connect to ``spec.host`` or start (reuse) the store's container,
    verify or establish ownership and create the schema's missing collections.

    ``embedding_transport`` (tests): the HTTP transport of the embedding requests.
    ``tolerated_collections`` (tests): collections that do not make an instance non-empty when
    it is claimed, e.g. the automated tests' own marker on their throwaway instance."""
    token = read_or_create_token(spec.token_file)
    if spec.host is not None:
        endpoint = container.Endpoint(spec.host, spec.rest_port or 8080, spec.grpc_port or 50051)
    else:
        endpoint = await asyncio.to_thread(container.ensure_container, spec)
    config = Config(environ={"WEAVIATE_HOST": endpoint.host, "WEAVIATE_REST_PORT": str(endpoint.rest_port),
                             "WEAVIATE_GRPC_PORT": str(endpoint.grpc_port)})
    client = await connect_weaviate(config)
    try:
        state = await claim(client, token, tolerated_collections)
        await verify(client, token)
        created = await schema.create_app_collections(client, config.collectionNames)
        logger.info("Benchmark store %s:%d %s%s", endpoint.host, endpoint.rest_port, state,
                    f", created {', '.join(created)}" if created else "")
    except BaseException:
        await client.close()
        raise
    return WeaviateBenchmarkStore(client, token, config.collectionNames, embedding_transport=embedding_transport,
                                  endpoint="given instance" if spec.host is not None else f"container {spec.name}")
