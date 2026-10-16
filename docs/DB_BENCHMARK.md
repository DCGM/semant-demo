# Weaviate inventory and benchmark tool

`python -m semant_demo.maintenance.db_benchmark` is a small, read-only command-line tool for
recording the state of a Weaviate deployment and measuring the application's read paths at
low concurrency (#374). Use it again before and after a Weaviate upgrade, a quantization or
index change, a vector-index rebuild or the introduction of named vectors, and compare the
runs. The first production baseline and its findings are in
[WEAVIATE_AUDIT_2026-10.md](WEAVIATE_AUDIT_2026-10.md).

It is not a load-test framework, a monitor or a CI gate. Run it from `semant_demo_backend/`
with the repository `.venv`, like the [maintenance commands](DATA_MAINTENANCE.md); the module
docstring and `--help` list every option.

## Safety

- It only sends queries, aggregates and object reads. It never writes, restarts a service,
  flushes a cache or changes a schema or index.
- A profile above the production-safe limits (concurrency 10, 25 request starts per second,
  200 requests or 60 s per scenario and level, 60 s timeout, 500 sampled chunks) is refused
  unless `--allow-heavy` is given. Use that only on a staging instance or a snapshot. Rates,
  request counts, durations, timeouts and concurrency levels must be positive (a zero rate
  would disable pacing), and unknown `--scenarios` are refused. No request starts after a
  point's time cap. Cold-cache and restart experiments are out of scope for the tool; do them
  on a snapshot.
- Query inputs are sampled from the target at run time with a fixed seed. Query vectors are
  the stored vectors of sampled chunks, so no embedding service is called and embedding time
  is not part of any timing. BM25 text is the two longest words of the same chunk.
- Results hold no query texts, vectors or object ids: only 12-character **keyed** hashes of
  result ids and query fingerprints (for overlap between runs), counts, timings and
  configuration. The key is read from `--id-key-file` (default
  `~/.config/semant-demo/db-benchmark-id-key`, created with a random key on first use; never
  commit or publish it). An unkeyed hash of an id can be matched by anyone who can list the
  ids; a keyed one cannot. Only runs made with the same key can be compared for overlap; the
  results record a `key_id` that identifies the key without revealing it.
- Results record no host paths, cgroup paths, container ids or backup ids. Container
  environment variables (which may hold credentials) are never read. Still review a result
  (JSON and Markdown) before publishing it.
- Point it at the endpoint you mean: `WEAVIATE_HOST` / `WEAVIATE_REST_PORT` /
  `WEAVIATE_GRPC_PORT`, or `--host` / `--rest-port` / `--grpc-port`. Running against the
  shared test or production Weaviate needs authorization for the task, even though it is
  read-only.

## Inventory

```bash
python -m semant_demo.maintenance.db_benchmark inventory \
  --container semant-demo-weaviate-1 \
  --data-dir <host data dir> --container-files \
  --backup-dir <host backup dir> \
  --out results/inventory
```

Writes `results/inventory.json` and `results/inventory.md` with:

- Weaviate version, nodes, shards (object counts, indexing status, `compressed`), aliases;
- per collection: vector indexes (type, distance, HNSW parameters, enabled quantizer), vector
  dimensions per named vector, inverted-index settings (BlockMax WAND), searchable,
  filterable and range-indexed properties, references, sharding and replication;
- **vector index coverage**: for `--coverage-sample` random chunks (default 100), whether a
  vector query with the chunk's own vector returns it in the top `--coverage-k` (10), and
  whether a vector query restricted to its own id finds it. A healthy index finds nearly all
  of them; a low rate means vectors are missing from the index (see the 2026-10 audit);
- disk use per collection directory, shard component and LSM bucket, with the largest segments
  of the object and compressed-vector buckets, and free space of the data and backup
  filesystems;
- memory: host total/available, page cache, swap, ZFS ARC size and maximum (`arcstats`; Linux
  counts the ARC as used, not available), memory pressure (PSI), and the container's cgroup
  memory (anon vs. file cache, peak, limit, OOM kills);
- log signals: counts of warning/error entries by action and message (numbers masked, no
  payload fields), process starts and lines mentioning a panic;
- backups listed by the `backup-filesystem` module (start time, status, size; not their ids).

Each source is optional; what cannot be read is reported as unavailable, never as zero:

| Option | Source | Fallback when it is not accessible |
|---|---|---|
| `--container NAME` | `docker inspect` (limits, start, restarts) and the cgroup v2 files | `--cgroup /sys/fs/cgroup/system.slice/docker-<id>.scope` |
| `--data-dir PATH` | `os.walk` and `statvfs` of the data directory | `--container-files` (`docker exec NAME find -xdev …`: mounts below the data path, such as a backup directory, are not counted) or `--files-list FILE` with `<bytes> <path>` lines |
| logs | `docker logs NAME [--since …]` | `--log-file FILE` (a saved log); `--logs-since none` skips it |

The data directory is usually owned by root; `--container-files` lists it from inside the
container instead. Disk attribution stops at LSM buckets: how much of the `objects` bucket is
vectors versus properties, or superseded versions awaiting compaction, is estimated in the
report, not measured.

## Benchmark run

```bash
python -m semant_demo.maintenance.db_benchmark run --profile baseline \
  --container semant-demo-weaviate-1 --out results/baseline
```

Profiles are YAML files in `semant_demo/configs/db_benchmark/` (a name) or any path:

- `baseline` — the production-safe default: 1, 5 and 10 concurrent requests, at most 20
  request starts per second, 40 requests or 20 s per scenario and level, 5 warm-up requests
  per scenario, 30 s timeout, 100 sampled chunks. It takes 5–15 minutes.
- `smoke` — every scenario kind a few times at concurrency 1 and 2 (seconds; used by the
  integration test).

Override the top-level limits with `--concurrency 1,5`, `--requests`, `--max-seconds`,
`--timeout`, `--max-qps`, `--seed` and `--level-inputs`, and select scenarios with
`--scenarios a,b`.

Scenario kinds (`layer` in the report):

| Kind | Layer | What it runs |
|---|---|---|
| `search` | adapter | `ChunkSearchRepository.search` — the search page and RAG retrieval: BM25, vector or hybrid, the document reference and its properties returned, optional `filter`: `year_range` (chunk `yearIssued`), `language`, `document_type` (through the document reference), `tag` (chunk tag references), `user_collection` (the last two query from a chunk inside the value) |
| `direct` | direct | the same query call without references and with one property, to separate the database search cost from reference expansion |
| `context` | adapter | `DocumentRepository.read_adjacent_chunks` before and after a chunk |
| `document_view` | adapter | `DocumentRepository.read_chunks` — all chunks of a document (documents above `max_document_chunks` are skipped) |
| `aggregate` | adapter | the corpus overview aggregates (`features/analytics`), uncached |
| `mixed` | mixed | requests drawn in turn from the named scenarios (an interleaved user mix) |
| `self_recall` | direct | each sampled chunk queried with its own vector; `non-empty` counts the chunks found in the top `limit` |

Each scenario first runs its warm-up requests on inputs from the end of the sample. Then, with
the default `level_inputs: same`, every concurrency level runs the **same** inputs (the first
`requests_per_point` of the sample, in the same order), so the levels differ only in
concurrency. The first level is the first timed execution of these inputs; later levels repeat
queries the store has just served, so they measure a **warm** cache (on production in 2026-10,
a fresh hybrid query took about 110 ms and the same query repeated about 10 ms). With
`level_inputs: disjoint` (`--level-inputs disjoint`), each level runs the next
`requests_per_point` inputs of the same sample instead: every level runs fresh queries drawn the
same way, but not identical ones. Sample at least levels × requests + warm-up inputs (the
report notes when inputs repeat). Use `same` to compare runs and `disjoint` to see the
concurrency cost of fresh queries; in both cases compare a level with the same level of another
run.

Tag and user-collection filters use only values that match at least one chunk (up to 1000
candidates are checked while sampling; `filter_values_checked` in the inputs), and the query
of such a search is taken from a chunk inside the tag or collection (one chunk per value), as
when a user searches within it; a random chunk's words rarely occur in the one or two chunks a
tag holds. The report flags any scenario in which no request returned a result, because such
timings measure an empty search.

Every request is timed on the client (wall time of the call, including gRPC and result
mapping). The report gives per scenario and level: requests, non-empty results, errors and
timeouts, p50/p95/p99 (p99 from 100 samples)/max latency, completed requests per second,
and, when a cgroup is available, Weaviate CPU (average cores), maximum anonymous memory,
bytes read from disk and the host I/O pressure. Requests per second is limited by the pacing,
so it is not a capacity figure.

To add a workload, copy a profile and change its scenarios, inputs (`year_ranges`,
`languages`, `document_types`) or `collections` (other collection names or aliases). For a
store with several named vectors, `--target-vector NAME` selects the one the `direct` and
`self_recall` scenarios and the coverage check query (the adapter queries whatever the
application queries). A named vector that the sampled chunks do not have is an error; it is
never replaced by another vector. Without the option, the first vector by name is used and the
run notes which vectors exist.

## Compare runs

```bash
python -m semant_demo.maintenance.db_benchmark compare results/before.json results/after.json --out results/compare
python -m semant_demo.maintenance.db_benchmark report results/after.json   # re-render the Markdown and summary
```

The comparison lists both setups (endpoint, Weaviate version, chunk class, object count,
vector index and quantizer, profile fingerprint, git commit) and flags differences, then gives
p50/p95 and errors side by side with their change. For the first concurrency level it gives
the mean overlap of the top-k result lists of identical queries (same sampled chunk and filter
value). Overlap is only meaningful when the query sets match: same profile and seed on the
same data, and the same id hash key (otherwise it is not computed). After an index or
quantization change, a lower overlap means the results changed; with `self_recall`, it shows
whether recall held.

## Results and archiving

`run` writes `<out>.json` (everything, including the per-query result hashes that `compare`
needs for overlap), `<out>.md` and `<out>.summary.json` (the same without the per-query
hashes, a few tens of KiB). Commit the Markdown and the summary of a run that a document
relies on; do not commit the full JSON of every run. Keep the full JSON of a reference run (such
as a baseline before an index change) as an immutable, dated file outside the repository, with
its SHA-256 checksum recorded where it is cited, and never overwrite it: a new measurement gets
a new dated file. The 2026-10 audit archive is described in
[WEAVIATE_AUDIT_2026-10.md](WEAVIATE_AUDIT_2026-10.md#saved-results).

```bash
python -m semant_demo.maintenance.db_benchmark sanitize results/run.json --out public/run-2026-10-16
```

`sanitize` writes a copy for publication: version 1 results (unkeyed hashes, cgroup paths,
backup ids) are converted with the key of `--id-key-file`, so they can be compared with later
runs made with the same key. Archives may be public: review them before uploading.

## Limitations

- Query vectors are document vectors, not embedded user questions; they find their own
  neighbourhood easily. For real query embeddings, run a profile against a prepared store or
  compare `self_recall` and overlap rather than absolute relevance.
- Timings include the Python client; the tool is single-process asyncio.
- Results depend on what else uses the host (page cache, other services). Record the context of
  each run and compare runs made under similar conditions.
- Cold-cache behaviour is not produced by the tool (it does not drop caches). The first
  requests of a scenario (warm-up excluded) show some of it.
