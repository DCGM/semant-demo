# Production Weaviate audit after the Qwen migration, 2026-10-17 (#394)

A read-only reassessment of the production Weaviate after the Qwen3 embedding migration
([#385](https://github.com/DCGM/semant-demo/issues/385)), the upgrade to 1.40.1 (#312, PR #389),
the container-derived Go memory limit (PR #390) and the Topicer switch (PR #391). It repeats the
[2026-10-16 pre-migration audit](WEAVIATE_AUDIT_2026-10.md) (which stays unchanged) with the
[benchmark tool](DB_BENCHMARK.md), and revisits [#149](https://github.com/DCGM/semant-demo/issues/149)
and [#376](https://github.com/DCGM/semant-demo/issues/376). Measured on 2026-10-17 between 12:19
and 12:48 UTC, about 7 hours after the backfill finished, with light user traffic (host load
average 1.1–1.4). Nothing was written to the store, no index or setting was changed and no service
was restarted.

## Conclusions

1. **The replacement vector index is complete as far as a read-only check can show.** All 500
   chunks of a random sample were found by their own vector in the top 10 and by an
   id-restricted vector query (the pre-migration index found 2 and 3 of 300); the benchmark's
   `self_recall` found 100/100. With 0 misses in 500 the missing fraction is below about 0.6% (95%).
   The compressed-vector bucket holds 8.7 GiB, about what 8.28 M 1024-byte RQ codes need
   (≈7.9 GiB plus keys and not yet compacted versions). The backfill processed all 8,280,272
   chunks with 0 empty inputs and exit 0 (see [Preconditions](#preconditions)). An exact count of
   chunks with a valid vector needs a full scan, which was **not run** (it reads the whole store;
   not authorized for this audit).
2. **The fresh-hybrid cost of #149 is gone.** A fresh hybrid query takes 17 ms p50 (121 ms before)
   and about 0.1 GB of disk reads the first time (1.3–1.5 GB before); fresh queries at 10 concurrent
   take 10 ms p50 / 12 ms p95 (0.9 s / 1.3 s before) with half a core of Weaviate CPU (23 cores
   before). This confirms the pre-migration hypothesis that the missing compressed vectors forced
   distance computations from full objects on disk.
3. **No blocking problem for up to 10 concurrent users on the single host.** About 1,900 benchmark
   requests had no error and no timeout. Search paths used by the application take 4–60 ms p95 (up to 106 ms with the language filter at 5–10 fresh concurrent queries).
   The slow paths that remain are chunk context (#376, 135–200 ms p50, up to 2.4 s), uncached
   corpus aggregates (0.3–0.5 s, cached by the application) and the `documentType` reference
   filter (1.0–1.3 s p95), which the application's Search does not use.
4. **Memory now has headroom.** Weaviate's anonymous memory was 16.4 GiB at rest and 28.5 GiB after
   the benchmark (the `documentType` scenario raised it; Go keeps the heap). The Go memory limit is
   84.2 GB (80% of the 98 GiB container limit, `LIMIT_RESOURCES`), the host had 73–86 GiB
   available, and the ZFS ARC is 26 GiB (83–86 GiB before). The container reached its limit 488
   times since the restart by filling it with page cache, with 0 OOM kills.
5. **Act now: there is no backup of the migrated store.** The newest Weaviate backup is from
   2026-10-12, before the Qwen vectors (8.8 hours of GPU backfill) existed. The backup ZFS pool has
   1,007 GiB free (98% used); the current store is 167 GiB on disk.
6. **#149 can be closed**: of its symptoms only the nested reference expansion remains, and only on
   a filter the application does not use (see [#149 symptoms](#historical-problems-from-149)).
   #376 is still justified but no longer urgent.

## Preconditions

| Item | Value |
|---|---|
| Weaviate | 1.40.1 (`e0c3f76`), single node, container `semant-demo-weaviate-1` created 2026-10-16 20:45 UTC (PR #390), restart count 0 |
| Limits | memory 98 GiB, no swap on the host, no CPU limit (`GOMAXPROCS=32`); Go memory limit 84,181,359,001 B (log "Set memory limit") |
| Aliases | `Chunks` → `Chunks_test`, `Documents` → `Documents_test`, `Span`, `Tag`, `UserCollection` unchanged |
| Chunks | 8,280,272 objects (as on 2026-10-16: no new chunks were ingested) |
| Chunk vector | only `Qwen3_Embedding_0_6B`: HNSW, cosine, 1024 dims, maxConnections 32, efConstruction 128, dynamic ef, ACORN, **RQ 8-bit, rescoreLimit 20**; shard `compressed: true`, `READY`, indexing queue 0 |
| Removed | the old `default` vector (3584 dims) and the hyphenated `Qwen3-Embedding-0-6B`; no vector directories or buckets of either remain (only an empty symlink `lsm/vectors_compressed` → the deleted `vectors_compressed_default`, from 2026-08-31) |
| Application | production app `SEARCH_VECTORS_CONFIG=…/search_vectors_qwen.yaml`, default and only vector `qwen3-embedding-0.6b` → `target_vector: Qwen3_Embedding_0_6B` |
| GraphQL | `Aggregate` and `Get` with a `document` reference work under `Chunks_test` and the `Chunks` alias. Startup logs "ignoring ref prop … nonexistent class" while classes load (ordering at startup; the references work) and "Multiple vector spaces are present, GraphQL Explore … disabled" (Explore is not used) |
| BM25 and properties | BM25 results for the 40 benchmark queries are identical to the pre-migration run B (overlap 1.0), so the inverted indexes and text survived; references and filters return results in every scenario |

**Backfill.** `data_tools/embedder` (config `input_template: '{{ text }}'`, no document
instruction, `truncate_prompt_tokens: -1`) started 2026-10-16 20:27 UTC. Its first process stopped
at the planned Weaviate restart at 20:45 after about 290,000 chunks; the restarted process (20:45:41)
skipped 290,704 chunks that already had the vector, embedded 7,989,568, found 0 empty inputs and
finished at 2026-10-17 05:34 UTC with exit 0 (it stops with an error on a failed write). A write
lost at the restart would have been embedded again, because the scan checks the vector itself.
Startup prefilled 290,700 compressed vectors, the state at the restart.

**Query and document formatting.** All vectors and all queries come from the same `qwen-embedder`
container (up since 2026-10-16 18:42 UTC, restart count 0): image `vllm/vllm-openai:v0.31.0` pinned
by digest, model revision `97b0c614…`, `--max-model-len 2048`. Documents are embedded as plain text;
queries use the prefix `Instruct: Given a web search query, retrieve relevant passages that answer
the query\nQuery:` (the model card's recommended asymmetric use).

**Truncation at 2048 tokens is not limiting.** The embedder's own histogram over all 8,766,263
requests since it started (the whole backfill and every query since) has no request above 2,000
tokens; a truncated input would count as 2,048. The mean is 374 tokens, and 92.5% have at most
500.

**New ingestion does not add the Qwen vector.** The repository has no chunk ingestion path; chunks
come from external tools ([#313](https://github.com/DCGM/semant-demo/issues/313)). A newly ingested
chunk has no `Qwen3_Embedding_0_6B` vector and is invisible to vector search (and the vector half of
hybrid search) until the embedder is run again; it is resumable and embeds only chunks without the
vector. Noted on #313.

**BlockMax WAND flag.** The schema of `Chunks_test` now reports `usingBlockMaxWAND: true` (it was
off before; it changed when the old vector was deleted, 2026-10-16 about 20:26 UTC). Its searchable
buckets are still in the map-collection format (segment suffix `.s2`, also for segments written
after the restart), unlike `Tag_test` and `Span_test` (`.s5`). The flag does not describe the data
on disk; no migration took place. BM25 results are unchanged (above).

## Disk

The data directory is 167.0 GiB (317.6 GiB before); `chunks_test` is 165.4 GiB of it. 1,013.5 GiB
are free on the data filesystem.

| Component of `chunks_test` | Size | Before | Notes |
|---|---|---|---|
| `lsm/objects` | 53.7 GiB | 252.4 GiB | 39.1 + 8.1 + 4.0 + 2.0 + 0.3 GiB. Each object now holds a 4 KiB float32 vector instead of 14 KiB; one current copy is an estimated 48 GiB, so a few GiB of superseded versions from the backfill remain |
| `property_text_searchable` (BM25) | 41.7 GiB | 24.9 GiB | segments 24.2 + 12.6 + 3.2 + … GiB, written 01:56–05:35 UTC during the backfill. Each vector update rewrote the object's inverted entries; an estimated 17 GiB are superseded entries awaiting compaction (estimate; recheck with `inventory`) |
| `property_text` (filterable) | 19.9 GiB | 19.1 GiB | still unused by the application |
| `vectors_compressed_Qwen3_Embedding_0_6B` | 8.7 GiB | 1.1 GiB (`default`) | RQ codes |
| `vectors_Qwen3_Embedding_0_6B.hnsw.commitlog.d` | 1.1 GiB | 1.0 GiB | |

The pre-migration estimate of ≈125 GiB of superseded objects is confirmed in substance: the
objects bucket has been compacted to about one copy. Disk warnings (`read_disk_use`, threshold
50%, disk at 71%) remain warnings only.

## Memory

| | Now | 2026-10-16 |
|---|---|---|
| Weaviate anonymous memory | 16.4 GiB at rest; 27–29 GiB during and after the benchmark | 3.6–4.2 GiB |
| Weaviate page cache (cgroup `file`) | 61–66 GiB | 9.6–13 GiB |
| Container memory limit / Go memory limit | 98 GiB / 84.2 GB | 98 GiB / none |
| Cgroup `memory.events max` (limit reached, page cache reclaimed) | 488 since 2026-10-16 20:45 | — |
| OOM kills | 0 | 0 |
| Host `MemAvailable` | 86 GiB before, 73 GiB after the runs | 12–14.5 GiB |
| ZFS ARC | 26 GiB (`c_max` 94 GiB) | 83–86 GiB |

The anonymous memory rose by about 8 GiB during the `hybrid_document_type` scenario (nested
reference expansion) and stayed there: the Go runtime keeps freed heap until it needs it or nears
the Go memory limit. The pre-migration estimate of about 35 GiB for a complete 3584-dimensional
index no longer applies; the 1024-dimensional RQ index needs about 8 GiB of codes plus the graph.
The container fills its 98 GiB with page cache and reclaims it at the limit; this caps Weaviate's
page cache, not its own memory, and caused no OOM kill. The compose file in the repository says
`128g`; the running container (and the server's compose file) use 98 GiB.

## Benchmark

Production-safe profiles from `semant_demo/configs/db_benchmark/` (1/5/10 concurrent requests, at
most 20 request starts per second, 40 requests or 20 s per scenario and level, 30 s timeout),
seed 374, **`--target-vector Qwen3_Embedding_0_6B`** in every run, git `8e22680`. Query vectors
are stored chunk vectors, so no query embedding or LLM time is included. Runs (results in
[weaviate-audit-2026-10-17/](weaviate-audit-2026-10-17/)):

- **a**: `baseline`, 12:37–12:40 UTC ([baseline-2026-10-17a.md](weaviate-audit-2026-10-17/baseline-2026-10-17a.md)).
  Level 1 is the first timed execution of these inputs (as in run B). Made with a throwaway id
  hash key by mistake (the tool's container had no access to the key file), so its result hashes
  cannot be compared with any other run; its timings are valid.
- **b**: `baseline` again, 12:41–12:44 UTC, with the archived runs' key `968d574b`
  ([baseline-2026-10-17b.md](weaviate-audit-2026-10-17/baseline-2026-10-17b.md)). Same inputs as a,
  so **every level is warm**. The reference run for later comparisons;
  [comparison with B](weaviate-audit-2026-10-17/compare-B-2026-10-17.md).
- **f**: `baseline-fresh-levels`, 12:45–12:46 UTC
  ([fresh-levels-2026-10-17.md](weaviate-audit-2026-10-17/fresh-levels-2026-10-17.md),
  [comparison with F](weaviate-audit-2026-10-17/compare-F-2026-10-17.md)). With the same seed its
  first 100 sampled chunks are those of the baseline, so level 1 repeats queries just served; levels
  5 and 10 run fresh inputs. The same holds for the pre-migration run F.

| Scenario | B at 1 (fresh, before) | **a at 1 (fresh)** | b at 5 · 10 (warm) | F at 5 · 10 (fresh, before) | **f at 5 · 10 (fresh)** |
|---|---|---|---|---|---|
| `bm25` | 15 / 24 | 7 / 10 | 3 / 8 · 3 / 7 | | |
| `vector` | 10 / 15 | 5 / 13 | 4 / 5 · 4 / 5 | | |
| `hybrid` (default search, RAG) | 121 / 148 | **17 / 20** | 11 / 17 · 10 / 12 | 563 / 687 · 925 / 1293 | **10 / 12 · 10 / 12** |
| `hybrid_direct` (no references) | 82 / 123 | 8 / 9 | 7 / 10 · 7 / 10 | 480 / 779 · 797 / 1296 | 7 / 10 · 8 / 13 |
| `hybrid_year` | 73 / 134 | 31 / 41 | 28 / 38 · 29 / 40 | 280 / 456 · 257 / 541 | 31 / 41 · 30 / 42 |
| `hybrid_language` | 85 / 135 | 14 / 60 | 13 / 57 · 13 / 58 | 373 / 568 · 504 / 875 | 15 / 106 · 16 / 104 |
| `hybrid_document_type` | 10 / 993 | 11 / 1090 | 11 / 1254 · 12 / 1305 | | |
| `hybrid_tag` | 3 / 14 | 3 / 6 | 2 / 4 · 2 / 6 | | |
| `hybrid_user_collection` | 3 / 9 | 4 / 6 | 4 / 5 · 4 / 5 | | |
| `chunk_context` | 304 / 1466 | 138 / 331 (max 1.9 s) | 185 / 376 · 200 / 433 | 300 / 949 · 463 / 2266 | 176 / 289 · 196 / 328 |
| `document_view` (≤ 2000 chunks) | 36 / 290 | 21 / 112 | 27 / 130 · — | | |
| `corpus_overview` (uncached) | 476 / 496 | 274 / 292 | 488 / 651 · — | | |
| `mixed` | 64 / 156 | 12 / 134 | 13 / 163 · 12 / 165 | | |

p50 / p95 in milliseconds. `corpus_overview` reports 0 non-empty because aggregates are not
counted as results (the same in run B).

Resources (cgroup deltas per scenario and level): run a's 40 first hybrid queries read 4.7 GB from
disk in total (about 0.12 GB per query; 1.3–1.5 GB before) at 2.5 cores. All other hybrid levels
read nothing from disk and used 0.4–1.3 cores (16–25 before). The remaining CPU-heavy paths are
`hybrid_document_type` (6–15 cores), `corpus_overview` at 5 concurrent (23 cores for about 0.5 s
each) and `chunk_context` (5–7 cores at 5–10 concurrent). Host I/O pressure stayed low (PSI `some`
≤ 2.2%).

**Caveats.** The page cache was warm: the backfill and a day of use had read much of the store, and
the cgroup held 61 GiB of page cache. A cold start (after a restart or under memory pressure) will
be slower until the cache refills; the tool does not produce cold-cache conditions. Vector results
of the old and new embeddings are different search spaces: the overlap of 0.005 (vector) to 0.37
(hybrid) with run B shows the results changed, not their quality.

## Historical problems from #149

| #149 symptom | Status | Evidence |
|---|---|---|
| Memory saturation (92 of 98 GiB) | **Resolved** | anonymous memory 16–29 GiB of an 84 GB Go limit; the cgroup fills up with page cache (488 reclaims at the limit), 0 OOM kills |
| Large HNSW cache prefill at startup | Not a problem; full prefill not yet observed | the last start prefilled 290,700 codes (the index was being filled); a start now loads ≈8 GiB of codes, asynchronous |
| Nested reference expansion | **Still reproducible, not on an application path** | 52 warnings (up to 53,277 nested results) from the benchmark's `documentType` filter through the document reference, p95 1.0–1.3 s, 6–15 cores. The application's Search does not filter by `documentType`, and the production log had no such warning between the restart and the benchmark (≈15 hours) |
| BM25/hybrid timeouts, partial results | Not observed | 0 timeouts in ≈1,900 requests (30 s timeout), slowest 2.4 s (chunk context); no "partial results" or "hybrid failed" lines in the log since 2026-10-16 20:45 |
| Sustained disk I/O and CPU spikes | **Resolved for search** | fresh hybrid 0.12 GB and 2.5 cores at first execution, then no disk reads and under 1.5 cores; remaining CPU peaks in `documentType`, uncached corpus aggregates and chunk context (above) |
| Aggregation panics | Not observed (weak evidence) | 0 lines mentioning a panic in ≈16 hours of log; corpus aggregates and chunk counts succeed |
| Auth panics | Not testable | anonymous access, no authentication module |
| Raft warnings | Not a problem | one election warning at the start of the single node |
| Unexpected restarts / OOM | Not observed (short window) | the only restart since 2026-09-21 was the planned one for PR #390; restart count 0, 0 OOM kills |
| Disk pressure | Warnings only | 71% used, 1,014 GiB free; warning threshold 50%, read-only at 95%. Backup pool 98% used |

## #376: chunk context and document reads

Chunk context (`read_adjacent_chunks`, unchanged code) takes 135–200 ms p50, 280–430 ms p95, at
most 1.9–2.4 s, and 1.2–6.8 cores at 1–10 concurrent; before it was 90–460 ms p50 and up to 4.1 s
with tens of GB of disk reads. It no longer reads from disk because the smaller objects stay in page
cache, but it still loads and sorts every chunk of a document, which costs CPU and is the slowest
interactive path left. Document view takes 20–27 ms p50 and 112–130 ms p95. `count_chunks` was not
measured separately. The bounded-order-query fix remains a cheap application change worth doing,
but it is no longer urgent; updated on #376.

## Single-host recommendation

The current host is adequate for up to 10 concurrent users: application search paths stay under
110 ms p95 at 10 concurrent fresh requests (most under 15 ms), without errors, with most of the host's CPU and 70+ GiB of RAM
free. Before relying on it:

1. **Make a Weaviate backup of the migrated store** (operator action; check the ZFS pool space first).
2. Run the embedder after every chunk ingestion until ingestion adds the vector itself (#313).
3. Optionally, an exact coverage count: one sequential cursor scan of ids and the Qwen vector
   (reads the whole store, about 50 GB; run it off-peak).

Not justified by these measurements: schema flattening, other quantization or index types, more
memory. The earlier options for the next collection rebuild (dropping the filterable index on chunk
`text`, real BlockMax WAND) still apply but are not needed now.

## Saved results

In the repository, [weaviate-audit-2026-10-17/](weaviate-audit-2026-10-17/) holds the inventory
(`inventory-2026-10-17.md|json`, 12:21 UTC, 500-chunk coverage sample, seed 394), the Markdown
reports and compact `*.summary.json` of runs a, b and f, and the comparisons with runs B and F.

The full results are archived as immutable files in the project's benchmark Gist, revision
[`163e0f8`](https://gist.github.com/michal-hradis/5db0a765435bbaf8b2b12a155134282f/163e0f84f459b4f70b5aa81c461b5a320f491cb1)
(with an updated `SHA256SUMS`; the 2026-10-16 files are unchanged). Download a file at that
revision from
`https://gist.githubusercontent.com/michal-hradis/5db0a765435bbaf8b2b12a155134282f/raw/163e0f84f459b4f70b5aa81c461b5a320f491cb1/<file>`.

| File | Run | SHA-256 |
|---|---|---|
| `baseline-2026-10-17a.json` | a (throwaway id key: no overlap comparisons) | `f6c8acf3c57321aa2594aa3c75e1e4c3c8b08b6b4274e05f20f3611a5a0b04d2` |
| `baseline-2026-10-17b.json` | b (reference after the migration, key `968d574b`) | `91b4f118aeb5aba3e10bd796efd4ffd9d6cc8f006f94e9c9e1b3821c2621eb5e` |
| `fresh-levels-2026-10-17.json` | f (key `968d574b`) | `33fb30e5fd2bee6f5b2557291f1f3786309176d453e47d03d3617408133a963b` |

## Reproduce

As in the [2026-10-16 audit](WEAVIATE_AUDIT_2026-10.md#reproduce): the tool ran from
`semant_demo_backend/` with the repository `.venv` inside a `python:3.12` container with host
networking and `/sys/fs/cgroup` mounted read-only, using `--cgroup`, a saved file list
(`docker exec … find /var/lib/weaviate -xdev -type f -exec stat -c '%s %n' {} +`) and a saved log
(`docker logs`). Pass the key file explicitly when the tool runs in a container
(`--id-key-file ~/.config/semant-demo/db-benchmark-id-key`, mounted), or it creates a new key inside
the container and the results cannot be compared (run a).

```bash
python -m semant_demo.maintenance.db_benchmark inventory --cgroup <weaviate cgroup> \
  --target-vector Qwen3_Embedding_0_6B --data-dir <host data dir> --files-list files.txt \
  --backup-dir <host backup dir> --log-file weaviate.log --coverage-sample 500 --seed 394 \
  --out results/inventory-2026-10-17
python -m semant_demo.maintenance.db_benchmark run --profile baseline --cgroup <weaviate cgroup> \
  --target-vector Qwen3_Embedding_0_6B --id-key-file <key file> --out results/baseline-2026-10-17b
python -m semant_demo.maintenance.db_benchmark run --profile baseline-fresh-levels --cgroup <weaviate cgroup> \
  --target-vector Qwen3_Embedding_0_6B --id-key-file <key file> --out results/fresh-levels-2026-10-17
python -m semant_demo.maintenance.db_benchmark compare baseline-2026-10-16b.json \
  results/baseline-2026-10-17b.json --out results/compare-B-2026-10-17
```

## Not covered

- **End-to-end smoke checks** of #394 (Czech and German queries through the application with live
  query embedding, filtered and BM25-only Search, RAG retrieval and citations, Topicer, document,
  annotation and collection workflows) were not run in this audit (not authorized). The Topicer
  configuration was verified end to end with the Qwen embedder and vector when it was switched
  (PR #391, [deploy/README.md](../deploy/README.md#topicer)).
- An exact count of chunks with a valid vector (see recommendation 3).
- Cold-cache behaviour and a full compressed-cache prefill at startup.
