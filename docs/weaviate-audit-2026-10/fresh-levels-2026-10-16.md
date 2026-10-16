# Weaviate benchmark run

- Created: 2026-10-16T13:02:54+00:00
- Target: `localhost:8080` (Weaviate 1.34.4), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v2, git `f4cfaab`
- Profile: `baseline-fresh-levels` (fingerprint `c1455aadf289555a`), seed 374, max 20.0 req/s, 40 requests or 20.0 s per point, timeout 30.0 s, warm-up 5 requests per scenario
- Inputs: sampled_chunks 150, with_vector 150, vector_dimensions 3584, vector_name default, with_terms 150, documents 150, tags 0, filter_values_checked {}, user_collections 0, document_types 0, sampling_seconds 0.7, query_set ec1e0dc70b86
- Resource source: Weaviate container cgroup v2
- Heavy profile opt-in: False
- Inputs per level: each concurrency level runs the next inputs of the sample (fresh queries)
- Id hashes: keyed, key id `968d574b`

| scenario | layer | conc. | ok | non-empty | errors | timeouts | p50 ms | p95 ms | p99 ms | max ms | req/s | Weaviate CPU cores | anon max | disk read | host IO PSI max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hybrid | adapter | 1 | 40 | 40 | 0 | 0 | 128.4 | 168.7 | n/a | 177.8 | 8.24 | 16.47 | 3.7 GiB | 52527 MiB | 7.53 |
| hybrid | adapter | 5 | 40 | 40 | 0 | 0 | 562.5 | 687 | n/a | 1028.9 | 8.88 | 22.85 | 3.7 GiB | 58246 MiB | 8.38 |
| hybrid | adapter | 10 | 40 | 40 | 0 | 0 | 924.6 | 1293.3 | n/a | 2046.2 | 9.31 | 22.92 | 3.8 GiB | 54865 MiB | 8.5 |
| hybrid_year | adapter | 1 | 40 | 40 | 0 | 0 | 128.2 | 169.2 | n/a | 188.9 | 8.02 | 12.03 | 3.8 GiB | 45146 MiB | 8.98 |
| hybrid_year | adapter | 5 | 40 | 40 | 0 | 0 | 280.1 | 455.8 | n/a | 747.8 | 14.43 | 20.92 | 3.8 GiB | 32327 MiB | 9.54 |
| hybrid_year | adapter | 10 | 40 | 40 | 0 | 0 | 257 | 540.8 | n/a | 610.3 | 18.55 | 21.3 | 3.9 GiB | 24841 MiB | 8.72 |
| hybrid_language | adapter | 1 | 40 | 40 | 0 | 0 | 126.8 | 162.2 | n/a | 166.5 | 7.82 | 14.44 | 3.9 GiB | 52911 MiB | 9.71 |
| hybrid_language | adapter | 5 | 40 | 40 | 0 | 0 | 372.8 | 568.3 | n/a | 715.2 | 12.19 | 24.67 | 3.8 GiB | 42215 MiB | 8.67 |
| hybrid_language | adapter | 10 | 40 | 40 | 0 | 0 | 504.1 | 874.7 | n/a | 1092.4 | 14.4 | 25.06 | 3.9 GiB | 36097 MiB | 7.49 |
| hybrid_direct | direct | 1 | 40 | 40 | 0 | 0 | 120.5 | 149.8 | n/a | 163.2 | 8.33 | 21.43 | 3.9 GiB | 59012 MiB | 7.11 |
| hybrid_direct | direct | 5 | 40 | 40 | 0 | 0 | 479.9 | 778.9 | n/a | 843.9 | 9.15 | 24.24 | 3.9 GiB | 56053 MiB | 6.84 |
| hybrid_direct | direct | 10 | 40 | 40 | 0 | 0 | 797.4 | 1295.5 | n/a | 1577.5 | 10.57 | 24.86 | 3.9 GiB | 49398 MiB | 6.48 |
| chunk_context | adapter | 1 | 40 | 40 | 0 | 0 | 297.7 | 1523.5 | n/a | 3346.5 | 2.02 | 1.09 | 3.9 GiB | 49410 MiB | 5.63 |
| chunk_context | adapter | 5 | 40 | 40 | 0 | 0 | 299.6 | 948.7 | n/a | 4101.7 | 6.99 | 3.7 | 3.9 GiB | 37170 MiB | 3.28 |
| chunk_context | adapter | 10 | 40 | 40 | 0 | 0 | 462.5 | 2266.2 | n/a | 2883 | 10.74 | 7.79 | 3.8 GiB | 36625 MiB | 2.38 |

Scenarios: `hybrid` — Search page default and RAG retrieval (hybrid, alpha 0.5, 10 chunks); `hybrid_year` — Hybrid + chunk yearIssued range filter; `hybrid_language` — Hybrid + chunk language filter; `hybrid_direct` — Hybrid without references; `chunk_context` — Two chunks before and after a chunk (span chat / context)
