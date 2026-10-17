# Weaviate benchmark run

- Created: 2026-10-17T12:45:31+00:00
- Target: `localhost:8080` (Weaviate 1.40.1), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v2, git `8e22680`
- Profile: `baseline-fresh-levels` (fingerprint `c1455aadf289555a`), seed 374, max 20.0 req/s, 40 requests or 20.0 s per point, timeout 30.0 s, warm-up 5 requests per scenario
- Inputs: sampled_chunks 150, with_vector 150, vector_dimensions 1024, vector_name Qwen3_Embedding_0_6B, with_terms 150, documents 150, tags 0, filter_values_checked {}, user_collections 0, document_types 0, sampling_seconds 0.08, query_set ec1e0dc70b86
- Resource source: Weaviate container cgroup v2
- Heavy profile opt-in: False
- Inputs per level: each concurrency level runs the next inputs of the sample (fresh queries)
- Id hashes: keyed, key id `968d574b`

| scenario | layer | conc. | ok | non-empty | errors | timeouts | p50 ms | p95 ms | p99 ms | max ms | req/s | Weaviate CPU cores | anon max | disk read | host IO PSI max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hybrid | adapter | 1 | 40 | 40 | 0 | 0 | 10 | 11.9 | n/a | 12.6 | 20.41 | 0.45 | 27.1 GiB | 0 MiB | 0.58 |
| hybrid | adapter | 5 | 40 | 40 | 0 | 0 | 10 | 12.3 | n/a | 14.1 | 20.4 | 0.46 | 27.1 GiB | 0 MiB | 0.39 |
| hybrid | adapter | 10 | 40 | 40 | 0 | 0 | 10.3 | 12.4 | n/a | 288.1 | 20.41 | 0.62 | 27.4 GiB | 0 MiB | 0.26 |
| hybrid_year | adapter | 1 | 40 | 40 | 0 | 0 | 27.6 | 37.5 | n/a | 41.7 | 20.23 | 0.99 | 27.5 GiB | 0 MiB | 0.17 |
| hybrid_year | adapter | 5 | 40 | 40 | 0 | 0 | 31.4 | 41.1 | n/a | 53.7 | 20.18 | 1.21 | 27.8 GiB | 577 MiB | 2.1 |
| hybrid_year | adapter | 10 | 40 | 40 | 0 | 0 | 30.1 | 41.8 | n/a | 208.7 | 20.24 | 1.34 | 28.7 GiB | 365 MiB | 1.56 |
| hybrid_language | adapter | 1 | 40 | 40 | 0 | 0 | 11.9 | 60.6 | n/a | 181.6 | 18.68 | 0.58 | 28.8 GiB | 0 MiB | 1.04 |
| hybrid_language | adapter | 5 | 40 | 40 | 0 | 0 | 14.8 | 106.2 | n/a | 313.2 | 20.31 | 0.94 | 28.9 GiB | 234 MiB | 0.7 |
| hybrid_language | adapter | 10 | 40 | 40 | 0 | 0 | 15.5 | 104.2 | n/a | 202.1 | 19.95 | 0.91 | 29.3 GiB | 395 MiB | 0.46 |
| hybrid_direct | direct | 1 | 40 | 40 | 0 | 0 | 7.4 | 9 | n/a | 12.6 | 20.42 | 0.38 | 29.3 GiB | 0 MiB | 0.31 |
| hybrid_direct | direct | 5 | 40 | 40 | 0 | 0 | 7.3 | 10 | n/a | 23.3 | 20.43 | 0.38 | 29.4 GiB | 0 MiB | 0.21 |
| hybrid_direct | direct | 10 | 40 | 40 | 0 | 0 | 7.5 | 12.6 | n/a | 283.1 | 20.44 | 0.57 | 29.8 GiB | 0 MiB | 0.14 |
| chunk_context | adapter | 1 | 40 | 40 | 0 | 0 | 151.6 | 317 | n/a | 1914.3 | 4.23 | 1.64 | 29.8 GiB | 0 MiB | 0.09 |
| chunk_context | adapter | 5 | 40 | 40 | 0 | 0 | 176.1 | 288.8 | n/a | 2262.3 | 11.57 | 4.47 | 29.0 GiB | 0 MiB | 0.02 |
| chunk_context | adapter | 10 | 40 | 40 | 0 | 0 | 196 | 328.3 | n/a | 2435.5 | 16.09 | 6.66 | 28.5 GiB | 224 MiB | 0.01 |

Scenarios: `hybrid` — Search page default and RAG retrieval (hybrid, alpha 0.5, 10 chunks); `hybrid_year` — Hybrid + chunk yearIssued range filter; `hybrid_language` — Hybrid + chunk language filter; `hybrid_direct` — Hybrid without references; `chunk_context` — Two chunks before and after a chunk (span chat / context)
