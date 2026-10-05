import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue, ConfigurableSubclassFactory
from tqdm import tqdm

from .db import get_async_client, ensure_named_vector_exists
# Import embedders to register their subclasses for ConfigurableSubclassFactory
from .embedders import Embedder, VLLMEmbedder


@dataclass
class PipelineStats:
    scanned: int = 0  # records read from the collection
    already_filled: int = 0  # records that already have the vector
    empty: int = 0  # records whose rendered input text is empty
    embedded: int = 0  # records whose vector was written in this run
    dimension: Optional[int] = None

    # current state of the records in the pipeline (for monitoring of utilization and bottlenecks)
    queued: int = 0  # records waiting in the queue for an embedding request
    embedding: int = 0  # records in running embedding requests
    writing: int = 0  # records with embeddings that are being written to the database

    def postfix(self) -> dict:
        return {
            "embedded": self.embedded,
            "filled": self.already_filled,
            "empty": self.empty,
            "queued": self.queued,
            "embedding": self.embedding,
            "writing": self.writing,
        }


class EmbeddingPipeline(ConfigurableMixin, CreatableMixin):
    """A fully configurable pipeline that scans Weaviate database records, embeds those that do not have
    the given named vector yet, and writes the embeddings back as that named vector.

    Records that already have the vector are skipped, thus the pipeline can be interrupted at any time
    and it continues where it stopped when started again.
    """

    # Weaviate connection settings
    weaviate_host: str = ConfigurableValue(
        desc="Weaviate host address",
        user_default="localhost"
    )
    weaviate_port: int = ConfigurableValue(
        desc="Weaviate HTTP/REST port",
        user_default=8080
    )
    weaviate_grpc_port: int = ConfigurableValue(
        desc="Weaviate gRPC port (required for client v4)",
        user_default=50051
    )
    weaviate_api_key: Optional[str] = ConfigurableValue(
        desc="Authentication API Key for Weaviate instance",
        user_default=None,
        voluntary=True
    )
    weaviate_headers: Optional[dict] = ConfigurableValue(
        desc="Additional HTTP headers (e.g. API keys for third-party vectorizers)",
        user_default=None,
        voluntary=True
    )

    collection: str = ConfigurableValue(
        desc="Name of the Weaviate collection to embed (it must use named vectors)",
        user_default="Chunks"
    )

    # Target vector settings
    vector_name: str = ConfigurableValue(
        desc="Name of the named vector the embeddings are written to",
        user_default="my_embedder",
        validator=lambda x: isinstance(x, str) and len(x) > 0
    )
    create_vector: bool = ConfigurableValue(
        desc="Create the named vector in the collection schema if it does not exist",
        user_default=True
    )
    vector_index_type: str = ConfigurableValue(
        desc="Vector index type used when the named vector is created (hnsw, flat, dynamic)",
        user_default="hnsw"
    )
    distance_metric: str = ConfigurableValue(
        desc="Distance metric used when the named vector is created (cosine, dot, l2-squared, hamming, manhattan)",
        user_default="cosine"
    )

    # Record selection
    return_properties: Optional[list] = ConfigurableValue(
        desc="Properties fetched for the embedder input template (None for all non-reference properties)",
        user_default=None,
        voluntary=True
    )
    max_records: Optional[int] = ConfigurableValue(
        desc="Maximum total records to embed in this run (None or 0 for unlimited)",
        user_default=None,
        voluntary=True
    )

    # Execution settings
    scan_batch_size: int = ConfigurableValue(
        desc="Number of records read from the database per batch",
        user_default=512
    )
    embed_batch_size: int = ConfigurableValue(
        desc="Number of texts sent to the embedder in a single request",
        user_default=32
    )
    max_concurrent_requests: int = ConfigurableValue(
        desc="Maximum number of embedding requests running at the same time",
        user_default=8
    )
    max_concurrent_writes: int = ConfigurableValue(
        desc="Maximum number of database updates running at the same time",
        user_default=32
    )
    max_retries: int = ConfigurableValue(
        desc="Maximum number of retries for database operations in case of connection errors",
        user_default=5
    )
    retry_delay: float = ConfigurableValue(
        desc="Delay in seconds between retries",
        user_default=10.0
    )

    # Embedder settings
    embedder: Embedder = ConfigurableSubclassFactory(
        parent_cls_type=Embedder,
        desc="Embedder configuration",
        user_default=VLLMEmbedder
    )

    def run(self) -> None:
        """Run the embedding pipeline."""
        asyncio.run(self.run_async())

    async def run_async(self) -> None:
        """Run the embedding pipeline in the current event loop."""
        client = get_async_client(
            host=self.weaviate_host,
            port=self.weaviate_port,
            grpc_port=self.weaviate_grpc_port,
            headers=self.weaviate_headers,
            api_key=self.weaviate_api_key
        )

        stats = PipelineStats()
        pbar = None
        try:
            async with client:
                if self.create_vector:
                    await ensure_named_vector_exists(
                        client=client,
                        collection_name=self.collection,
                        vector_name=self.vector_name,
                        index_type=self.vector_index_type,
                        distance_metric=self.distance_metric
                    )
                else:
                    schema_config = await client.collections.use(self.collection).config.get()
                    if self.vector_name not in (schema_config.vector_config or {}):
                        raise ValueError(f"Named vector '{self.vector_name}' does not exist in collection '{self.collection}' and create_vector is disabled.")

                collection = client.collections.use(self.collection)

                print(f"Starting embedding pipeline on collection '{self.collection}' (vector '{self.vector_name}')...")
                total_count = (await collection.aggregate.over_all(total_count=True)).total_count
                pbar = tqdm(total=total_count, desc="Embedding records")

                queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_concurrent_requests * 2)
                write_semaphore = asyncio.Semaphore(self.max_concurrent_writes)

                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._produce(collection, queue, pbar, stats))
                        for _ in range(self.max_concurrent_requests):
                            tg.create_task(self._consume(collection, queue, write_semaphore, pbar, stats))
                except ExceptionGroup as eg:
                    # the first failure cancels the other tasks, so it is the one worth reporting
                    raise eg.exceptions[0]

                pbar.close()
                print(f"Pipeline finished. Embedded {stats.embedded} records in this run "
                      f"({stats.already_filled} already had the vector, "
                      f"{stats.empty} with empty input).")
        finally:
            if pbar is not None:
                pbar.close()
            await self.embedder.close()
            print("Weaviate connection closed.")

    async def _with_retries(self, operation: Callable[[], Awaitable[Any]], description: str) -> Any:
        """Run a database operation, retrying it in case of failure.

        Args:
            operation: Function creating the awaitable to run (called again for each attempt).
            description: Description of the operation for messages.

        Returns:
            Result of the operation.
        """
        retries = 0
        while True:
            try:
                return await operation()
            except Exception as e:
                if retries >= self.max_retries:
                    print(f"\n[Error] {description} failed after {self.max_retries} retries.")
                    raise e
                retries += 1
                print(f"\n[Warning] {description} failed: {e}. Retrying in {self.retry_delay}s... (Attempt {retries}/{self.max_retries})")
                await asyncio.sleep(self.retry_delay)

    async def _produce(self, collection, queue: asyncio.Queue, pbar: tqdm, stats: PipelineStats) -> None:
        """Scan the whole collection with a cursor and enqueue batches of records without the vector."""
        max_rec = self.max_records or 0
        enqueued = 0
        pending_uuids, pending_texts = [], []
        last_uuid = None

        while max_rec <= 0 or enqueued < max_rec:
            response = await self._with_retries(
                lambda: collection.query.fetch_objects(
                    limit=self.scan_batch_size,
                    after=last_uuid,
                    include_vector=[self.vector_name],
                    return_properties=self.return_properties
                ),
                f"Scanning records after {last_uuid}"
            )

            if not response.objects:
                break

            last_uuid = response.objects[-1].uuid
            stats.scanned += len(response.objects)
            done_without_embedding = 0

            for obj in response.objects:
                if max_rec > 0 and enqueued >= max_rec:
                    break

                if (obj.vector or {}).get(self.vector_name):
                    stats.already_filled += 1
                    done_without_embedding += 1
                    continue

                database_record = {k: (v if v is not None else "") for k, v in obj.properties.items()}
                text = self.embedder.render(database_record)
                if not text.strip():
                    stats.empty += 1
                    done_without_embedding += 1
                    continue

                pending_uuids.append(obj.uuid)
                pending_texts.append(text)
                enqueued += 1

                if len(pending_uuids) >= self.embed_batch_size:
                    await self._enqueue(queue, pending_uuids, pending_texts, pbar, stats)
                    pending_uuids, pending_texts = [], []

            pbar.update(done_without_embedding)
            pbar.set_postfix(stats.postfix())

        if pending_uuids:
            await self._enqueue(queue, pending_uuids, pending_texts, pbar, stats)

        for _ in range(self.max_concurrent_requests):
            await queue.put(None)

    async def _enqueue(self, queue: asyncio.Queue, uuids: list, texts: list[str], pbar: tqdm, stats: PipelineStats) -> None:
        """Put a batch of records to the queue for embedding (waits when the queue is full)."""
        await queue.put((uuids, texts))
        stats.queued += len(uuids)
        pbar.set_postfix(stats.postfix(), refresh=False)

    async def _consume(self, collection, queue: asyncio.Queue, write_semaphore: asyncio.Semaphore, pbar: tqdm, stats: PipelineStats) -> None:
        """Embed enqueued batches and write the embeddings to the database."""
        while True:
            item = await queue.get()
            if item is None:
                break

            uuids, texts = item
            stats.queued -= len(uuids)
            stats.embedding += len(uuids)
            pbar.set_postfix(stats.postfix(), refresh=False)

            embeddings = await self.embedder.embed_batch(texts)

            stats.embedding -= len(uuids)
            stats.writing += len(uuids)
            pbar.set_postfix(stats.postfix(), refresh=False)

            if stats.dimension is None:
                stats.dimension = len(embeddings[0])
                tqdm.write(f"Embedding dimension: {stats.dimension}")

            await asyncio.gather(*(
                self._write_vector(collection, uuid, embedding, write_semaphore)
                for uuid, embedding in zip(uuids, embeddings)
            ))

            stats.writing -= len(uuids)
            stats.embedded += len(uuids)
            pbar.update(len(uuids))
            pbar.set_postfix(stats.postfix())

    async def _write_vector(self, collection, uuid, embedding: list[float], write_semaphore: asyncio.Semaphore) -> None:
        """Write the named vector of a single record (PATCH, other properties and vectors are kept)."""
        async with write_semaphore:
            await self._with_retries(
                lambda: collection.data.update(uuid=uuid, vector={self.vector_name: embedding}),
                f"Database update for record {uuid}"
            )
