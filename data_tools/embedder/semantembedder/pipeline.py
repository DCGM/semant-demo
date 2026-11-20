import asyncio
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue, ConfigurableSubclassFactory
from tqdm import tqdm
from weaviate.classes.query import Filter, Sort

from .db import HAVE_VECTOR, get_async_client, ensure_named_vector_exists, have_vector_problem, named_vector_exists
# Import embedders to register their subclasses for ConfigurableSubclassFactory
from .embedders import Embedder, VLLMEmbedder


@dataclass
class PipelineStats:
    scanned: int = 0  # selected records read (their haveVector lacks the vector's name)
    already_stored: int = 0  # selected records that store the vector: a run only adds its name to haveVector
    empty: int = 0  # selected records whose rendered input text is empty (not embedded, stay selected)
    embedded: int = 0  # records whose vector (and name in haveVector) was written in this run
    missing: int = 0  # check only: selected records a run would embed
    refused: Optional[str] = None  # check only: why a run would be refused before embedding anything
    dimension: Optional[int] = None

    # current state of the records in the pipeline (for monitoring of utilization and bottlenecks)
    queued: int = 0  # records waiting in the queue for an embedding request
    embedding: int = 0  # records in running embedding requests
    writing: int = 0  # records with embeddings that are being written to the database

    def postfix(self) -> dict:
        return {
            "embedded": self.embedded,
            "stored": self.already_stored,
            "empty": self.empty,
            "queued": self.queued,
            "embedding": self.embedding,
            "writing": self.writing,
        }


class EmbeddingPipeline(ConfigurableMixin, CreatableMixin):
    """A fully configurable pipeline that embeds the Weaviate records lacking the given named vector and
    writes each embedding back as that named vector, together with the vector's name in the record's
    ``haveVector`` list (#816).

    A run reads only the records whose ``haveVector`` lacks the name (``contains_none``), in id order
    (keyset paging: Weaviate's cursor cannot be combined with a filter, and offset paging stops at
    ``QUERY_MAXIMUM_RESULTS``). A record written leaves the selection, so the pipeline can be interrupted
    at any time and the next run continues with what is left. A selected record that already stores the
    vector only gets the name; a record with an empty input is skipped and stays selected. The collection
    must declare ``haveVector`` (``db.HAVE_VECTOR_DECLARATION``); a run never declares it. One run per
    collection at a time: a write replaces the whole list.
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
        desc="Name of the named vector the embeddings are written to. Letters, digits and _ only, "
             "not starting with a digit: Weaviate builds GraphQL names from it, and a name with '-' "
             "breaks GraphQL for the whole instance",
        user_default="my_embedder",
        validator=lambda x: isinstance(x, str) and re.fullmatch(r"[_A-Za-z][_A-Za-z0-9]*", x) is not None
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

    async def run_async(self) -> PipelineStats:
        """Run the embedding pipeline in the current event loop; returns its counts."""
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
                exists = await named_vector_exists(client, self.collection, self.vector_name)
                problem = await have_vector_problem(client, self.collection)
                if problem:
                    raise ValueError(problem)
                if not exists and self.create_vector:
                    await ensure_named_vector_exists(
                        client=client,
                        collection_name=self.collection,
                        vector_name=self.vector_name,
                        index_type=self.vector_index_type,
                        distance_metric=self.distance_metric
                    )
                elif not exists:
                    raise ValueError(f"Named vector '{self.vector_name}' does not exist in collection '{self.collection}' and create_vector is disabled.")

                collection = client.collections.use(self.collection)

                print(f"Starting embedding pipeline on collection '{self.collection}' (vector '{self.vector_name}')...")
                # Only the progress bar's total: a count taken right after a bulk write can be off (#805).
                total_count = (await collection.aggregate.over_all(filters=self._selection(),
                                                                   total_count=True)).total_count
                pbar = tqdm(total=total_count, desc="Embedding records")

                queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_concurrent_requests * 2)
                write_semaphore = asyncio.Semaphore(self.max_concurrent_writes)

                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._produce(collection, queue, write_semaphore, pbar, stats))
                        for _ in range(self.max_concurrent_requests):
                            tg.create_task(self._consume(collection, queue, write_semaphore, pbar, stats))
                except ExceptionGroup as eg:
                    # the first failure cancels the other tasks, so it is the one worth reporting
                    raise eg.exceptions[0]

                pbar.close()
                print(f"Pipeline finished. Embedded {stats.embedded} records in this run "
                      f"({stats.already_stored} already stored the vector and got only its name in {HAVE_VECTOR}, "
                      f"{stats.empty} with empty input).")
                return stats
        finally:
            if pbar is not None:
                pbar.close()
            await self.embedder.close()
            print("Weaviate connection closed.")

    def check(self) -> PipelineStats:
        """Count what a run would do, without embedding or writing anything."""
        return asyncio.run(self.check_async())

    async def check_async(self) -> PipelineStats:
        """Count what a run would do; read-only (no schema change, no embedding requests, no writes).

        When a run would be refused (``haveVector`` missing or declared otherwise, or the vector missing and
        ``create_vector`` disabled), it returns at once with ``refused`` saying why, without reading any
        record: the counts stay 0.

        It reads the records a run would select (``haveVector`` lacking the name), like a run, and none of
        the others. ``max_records`` is not applied: the counts cover the whole selection.
        """
        stats = PipelineStats()
        async with get_async_client(
            host=self.weaviate_host,
            port=self.weaviate_port,
            grpc_port=self.weaviate_grpc_port,
            headers=self.weaviate_headers,
            api_key=self.weaviate_api_key
        ) as client:
            exists = await named_vector_exists(client, self.collection, self.vector_name)
            problem = await have_vector_problem(client, self.collection)
            if problem:
                stats.refused = problem
                print(f"{problem} A run would be refused.")
                return stats
            if not exists:
                missing_vector = f"Named vector '{self.vector_name}' does not exist in collection '{self.collection}'"
                if self.create_vector:
                    print(f"{missing_vector}; a run would create it (create_vector).")
                else:
                    stats.refused = f"{missing_vector} and create_vector is disabled."
                    print(f"{missing_vector}; a run would be refused (create_vector is disabled).")
                    return stats
            collection = client.collections.use(self.collection)
            print(f"Checking collection '{self.collection}' (vector '{self.vector_name}'), nothing is written...")
            async for objects in self._scan(collection, include_vector=exists):
                stats.scanned += len(objects)
                for obj in objects:
                    if self._input_of(obj, stats) is not None:
                        stats.missing += 1
        print(f"Check finished. {stats.scanned} records lack '{self.vector_name}' in {HAVE_VECTOR}: "
              f"{stats.missing} a run would embed, {stats.already_stored} already store the vector "
              f"(a run only adds the name), {stats.empty} with empty input.")
        if self.max_records and stats.missing > self.max_records:
            print(f"A run embeds at most max_records={self.max_records} of them.")
        return stats

    def _selection(self) -> Filter:
        """The records whose ``haveVector`` lacks the vector's name (also those without a list)."""
        return Filter.by_property(HAVE_VECTOR).contains_none([self.vector_name])

    def _returned_properties(self) -> Optional[list]:
        """``return_properties`` with ``haveVector``, whose list a write extends (None: all properties)."""
        if self.return_properties is None:
            return None
        return [*self.return_properties, *([] if HAVE_VECTOR in self.return_properties else [HAVE_VECTOR])]

    async def _scan(self, collection, include_vector: bool = True,
                    done: Callable[[], bool] = lambda: False) -> AsyncIterator[list]:
        """Read the selected records in id order, ``scan_batch_size`` per request, until ``done()``.

        Keyset paging: each page is the selection after the last id read, sorted by id (without the sort
        the pages would skip and repeat records). Records written meanwhile have smaller ids, so reading
        ahead of the writes reads nothing twice, and records left selected (empty input) are passed."""
        last_uuid = None
        while not done():
            filters = self._selection()
            if last_uuid is not None:
                filters = filters & Filter.by_property("_id").greater_than(str(last_uuid))
            response = await self._with_retries(
                lambda: collection.query.fetch_objects(
                    limit=self.scan_batch_size,
                    filters=filters,
                    sort=Sort.by_property("_id"),
                    include_vector=[self.vector_name] if include_vector else False,
                    return_properties=self._returned_properties()
                ),
                f"Reading the selected records after {last_uuid}"
            )
            if not response.objects:
                return
            last_uuid = response.objects[-1].uuid
            yield response.objects

    def _input_of(self, obj, stats: PipelineStats) -> Optional[str]:
        """The text to embed for a selected record, or None (counted) when it already stores the vector
        or has an empty input."""
        if (obj.vector or {}).get(self.vector_name):
            stats.already_stored += 1
            return None
        database_record = {k: (v if v is not None else "") for k, v in obj.properties.items() if k != HAVE_VECTOR}
        text = self.embedder.render(database_record)
        if not text.strip():
            stats.empty += 1
            return None
        return text

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

    async def _produce(self, collection, queue: asyncio.Queue, write_semaphore: asyncio.Semaphore, pbar: tqdm,
                       stats: PipelineStats) -> None:
        """Read the selected records and enqueue batches of those to embed; records that already store
        the vector get only its name in ``haveVector``."""
        max_rec = self.max_records or 0
        enqueued = 0
        pending_uuids, pending_texts, pending_listed = [], [], []

        async for objects in self._scan(collection, done=lambda: max_rec > 0 and enqueued >= max_rec):
            stats.scanned += len(objects)
            done_without_embedding = 0
            name_only = []

            for obj in objects:
                if max_rec > 0 and enqueued >= max_rec:
                    break

                listed = obj.properties.get(HAVE_VECTOR)
                stored_before = stats.already_stored
                text = self._input_of(obj, stats)
                if text is None:
                    if stats.already_stored > stored_before:
                        name_only.append((obj.uuid, listed))
                    done_without_embedding += 1
                    continue

                pending_uuids.append(obj.uuid)
                pending_texts.append(text)
                pending_listed.append(listed)
                enqueued += 1

                if len(pending_uuids) >= self.embed_batch_size:
                    await self._enqueue(queue, pending_uuids, pending_texts, pending_listed, pbar, stats)
                    pending_uuids, pending_texts, pending_listed = [], [], []

            await asyncio.gather(*(self._write(collection, uuid, listed, None, write_semaphore)
                                   for uuid, listed in name_only))
            pbar.update(done_without_embedding)
            pbar.set_postfix(stats.postfix())

        if pending_uuids:
            await self._enqueue(queue, pending_uuids, pending_texts, pending_listed, pbar, stats)

        for _ in range(self.max_concurrent_requests):
            await queue.put(None)

    async def _enqueue(self, queue: asyncio.Queue, uuids: list, texts: list[str], listed: list, pbar: tqdm,
                       stats: PipelineStats) -> None:
        """Put a batch of records (with their ``haveVector`` lists) to the queue for embedding (waits when
        the queue is full)."""
        await queue.put((uuids, texts, listed))
        stats.queued += len(uuids)
        pbar.set_postfix(stats.postfix(), refresh=False)

    async def _consume(self, collection, queue: asyncio.Queue, write_semaphore: asyncio.Semaphore, pbar: tqdm, stats: PipelineStats) -> None:
        """Embed enqueued batches and write the embeddings to the database."""
        while True:
            item = await queue.get()
            if item is None:
                break

            uuids, texts, listed = item
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
                self._write(collection, uuid, names, embedding, write_semaphore)
                for uuid, names, embedding in zip(uuids, listed, embeddings)
            ))

            stats.writing -= len(uuids)
            stats.embedded += len(uuids)
            pbar.update(len(uuids))
            pbar.set_postfix(stats.postfix())

    async def _write(self, collection, uuid, listed: Optional[list], embedding: Optional[list[float]],
                     write_semaphore: asyncio.Semaphore) -> None:
        """Add the vector's name to a record's ``haveVector`` and write the vector with it, or only the
        name when ``embedding`` is None: one PATCH, other properties, vectors and listed names are kept.

        ``listed`` is the list as read: ``None`` (absent or null) counts as ``[]``, which Weaviate reads
        back as ``[]`` but treats alike in the selection."""
        names = [*(listed or []), self.vector_name]
        vector = None if embedding is None else {self.vector_name: embedding}
        async with write_semaphore:
            await self._with_retries(
                lambda: collection.data.update(uuid=uuid, properties={HAVE_VECTOR: names}, vector=vector),
                f"Database update for record {uuid}"
            )
