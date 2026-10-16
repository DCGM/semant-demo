# Production Weaviate audit, 2026-10-16 (#374)

A measured, read-only baseline of the production Weaviate: what it holds, what it costs in disk
and memory, how the application's read paths perform at 1–10 concurrent requests, which of the
problems in [#149](https://github.com/DCGM/semant-demo/issues/149) remain, and what one or two
named vectors would need. Measured on 2026-10-16 between 09:40 and 10:20 UTC with light user
traffic, and again between 12:41 and 13:10 UTC after review corrections to the tool (see
[Saved results](#saved-results)). Nothing was written to the store, no index or setting was
changed and no service was restarted. Statements are marked as measurements, estimates or
explanations where the difference matters.

The tool is described in [DB_BENCHMARK.md](DB_BENCHMARK.md).

## Conclusions

1. **Fix now: the chunk vector index covers an estimated 2% of the chunks.** Measured: for 300
   random chunks, a vector query with the chunk's own vector found it 2 times, and a vector
   query restricted to its own id found it 3 times (the same in both inventories; 0/100 in each
   benchmark's `self_recall`). In a healthy index both find nearly all of them; on the test
   store they find all of them. Startup prefilled 198,855 compressed vectors for a highest node
   id of 8,279,234, and the compressed-vector bucket holds about 1.1 GiB where 8.28 M 8-bit RQ
   codes need about 28 GiB. The coverage is an estimate from this sample (about 0.3–2.9% at
   95%), not an exact fraction. Vector search, and the vector half of hybrid search (the default
   search and RAG retrieval), therefore see only a small part of the corpus. BM25 is not
   affected. The restore from a backup without compressed vectors is a plausible but unproven
   explanation; see [Vector index coverage](#vector-index-coverage). Diagnosis and repair are
   tracked in [#375](https://github.com/DCGM/semant-demo/issues/375); this audit changed nothing.
2. **No other blocking performance problem for up to 10 users on the current (incomplete)
   index, with one caveat.** Measured: 4,240 benchmark requests in three runs at 1/5/10
   concurrent requests had no error and no timeout (slowest 4.1 s). BM25, vector, tag and
   collection-filtered searches take 4–30 ms (p95). The expensive path is a **fresh hybrid
   query**: about 120–130 ms, 2–3 CPU-seconds and 1.3–1.5 GB of disk reads per query. With 10
   fresh queries at once that is 0.9–1.1 s p50 / 1.3–1.8 s p95 and 23–26 of the host's 32 cores
   busy. An identical repeated query costs about 10 ms. The cost may be a consequence of the
   missing compressed vectors (distances read from full objects on disk); that is a hypothesis,
   so measure again after the repair before treating it as a separate problem. Chunk context and
   document reads are the second hot spot (0.1–0.5 s p50, up to 4 s): they sort or scan every
   chunk of a document. These runs show that the current deployment stays available at this
   load; they **cannot** establish the latency, CPU or memory of a complete vector index, which
   has to be measured on a rebuilt copy and again after the repair.
3. **The single-host setup is adequate for an early deployment of up to 10 users, but memory
   headroom after the rebuild is not.** Weaviate now uses about 4 GiB of anonymous memory because
   the index holds so few vectors. A complete 8-bit RQ index needs about 28 GiB of codes plus
   graph and working memory (about 35 GiB anonymous memory, an estimate to be measured on a
   rebuilt copy). The host had 14–14.5 GiB `MemAvailable`: about 83–86 GiB is ZFS ARC (measured
   from `arcstats`, see [Memory](#memory)), plus Elasticsearch (35 GiB), another Weaviate
   (17.5 GiB) and other services. The ARC is reclaimable but competes with the page cache, and
   there is no swap. Reserve the memory (for example cap `zfs_arc_max`; a host decision) before
   the rebuild.
4. **Disk is not the constraint now: 964 GiB are free on the data filesystem.** The chunk
   directory is 316 GiB, of which an estimated 125 GiB are superseded object versions from the
   2026-10-13 `chunk_year --write` pass, awaiting LSM compaction (estimated from segment sizes;
   to be confirmed after compaction). Quantization reduces memory,
   not disk: each object keeps its float32 vector (14 KiB of its 16 KiB), which is why the RQ
   change in #149 did not shrink the directory. The backup ZFS pool is 98% full (1.3 TiB free
   of 43 TiB; eight Weaviate backups).
5. **Named vectors: fix the index first.** Measured against the current baseline, one more
   1024-dimensional vector costs about 32 GiB of disk in the objects, about 8 GiB of RAM with
   8-bit RQ (1 GiB with 1-bit/BQ), up to 4 GiB of graph, and, when existing objects are updated
   to add it, one more full copy of the objects bucket (about 130 GiB) until compaction. See
   [Named vectors](#named-vectors).

## Deployment

| Item | Value |
|---|---|
| Weaviate | 1.34.4 (`275e438`), single node `node1`, image `cr.weaviate.io/semitechnologies/weaviate:1.34.4`, container `semant-demo-weaviate-1` up since 2026-09-21 22:21 UTC, restart count 0 |
| Container limits | memory 98 GiB (`mem_limit`; the repository's `deploy/docker-compose.database.yml` says `128g`, the running container was created with 98 GiB), no swap, no CPU limit |
| Running configuration not in the repository compose file | `ENABLE_MODULES=backup-filesystem`, `BACKUP_FILESYSTEM_PATH`, a bind mount of the backup directory on ZFS, `TOMBSTONE_DELETION_{CONCURRENCY=1,MIN_PER_CYCLE=1000,MAX_PER_CYCLE=100000}` |
| Host | AMD Ryzen 9 7950X3D, 32 threads, 188 GiB RAM, no swap, up 181 days; shared with ClearML (Elasticsearch, MongoDB), another Weaviate (`orbis`, 17.5 GiB), the test Weaviate and about 20 PR preview apps, the embedding service and Topicer |
| Data | a bind-mounted directory on a software RAID 0 over two NVMe partitions (ext4, no redundancy), 3.6 TiB, 964 GiB free (73% used) |
| Backups | `backup-filesystem` on ZFS pool `zfs1` (43 TiB, 98% used) |
| Monitoring | Prometheus metrics not enabled (`PROMETHEUS_MONITORING_ENABLED` unset); `LOG_LEVEL` unset (warning "log level not recognized") |

## Collections

| Collection (alias) | Objects | Vector index | Notes |
|---|---|---|---|
| `Chunks_test` (`Chunks`) | 8,280,272 | named `default`, HNSW, cosine, 3584 dims, maxConnections 32, efConstruction 128, dynamic ef 100–500, ACORN filtering, **RQ 8-bit, rescoreLimit 20**, shard `compressed: true` | 31 properties: 21 searchable (BM25 on `text`, `title`, `start_page_id`, 17 classification `text[]`), all filterable, range index only on `yearIssued`; 5 references (`document`, `userCollection`, three tag lists); **BlockMax WAND off** |
| `Documents_test` (`Documents`) | 59,008 | `default` declared, no vectors stored | 27 properties, BlockMax WAND off, reference `collection` |
| `Span_test` (`Span`) | 12,776 | none stored | |
| `Tag_test` (`Tag`) | 11,336 | none stored | |
| `Usercollection_test` (`UserCollection`) | 122 | none stored | |
| `TmpChunks` | 32 | unnamed, 3584 dims, uncompressed | experimental leftover, negligible size |
| `MetaDataEnrichmentTest` | 10 | none stored | experimental leftover, negligible size |

All collections have one shard, replication factor 1 and no multi-tenancy. `vectorIndexingStatus`
is `READY` with an empty queue everywhere. The `chunks_test_multivector` collection from #149 is
gone (collection and directory).

## Disk

The data directory is 317.6 GiB; `chunks_test` is 316.1 GiB of it:

| Component of `chunks_test` | Size | Notes |
|---|---|---|
| `lsm/objects` | 252.4 GiB | segments 127.3 + 57.5 + 46.6 + 14.5 + 6.5 GiB |
| — one current copy of every object | ≈127 GiB | 16.1 KiB per chunk, of which 14.0 KiB is the float32 vector (3584 × 4 B) |
| — superseded versions (estimate) | ≈125 GiB | the four later segments were written on 2026-10-13 (`chunk_year --write` rewrote all 8,280,272 chunks, #153). The split is estimated from segment sizes and the object size, not measured; LSM compaction should reclaim it, which only a later inventory can confirm. It does not compact segments of different levels promptly, and a merge needs temporary space of the merged size |
| BM25 (`*_searchable`) | 36.2 GiB | `text` 24.9 GiB, the rest under 1.4 GiB each |
| filterable and other property indexes | 25.4 GiB | `text` filterable 19.1 GiB (the application never filters on chunk text), `start_page_id` 2.9 GiB, `_id` 1.1 GiB |
| `vectors_compressed_default` | 1.1 GiB | RQ codes; a complete index needs ≈28 GiB |
| `vectors_default.hnsw.commitlog.d` | 1.0 GiB | graph commit log (condensed 2026-08-31, 2026-10-12) |

Everything else (documents 1.5 GiB, tags, spans, raft, schema) is under 2 GiB. No temporary,
orphaned or deleted-collection data was found in the data directory (`.backup.tmp` and `backups`
are empty; backups go to ZFS).

Probably reclaimable without data changes: the superseded object versions (≈125 GiB, an
estimate until compaction has run and a later inventory shows it).
Reclaimable only by schema/collection changes: the filterable index on `text` (19 GiB) and,
negligibly, the two experimental collections. Each backup takes 85–145 GiB on ZFS (188–268 GB
before compression).

## Memory

At idle and during the benchmark:

| | Value |
|---|---|
| Weaviate anonymous memory | 3.6 GiB idle, at most 4.2 GiB during the benchmark |
| Weaviate page cache (cgroup `file`) | 9.6–13 GiB |
| Weaviate cgroup peak since 2026-09-21 | 95 GiB of 98 GiB (page cache counts; probably the backup and the 2026-10-13 rewrite) |
| OOM kills | 0 |
| Host `MemAvailable` | 12–14.5 GiB of 188 GiB |
| ZFS ARC | 83–86 GiB (`arcstats` `size`, 12:41–12:42 UTC; `c_max` 94.0 GiB, `c_min` 5.9 GiB); Linux reports it as used, not available. The first inventory recorded 4 B here (a parser bug, fixed); the values are from the re-collected inventory |
| Swap | none |
| Memory pressure (PSI) | 0 now; cumulative `full` stall since boot about 82 hours (not datable) |

VSZ (49 GiB for Weaviate) is address space, not memory use, and is ignored here.

Weaviate's own footprint is small only because the vector index is nearly empty. A complete
8-bit RQ index keeps all codes in memory (27.6 GiB for 8.28 M × 3584 B) plus the graph (up to
about 4 GiB at maxConnections 32) and rescores from full vectors read from disk (page cache).
Expect about 35 GiB anonymous memory and a working page cache of tens of GiB. The host does not
have that available today unless the ARC shrinks. The container limit (98 GiB) is not the limit
that matters.

Startup today: shards loaded in 4 s, compressed-cache prefill of 198,855 vectors in 0.2 s
(asynchronous). With a complete index, expect the prefill to read about 28 GiB; queries are
served meanwhile (`wait_for_cache_prefill: false`).

## Vector index coverage

Self-retrieval checks with `inventory --coverage-sample 300` and the benchmark's `self_recall`
scenario (100 more chunks): 2/300 and 0/100 chunks were found in the top 10 for their own vector;
3/300 were found by a vector query filtered to their own id (which bypasses the graph search).
The top-1 distances of these queries were 0.09–0.43, so they return other chunks. On the
integration test store, the same checks find every chunk.

How much of the corpus the index covers is an **estimate from a sample**: 3 of 300 random
chunks found by the id-restricted query is 1% (95% interval about 0.3–2.9%); the startup
prefill count (198,855 of 8.28 M, 2.4%) and the size of the compressed-vector bucket (1.1 of
about 28 GiB) agree with it. "About 2%" in this report means this range, not a verified exact
fraction.

Observations from the files and backups (backups named by their start time):

- The backups up to the one of 2026-08-25, and the one started 2026-08-31 06:17, used the
  legacy unnamed vector (`main.hnsw.commitlog.d`) and contained a `vectors_compressed` bucket.
- The backup of 2026-08-28 (made after the chunks were recreated with the named vector
  `default`) contains the HNSW commit log but **no compressed-vector bucket**. The current store
  was restored from it on 2026-08-31 (its `restore_config.json`).
- The current compressed-vector bucket was first written on 2026-09-16, about 0.7 GiB, roughly
  200,000 codes. The shard reports `compressed: true`.

Explanation (plausible, **not proven**): the index is marked compressed, so search uses the
codes, and nodes without a code are not found; the restore from a backup without codes would
produce that state. How the index came to be marked compressed without its codes (RQ enabled
during or after the re-creation, before the backup) cannot be established read-only, and
[#375](https://github.com/DCGM/semant-demo/issues/375) should confirm the cause on a copy
before the repair. The consequence does not depend on the cause: rebuild the vector index and
verify it with the coverage check.

## Benchmark

Three runs of production-safe profiles, 100–150 randomly sampled chunks as inputs (seed 374), 40
requests per scenario and concurrency, at most 20 request starts per second, 5 warm-up requests
per scenario. Times are client-side and include gRPC and mapping; query vectors are stored chunk
vectors, so no embedding time is included.

- **A**: `baseline`, 10:09–10:14 UTC, tool version 1
  ([baseline-2026-10-16a.md](weaviate-audit-2026-10/baseline-2026-10-16a.md)). Each
  concurrency level ran the *next* 40 inputs, so levels differ in queries as well as
  concurrency (100 inputs for 120 requests: the last level partly repeats the first). Its tag
  scenario sampled tags that match no chunk, so its tag timings measure an empty search.
- **B**: `baseline`, 12:58–13:02 UTC, corrected tool
  ([baseline-2026-10-16b.md](weaviate-audit-2026-10/baseline-2026-10-16b.md)). Every level
  runs the *same* 40 inputs, so levels 5 and 10 repeat queries just served at level 1 and
  measure a **warm** cache; tag and collection searches query from a chunk inside the tag or
  collection. **The reference run for comparisons after the repair (#375).**
- **F**: `baseline-fresh-levels`, 13:03–13:08 UTC
  ([fresh-levels-2026-10-16.md](weaviate-audit-2026-10/fresh-levels-2026-10-16.md)): the hybrid
  and context scenarios with *disjoint* inputs per level (150 sampled, 40 fresh queries per
  level), for the concurrency cost of fresh queries.

| Scenario | B at 1 (fresh): p50 / p95 ms | B at 5 · 10 (warm repeats) | F at 5 (fresh) | F at 10 (fresh) | Notes |
|---|---|---|---|---|---|
| `bm25` (search page, keyword) | 15 / 24 | 4 / 8 · 4 / 9 | | | A (fresh at every level): 8–15 / 18–24 |
| `vector` (search page, vector) | 10 / 15 | 4 / 5 · 4 / 5 | | | fast partly because the index is nearly empty |
| `hybrid` (default search, RAG retrieval) | 121 / 148 | 29 / 49 · 12 / 14 | 563 / 687 | 925 / 1293 | fresh: CPU-bound, 16–23 cores, 1.3–1.5 GB disk read per query; A: 513 / 894 at 5, 1080 / 1819 at 10 |
| `hybrid_direct` (no references) | 82 / 123 | 19 / 125 · 7 / 11 | 480 / 779 | 797 / 1296 | the cost is not the reference expansion |
| `hybrid_year` | 73 / 134 | 32 / 102 · 32 / 105 | 280 / 456 | 257 / 541 | |
| `hybrid_language` | 85 / 135 | 28 / 89 · 16 / 84 | 373 / 568 | 504 / 875 | |
| `hybrid_document_type` (filter through the document reference) | 10 / 993 | 18 / 1478 · 22 / 1529 | | | logs "nested reference results exceed QUERY_MAXIMUM_RESULTS"; slow even when warm |
| `hybrid_tag` (query from a chunk inside the tag) | 3 / 14 | 2 / 4 · 3 / 5 | | | 40/40 non-empty; the sampled tags hold 1–2 chunks each (A: 0/40 non-empty, not representative) |
| `hybrid_user_collection` (query from a chunk inside the collection) | 3 / 9 | 3 / 4 · 3 / 5 | | | 40/40 non-empty (A: 25/40) |
| `chunk_context` (2 chunks before/after) | 304 / 1466 | 102 / 303 · 91 / 225 | 300 / 949 | 463 / 2266 | sorts all chunks of the document; max 4.1 s (F) |
| `document_view` (≤ 2000 chunks) | 36 / 290 | 41 / 286 · — | | | reads every chunk object of the document; A (other documents per level): 111 / 1216 |
| `corpus_overview` (uncached aggregates) | 476 / 496 | 1500 / 1606 · — | | | the same aggregates every time; cached by the app for 10 minutes |
| `mixed` (hybrid, year, bm25, collection, context, document) | 64 / 156 | 13 / 89 · 14 / 95 | | | A (fresh): 150 / 1370 at 5, 128 / 898 at 10 |

Runs A and F agree on the concurrency cost of fresh hybrid queries (about 0.9–1.1 s p50 at 10);
run B shows that the same queries repeated cost a few to a few tens of milliseconds. Real
traffic lies between the two, closer to fresh queries.

Diagnosis of the hybrid cost (sequential, 10 fresh queries each, cgroup CPU/IO deltas):
BM25 alone 18 ms and 0.04 CPU-s per query; near_vector 7 ms; hybrid with keyword weight only
(alpha 0) 2 ms; hybrid with vector weight only (alpha 1) 6 ms. Hybrid with both (alpha 0.5),
ranked or relative-score fusion: 110–130 ms, **2.6–3.0 CPU-s and 1.4–1.7 GB read per query**.
The same 10 queries repeated: 7 ms, 0.04 CPU-s, 9 MiB. Hybrid scores the keyword candidates
by vector distance too. With compressed codes missing for 98% of the chunks, those distances
probably come from full objects read from disk. This is a hypothesis to check by re-running
the baseline after the rebuild; if it persists, it is a separate problem.

For chunk context, a reference filter with `order > n` returns 2 chunks in 55 ms, but the same
query **sorted** by `order` takes 126 ms (max 761 ms) and reads about 0.7 GB per request,
because Weaviate loads every matching chunk object (16 KiB each, vector included) to sort them.
Counting a document's chunks through the reference reads similar amounts.

Disk I/O pressure on the host stayed low (PSI `some` ≤ 7.5%), Weaviate anonymous memory flat
(3.4–4.2 GiB), no request failed in the three runs (4,240 requests).

**Against the tolerance of an early public deployment** (interactive search within about 2 s,
RAG retrieval a small part of a multi-second LLM answer): every scenario meets it at the
expected concurrency of a few simultaneous requests. Ten simultaneous fresh hybrid searches
come close (1.3–1.8 s p95) and use most of the host's CPU, which the other services share.
This holds for the current, incomplete index. A complete index changes the vector part of every
hybrid query and the memory use, so these runs say nothing about capacity after the repair.

## Historical problems from #149

| #149 symptom | Status | Evidence |
|---|---|---|
| Memory saturation (92 of 98 GiB) | **Resolved for now, will partly return** | anon 3.6–4.2 GiB; deleting `chunks_test_multivector` and RQ removed most of it. Expect about 35 GiB after the index rebuild |
| Large HNSW cache prefill at startup | Not a problem now | 198,855 compressed vectors in 0.2 s; shard load 4 s. A full RQ cache is about 28 GiB to read at startup (asynchronous) |
| Nested reference expansion | **Still reproducible** | 758 warnings since 2026-09-21; 24 during run A from the `documentType` filter through the document reference (p95 1.0–2.4 s, no error). `yearIssued` no longer goes through the reference (#153) |
| BM25/hybrid/vector timeouts or partial results | Not observed | 0 timeouts in 4,240 requests (30 s timeout); slowest 4.1 s. But vector results are incomplete because of the index (above) |
| Sustained disk I/O and CPU spikes | **Still reproducible** | fresh hybrid queries: 1.3–1.5 GB read and about 2–3 CPU-s each; 23–26 cores at 10 concurrent |
| Aggregation panics | Not observed | 0 lines mentioning a panic since 2026-09-21; corpus overview aggregates and per-document counts succeed |
| Auth panics | Not testable | anonymous access, no authentication module configured |
| Raft warnings | Not a problem | one election warning at startup of a single node |
| Unexpected restarts / OOM | Not observed | up since 2026-09-21, restart count 0, 0 OOM kills |
| Disk pressure | Warnings only | 53 `read_disk_use` warnings: threshold 50%, disk at 73–90% (read-only at 95%) |

## Options

| Option | Disk | RAM | Latency / quality | Confidence | Risk, migration | Priority |
|---|---|---|---|---|---|---|
| Keep as is | — | — | vector and hybrid recall about 2% | high | — | **not acceptable** |
| **Rebuild the chunk vector index, keep HNSW + RQ 8-bit** | +27 GiB codes; a rewrite adds a temporary full copy of the objects (≈130 GiB) | +≈30 GiB anon | correct results; hybrid cost to re-measure | high | needs a rehearsal on a copy, a backup and a maintenance window; keep the old shard/backup for rollback; ARC cap first | **now** |
| RQ 1-bit or BQ instead of RQ 8-bit | codes 3.5 GiB instead of 27.6 | −24 GiB vs. RQ 8-bit | lower recall before rescoring; needs a larger rescore limit, more disk reads | medium (1-bit RQ support in 1.34 to verify) | same rebuild; measure recall with `self_recall`/overlap on a copy | consider during rebuild if RAM is short |
| PQ / SQ | PQ ≈ 1–2 GiB, SQ ≈ 28 GiB | similar to the codes | PQ needs training, lower recall at 3584 dims | low | rebuild | no |
| Lower `maxConnections` (32 → 16) | — | graph −50% (≤2 GiB) | slightly lower recall | medium | only at index creation | optional, small gain |
| Disk-oriented index (HFresh) | — | much lower | higher latency | low | not in 1.34; with the 1.40 upgrade (#312) | evaluate after #312 |
| Drop the filterable index on chunk `text` | −19 GiB | less page cache | none for the application | high | needs a new collection, or an index-deletion API if the target version has one | with the next collection rebuild |
| Enable BlockMax WAND on `Chunks` | smaller BM25 | — | faster BM25 on frequent terms | medium | needs a new collection or a migration | with the next collection rebuild |
| Chunk context without sorting all document chunks (bounded `order` range, sort in Python) | — | — | 0.1–0.5 s → tens of ms expected | high | application change only | **soon** |
| `documentType` filter as a chunk property (like `yearIssued`) | small | — | removes the nested reference expansion | medium | data copy like `chunk_year` | only if the filter is used |
| Compaction of superseded objects | −≈125 GiB (estimate) | — | — | medium | automatic; cannot be forced safely | wait; recheck with `inventory` |
| Schema flattening (#149) | — | — | — | — | — | not justified by current data |

## Named vectors

Per additional vector over the 8.28 M chunks, as raw/compressed sizes; the graph is an upper
bound at maxConnections 32 (64 links per node on layer 0, 8 B each):

| Dimensions | float32 in objects (disk) | RQ 8-bit codes (RAM + disk) | RQ 1-bit / BQ codes | HNSW graph |
|---|---|---|---|---|
| 384 | 11.8 GiB | 3.0 GiB | 0.4 GiB | ≤3.9 GiB |
| 768 | 23.7 GiB | 5.9 GiB | 0.7 GiB | ≤3.9 GiB |
| 1024 | 31.6 GiB | 7.9 GiB | 1.0 GiB | ≤3.9 GiB |
| 3584 (like the current one) | 110.6 GiB | 27.6 GiB | 3.5 GiB | ≤3.9 GiB |

Assumptions and constraints:

- The current vector, once indexed completely, needs about 35 GiB anonymous memory with RQ 8-bit.
  One more 1024-dimensional RQ 8-bit vector adds about 8–12 GiB, so about 45–50 GiB in total;
  two 3584-dimensional vectors need about 65–70 GiB. The host has to set this memory aside from
  the ARC and the other services.
- Adding a vector to existing objects rewrites every object (as `chunk_year --write` did), so the
  objects bucket temporarily grows by another full copy (≈130 GiB plus the new vectors) until
  compaction. The data filesystem has room (964 GiB), but plan backups (the ZFS pool is 98% full).
- Index build time was not measured (no writes in this audit); HNSW insertion of 8.28 M vectors
  at efConstruction 128 takes hours of CPU and competes with queries. Measure it on a copy.
- Required before named vectors: the complete current index (Conclusion 1), memory reserved for
  it, and a baseline run after the rebuild to compare against. Upgrading to 1.40 (#312) is
  independent but adds index options (and should be measured with the same profile).

## Follow-up

Separate issues, created for the justified changes:

- [#375](https://github.com/DCGM/semant-demo/issues/375) **Rebuild the chunk vector index** (critical): confirm the cause on a copy, staging
  rehearsal, memory reservation, backup and rollback, then re-run `inventory`, `baseline` and
  `baseline-fresh-levels` and `compare` them with the archived runs B and F (same id hash key).
- [#376](https://github.com/DCGM/semant-demo/issues/376) **Chunk context and document chunk counts read every chunk of the document**: bounded queries
  for `read_adjacent_chunks` / `read_following_chunk_texts` / `count_chunks`.

Noted here without an issue: the compose file's `mem_limit` (128g) and missing backup/tombstone
settings differ from the running container; the experimental `TmpChunks` and
`MetaDataEnrichmentTest` collections; the `documentType` reference filter; the low
`DISK_USE_WARNING_PERCENTAGE`; the full backup pool.

## Saved results

In the repository, [weaviate-audit-2026-10/](weaviate-audit-2026-10/) holds the Markdown
reports and compact `*.summary.json` files (all metrics, no per-query hashes) of runs A, B and F,
and the inventory (`inventory-2026-10-16b.md|json`, 12:42 UTC). The inventory was collected
again after the review because the first one recorded the ZFS ARC as 4 B (a parser bug) and
`--container-files` would have counted the backup mount; its other figures differ from the first
collection (10:08 UTC) only by normal drift (for example 958 instead of 964 GiB free), and the
coverage check gave the same 2/300 and 3/300.

The full results, which `compare` needs for result overlap, are archived as immutable, dated
files in the project's benchmark Gist (linked from #374/#377; **upload pending** when this was
written: add the exact Gist revision here once uploaded). Never overwrite them; later runs get
new dated files. Their id hashes are keyed (run A was converted with `sanitize`), and the key
stays on the production server outside the repository, so overlap with them can only be
computed there.

| File | Run | SHA-256 |
|---|---|---|
| `baseline-2026-10-16a.json` | A (tool version 1, sanitized) | `a1fce8ab12248ab7aa32432cd8d8bd6d41be1d62bf6e1df8afc807dc2227d9c0` |
| `baseline-2026-10-16b.json` | B (reference) | `e121451f09af2ebc3e8b28cbeb772f1f193e974953a3692d0ade6166105a697c` |
| `fresh-levels-2026-10-16.json` | F | `4f3fbc4c10afb67055fff1f3571d327d993c64cabe24a3825eb33eaf6cf90753` |

Check a download with `sha256sum` before comparing against it. Runs B and F record git commit
`f4cfaab`, a local commit that was split before publishing; `36c9921` has the identical tool
code.

## Reproduce

From `semant_demo_backend/` with the repository `.venv`, on the host (or a container with host
networking, `/sys/fs/cgroup` mounted, and the file list and log saved with
`docker exec … find -xdev` and `docker logs`, as in this audit). Use the same id hash key file
as the archived runs (it stays on the production server, outside the repository), or overlap
cannot be compared:

```bash
python -m semant_demo.maintenance.db_benchmark inventory --container semant-demo-weaviate-1 \
  --data-dir <host data dir> --container-files \
  --backup-dir <host backup dir> --coverage-sample 300 --out results/inventory
python -m semant_demo.maintenance.db_benchmark run --profile baseline \
  --container semant-demo-weaviate-1 --out results/baseline
python -m semant_demo.maintenance.db_benchmark compare \
  baseline-2026-10-16b.json results/baseline.json --out results/compare   # archived file, see Saved results
```

The audit run used `--cgroup`, `--files-list` and `--log-file` instead of `--container`,
because the host's Python is older than the backend's (3.12) and the tool ran in a
`python:3.12` container.
