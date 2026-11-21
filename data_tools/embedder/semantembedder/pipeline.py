import asyncio
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue, ConfigurableSubclassFactory
from tqdm import tqdm
from weaviate.classes.query import Filter

from .db import (HAVE_VECTOR, check_grpc, ensure_named_vector_exists, get_async_client, have_vector_problem,
                 named_vector_exists)
# Import embedders to register their subclasses for ConfigurableSubclassFactory
from .embedders import Embedder, VLLMEmbedder


@dataclass
class PipelineStats:
    selected: int = 0  # records read whose haveVector lacks the vector's name
    scanned: int = 0  # records whose id and haveVector were read by the cursor (0 unless it fell back to it)
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

    A run reads again and again the first page of the records whose list lacks the name
    (``contains_none``), leaving out by id those it has already read and not written: the records being
    embedded or written, and those with an empty input. A record written leaves the selection, so the
    pipeline can be interrupted at any time and the next run continues with what is left. Weaviate's
    cursor cannot be combined with a filter, and keyset paging (sorted by ``_id``) costs minutes a page
    when most records are selected (measured in #816). When more than ``max_excluded`` ids would be left
    out (many empty inputs, or a check, which writes nothing), the run reads the rest of the collection
    with the cursor instead, only the ids and ``haveVector``, and the records lacking the name by id.

    A selected record that already stores the vector only gets the name; a record with an empty input is
    skipped and stays selected. The collection must declare ``haveVector``
    (``db.HAVE_VECTOR_DECLARATION``); a run never declares it. One run per collection at a time: a write
    replaces the whole list.
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
    max_excluded: int = ConfigurableValue(
        desc="Maximum number of ids left out of the selection query (records read and not yet written, "
             "or with an empty input); above it the rest is read with the cursor (ids and haveVector of "
             "every record)",
        user_default=5000,
        validator=lambda x: isinstance(x, int) and x >= 0,
        voluntary=True
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
                    # the schema calls use REST: check gRPC before the schema changes
                    await check_grpc(client, self.collection, self.weaviate_host, self.weaviate_grpc_port)
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
                pbar = tqdm(desc="Embedding records")

                queue: asyncio.Queue = asyncio.Queue(maxsize=self.max_concurrent_requests * 2)
                write_semaphore = asyncio.Semaphore(self.max_concurrent_writes)
                excluded: set = set()  # read and not written: being embedded or written, or an empty input

                try:
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._produce(collection, queue, write_semaphore, pbar, stats, excluded))
                        for _ in range(self.max_concurrent_requests):
                            tg.create_task(self._consume(collection, queue, write_semaphore, pbar, stats, excluded))
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

        It reads the records lacking the name like a run, but since it writes nothing, each page read is
        left out of the next query, so beyond ``max_excluded`` records it reads the rest with the cursor
        (the id and ``haveVector`` of every record). The cursor reads no record twice, so the ids it
        yields are not kept: the memory stays bounded by ``max_excluded`` and a page. ``max_records`` is
        not applied: the counts cover the whole selection.
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
            excluded: set = set()  # nothing is written, so every record read is left out of the next query
            async for objects in self._select(collection, excluded, stats, include_vector=exists):
                stats.selected += len(objects)
                from_cursor = stats.scanned > 0  # _scan counts its page before yielding it
                for obj in objects:
                    if not from_cursor:
                        excluded.add(obj.uuid)
                    if self._input_of(obj, stats) is not None:
                        stats.missing += 1
        print(f"Check finished. {stats.selected} records lack '{self.vector_name}' in {HAVE_VECTOR}: "
              f"{stats.missing} a run would embed, {stats.already_stored} already store the vector "
              f"(a run only adds the name), {stats.empty} with empty input.")
        if self.max_records and stats.missing > self.max_records:
            print(f"A run embeds at most max_records={self.max_records} of them.")
        return stats

    def _lacks_name(self, listed: Optional[list]) -> bool:
        """Whether a ``haveVector`` list (None when absent or null) lacks the vector's name, as
        ``contains_none([name])`` selects it."""
        return self.vector_name not in (listed or [])

    def _returned_properties(self) -> Optional[list]:
        """``return_properties`` with ``haveVector``, whose list a write extends (None: all properties)."""
        if self.return_properties is None:
            return None
        return [*self.return_properties, *([] if HAVE_VECTOR in self.return_properties else [HAVE_VECTOR])]

    def _include_vector(self, include_vector: bool):
        return [self.vector_name] if include_vector else False

    async def _select(self, collection, excluded: set, stats: PipelineStats, include_vector: bool = True,
                      done: Callable[[], bool] = lambda: False) -> AsyncIterator[list]:
        """Yield pages of the records lacking the name, with their properties (and the target vector with
        ``include_vector``), until ``done()`` or none is left.

        Each page is the first ``scan_batch_size`` records of ``contains_none([name])`` without the ids in
        ``excluded``, which the caller keeps: a record read and not yet written must be in it before the
        next page is requested, or it is read again. When ``excluded`` grows beyond ``max_excluded``, the
        rest is read by ``_scan`` (the cursor)."""
        lacking = Filter.by_property(HAVE_VECTOR).contains_none([self.vector_name])
        while not done():
            if len(excluded) > self.max_excluded:
                tqdm.write(f"More than max_excluded={self.max_excluded} records read and not written "
                           f"(empty inputs, or a check); reading the rest with the cursor.")
                async for objects in self._scan(collection, excluded, stats, include_vector, done):
                    yield objects
                return
            filters = lacking & Filter.by_id().contains_none(list(excluded)) if excluded else lacking
            response = await self._with_retries(
                lambda: collection.query.fetch_objects(
                    filters=filters, limit=self.scan_batch_size,
                    include_vector=self._include_vector(include_vector),
                    return_properties=self._returned_properties()),
                f"Reading the records lacking '{self.vector_name}'"
            )
            if not response.objects:
                return
            yield response.objects

    async def _scan(self, collection, excluded: set, stats: PipelineStats, include_vector: bool,
                    done: Callable[[], bool]) -> AsyncIterator[list]:
        """Read the collection with a cursor, ``scan_batch_size`` ids and ``haveVector`` lists per request,
        until ``done()``; yield the records of each page lacking the name and not in ``excluded``, read
        again by id with their properties (and the target vector with ``include_vector``).

        The cursor reads no text and no vectors of the records listing the name. The second read takes
        the current list, so a record listed meanwhile is left out."""
        last_uuid = None
        while not done():
            response = await self._with_retries(
                lambda: collection.query.fetch_objects(
                    limit=self.scan_batch_size, after=last_uuid, return_properties=[HAVE_VECTOR]),
                f"Scanning records after {last_uuid}"
            )
            if not response.objects:
                return
            stats.scanned += len(response.objects)
            last_uuid = response.objects[-1].uuid
            ids = [obj.uuid for obj in response.objects
                   if obj.uuid not in excluded and self._lacks_name(obj.properties.get(HAVE_VECTOR))]
            if not ids:
                continue
            selected = (await self._with_retries(
                lambda: collection.query.fetch_objects(
                    filters=Filter.by_id().contains_any(ids), limit=len(ids),
                    include_vector=self._include_vector(include_vector),
                    return_properties=self._returned_properties()),
                f"Reading the {len(ids)} selected records after {last_uuid}"
            )).objects
            objects = [obj for obj in selected if self._lacks_name(obj.properties.get(HAVE_VECTOR))]
            if objects:
                yield objects

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
                       stats: PipelineStats, excluded: set) -> None:
        """Read the selected records and enqueue batches of those to embed; records that already store
        the vector get only its name in ``haveVector`` before the next page is read. The records enqueued
        and those with an empty input are added to ``excluded``; ``_consume`` removes a record once
        written."""
        max_rec = self.max_records or 0
        enqueued = 0
        pending_uuids, pending_texts, pending_listed = [], [], []

        async for objects in self._select(collection, excluded, stats,
                                          done=lambda: max_rec > 0 and enqueued >= max_rec):
            stats.selected += len(objects)
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
                    else:  # an empty input stays selected
                        excluded.add(obj.uuid)
                    done_without_embedding += 1
                    continue

                excluded.add(obj.uuid)
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

    async def _consume(self, collection, queue: asyncio.Queue, write_semaphore: asyncio.Semaphore, pbar: tqdm,
                       stats: PipelineStats, excluded: set) -> None:
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

            excluded.difference_update(uuids)  # written: they left the selection
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
