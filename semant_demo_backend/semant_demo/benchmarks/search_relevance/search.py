"""The application's chunk search with the benchmark's settings (#727).

``BenchmarkChunkSearch`` is the application's ``ChunkSearchRepository`` with one step replaced:
the query that ranks the chunks (``_ranked``). It keeps everything else of the application's
search: the access filter (``_filter``: public documents, #793), the limit, the vector selection
and how ``search_passages`` reads the results. The replaced step adds what the application does
not set: the hybrid fusion type, the BM25 properties with boosts, and Weaviate's score metadata,
which it records per ranked chunk.

The application's classes stay as they are; nothing here changes them. The price is a dependency
on two internal names of ``ChunkSearchRepository`` (``_ranked`` and ``_filter``). If the
application changes how it ranks, ``tests/test_search_benchmark_store.py`` (the same query
arguments as the application's for default settings) and the integration tests fail.
"""
from collections.abc import Sequence
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import HybridFusion, MetadataQuery

from semant_demo.adapters.weaviate.names import CollectionNames
from semant_demo.adapters.weaviate.search import ChunkSearchRepository
from semant_demo.features.search.schemas import ChunkQuery, SearchType

SCORES = MetadataQuery(score=True, distance=True)


class BenchmarkChunkSearch(ChunkSearchRepository):
    """One search's repository (it records that search's scores)."""

    def __init__(self, client: WeaviateAsyncClient, names: CollectionNames, *, fusion: HybridFusion | None = None,
                 query_properties: Sequence[str] | None = None):
        super().__init__(client, names)
        self.fusion = fusion
        """Hybrid fusion; None: Weaviate's default (relative score), as the application."""
        self.query_properties = list(query_properties) if query_properties is not None else None
        """BM25 properties, optionally boosted (``"title^2"``); None: every text property, as the application."""
        self.scores: dict[UUID, tuple[float | None, float | None]] = {}
        """Chunk id -> (Weaviate's score, vector distance) as Weaviate returned them."""

    async def _ranked(self, query: ChunkQuery, **returned):
        chunks = self.client.collections.get(self.collectionNames.chunks_collection_name)
        common = dict(limit=query.limit, filters=await self._filter(query), return_metadata=SCORES, **returned)
        if query.mode == SearchType.text:
            result = await chunks.query.bm25(query=query.text, query_properties=self.query_properties, **common)
        elif query.mode == SearchType.vector:
            vector, target = _vector(query)
            result = await chunks.query.near_vector(near_vector=vector, target_vector=target, **common)
        elif query.mode == SearchType.hybrid:
            vector, target = _vector(query)
            result = await chunks.query.hybrid(query=query.text, alpha=query.alpha, vector=vector,
                                               target_vector=target, fusion_type=self.fusion,
                                               query_properties=self.query_properties, **common)
        else:
            raise ValueError(f"Unknown search type: {query.mode}")
        for obj in result.objects:
            metadata = obj.metadata
            self.scores.setdefault(UUID(str(obj.uuid)),
                                   (metadata.score, metadata.distance) if metadata else (None, None))
        return result


def _vector(query: ChunkQuery) -> tuple[list[float], str]:
    if query.vector is None or not query.target_vector:
        raise ValueError(f"{query.mode.value} search needs a query vector and its target vector")
    return query.vector, query.target_vector
