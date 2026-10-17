# Weaviate benchmark run

- Created: 2026-10-17T12:41:27+00:00
- Target: `localhost:8080` (Weaviate 1.40.1), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v2, git `8e22680`
- Profile: `baseline` (fingerprint `38e2705497ecc09a`), seed 374, max 20.0 req/s, 40 requests or 20.0 s per point, timeout 30.0 s, warm-up 5 requests per scenario
- Inputs: sampled_chunks 100, with_vector 100, vector_dimensions 1024, vector_name Qwen3_Embedding_0_6B, with_terms 100, documents 100, tags 20, filter_values_checked {'tag': 84, 'user_collection': 11}, user_collections 10, document_types 10, sampling_seconds 0.38, query_set 716d6939397d; note: document_view skips 7 sampled documents with more than 2000 chunks
- Resource source: Weaviate container cgroup v2
- Heavy profile opt-in: False
- Inputs per level: every concurrency level runs the same inputs; levels after the first re-run them
- Id hashes: keyed, key id `968d574b`

| scenario | layer | conc. | ok | non-empty | errors | timeouts | p50 ms | p95 ms | p99 ms | max ms | req/s | Weaviate CPU cores | anon max | disk read | host IO PSI max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | adapter | 1 | 40 | 40 | 0 | 0 | 3.5 | 8.2 | n/a | 14.5 | 20.47 | 0.07 | 27.5 GiB | 0 MiB | 0.34 |
| bm25 | adapter | 5 | 40 | 40 | 0 | 0 | 3.2 | 7.8 | n/a | 13.6 | 20.48 | 0.07 | 27.5 GiB | 0 MiB | 0.28 |
| bm25 | adapter | 10 | 40 | 40 | 0 | 0 | 3.3 | 7.3 | n/a | 14.2 | 20.47 | 0.08 | 27.5 GiB | 0 MiB | 0.18 |
| vector | adapter | 1 | 40 | 40 | 0 | 0 | 4.2 | 5.2 | n/a | 5.7 | 20.45 | 0.07 | 27.5 GiB | 0 MiB | 4.08 |
| vector | adapter | 5 | 40 | 40 | 0 | 0 | 4.2 | 5.1 | n/a | 5.8 | 20.46 | 0.07 | 27.5 GiB | 0 MiB | 3.34 |
| vector | adapter | 10 | 40 | 40 | 0 | 0 | 4.3 | 5.2 | n/a | 5.5 | 20.47 | 0.07 | 27.5 GiB | 0 MiB | 2.24 |
| hybrid | adapter | 1 | 40 | 40 | 0 | 0 | 10.6 | 12.8 | n/a | 14.8 | 20.42 | 0.46 | 27.5 GiB | 0 MiB | 1.5 |
| hybrid | adapter | 5 | 40 | 40 | 0 | 0 | 10.6 | 16.5 | n/a | 21.9 | 20.41 | 0.46 | 27.5 GiB | 0 MiB | 1 |
| hybrid | adapter | 10 | 40 | 40 | 0 | 0 | 9.9 | 12.1 | n/a | 14.6 | 20.41 | 0.45 | 27.6 GiB | 0 MiB | 0.67 |
| hybrid_year | adapter | 1 | 40 | 40 | 0 | 0 | 29 | 39.5 | n/a | 44.8 | 20.2 | 1.06 | 28.1 GiB | 0 MiB | 0.37 |
| hybrid_year | adapter | 5 | 40 | 40 | 0 | 0 | 28.2 | 37.8 | n/a | 43.5 | 20.23 | 1.03 | 28.6 GiB | 0 MiB | 0.24 |
| hybrid_year | adapter | 10 | 40 | 40 | 0 | 0 | 29.2 | 39.6 | n/a | 42.9 | 20.2 | 1.05 | 29.0 GiB | 0 MiB | 0.16 |
| hybrid_language | adapter | 1 | 40 | 40 | 0 | 0 | 12.9 | 60.6 | n/a | 181.2 | 18.7 | 0.59 | 29.1 GiB | 0 MiB | 0.11 |
| hybrid_language | adapter | 5 | 40 | 40 | 0 | 0 | 13.2 | 57.1 | n/a | 181.9 | 20.4 | 2.69 | 29.1 GiB | 0 MiB | 0.24 |
| hybrid_language | adapter | 10 | 40 | 40 | 0 | 0 | 12.8 | 57.8 | n/a | 179.3 | 20.4 | 0.63 | 27.0 GiB | 0 MiB | 0.19 |
| hybrid_document_type | adapter | 1 | 40 | 40 | 0 | 0 | 8.2 | 1005.7 | n/a | 1119.9 | 6.35 | 5.65 | 27.3 GiB | 0 MiB | 0.13 |
| hybrid_document_type | adapter | 5 | 40 | 40 | 0 | 0 | 10.7 | 1254 | n/a | 1395.1 | 13.09 | 13.01 | 27.2 GiB | 0 MiB | 0.05 |
| hybrid_document_type | adapter | 10 | 40 | 40 | 0 | 0 | 12 | 1305.1 | n/a | 1353.3 | 13.42 | 14.53 | 27.4 GiB | 0 MiB | 2.38 |
| hybrid_tag | adapter | 1 | 40 | 40 | 0 | 0 | 2.2 | 4.1 | n/a | 7 | 20.49 | 0.06 | 27.3 GiB | 0 MiB | 1.31 |
| hybrid_tag | adapter | 5 | 40 | 40 | 0 | 0 | 1.9 | 3.8 | n/a | 6.5 | 20.49 | 0.06 | 27.3 GiB | 0 MiB | 0.87 |
| hybrid_tag | adapter | 10 | 40 | 40 | 0 | 0 | 2.4 | 6.1 | n/a | 7.7 | 20.48 | 0.07 | 27.3 GiB | 0 MiB | 0.77 |
| hybrid_user_collection | adapter | 1 | 40 | 40 | 0 | 0 | 3.8 | 4.8 | n/a | 5.5 | 20.46 | 0.14 | 27.3 GiB | 0 MiB | 0.51 |
| hybrid_user_collection | adapter | 5 | 40 | 40 | 0 | 0 | 4.2 | 5.3 | n/a | 5.4 | 20.45 | 0.14 | 27.3 GiB | 0 MiB | 0.34 |
| hybrid_user_collection | adapter | 10 | 40 | 40 | 0 | 0 | 4.2 | 5.1 | n/a | 5.4 | 20.46 | 0.14 | 27.3 GiB | 0 MiB | 0.23 |
| bm25_direct | direct | 1 | 40 | 40 | 0 | 0 | 1.3 | 6.5 | n/a | 10.3 | 20.5 | 0.06 | 27.3 GiB | 0 MiB | 0.15 |
| bm25_direct | direct | 5 | 40 | 40 | 0 | 0 | 1.5 | 7.6 | n/a | 12.1 | 20.49 | 0.06 | 27.4 GiB | 0 MiB | 0.1 |
| bm25_direct | direct | 10 | 40 | 40 | 0 | 0 | 1.2 | 8.8 | n/a | 14.8 | 20.49 | 0.06 | 27.4 GiB | 0 MiB | 0.06 |
| vector_direct | direct | 1 | 40 | 40 | 0 | 0 | 2.7 | 3.2 | n/a | 3.4 | 20.48 | 0.06 | 27.4 GiB | 0 MiB | 0.04 |
| vector_direct | direct | 5 | 40 | 40 | 0 | 0 | 2.6 | 3.4 | n/a | 3.5 | 20.48 | 0.06 | 27.4 GiB | 0 MiB | 0.03 |
| vector_direct | direct | 10 | 40 | 40 | 0 | 0 | 2.4 | 3.1 | n/a | 3.2 | 20.48 | 0.05 | 27.4 GiB | 0 MiB | 0.01 |
| hybrid_direct | direct | 1 | 40 | 40 | 0 | 0 | 7.5 | 9.4 | n/a | 12.2 | 20.43 | 0.39 | 27.4 GiB | 0 MiB | 0.01 |
| hybrid_direct | direct | 5 | 40 | 40 | 0 | 0 | 7.2 | 9.7 | n/a | 10.8 | 20.44 | 0.38 | 27.5 GiB | 0 MiB | 0 |
| hybrid_direct | direct | 10 | 40 | 40 | 0 | 0 | 7.2 | 9.9 | n/a | 14.7 | 20.44 | 0.39 | 27.5 GiB | 0 MiB | 1.81 |
| chunk_context | adapter | 1 | 40 | 40 | 0 | 0 | 134.6 | 278 | n/a | 1908.5 | 4.4 | 1.22 | 28.3 GiB | 3 MiB | 1.21 |
| chunk_context | adapter | 5 | 40 | 40 | 0 | 0 | 184.5 | 376.2 | n/a | 2156.8 | 14.89 | 6.48 | 28.4 GiB | 0 MiB | 0.36 |
| chunk_context | adapter | 10 | 40 | 40 | 0 | 0 | 199.5 | 433.3 | n/a | 2155.7 | 15.18 | 6.76 | 28.4 GiB | 0 MiB | 0.24 |
| document_view | adapter | 1 | 40 | 40 | 0 | 0 | 19.5 | 114.2 | n/a | 235.9 | 16.02 | 0.64 | 28.3 GiB | 0 MiB | 0.16 |
| document_view | adapter | 5 | 40 | 40 | 0 | 0 | 27.2 | 129.8 | n/a | 221.8 | 18.89 | 0.77 | 28.3 GiB | 2 MiB | 0.08 |
| corpus_overview | adapter | 1 | 40 | 0 | 0 | 0 | 276.2 | 291.6 | n/a | 373.3 | 3.57 | 6.35 | 28.3 GiB | 0 MiB | 0.05 |
| corpus_overview | adapter | 5 | 40 | 0 | 0 | 0 | 488.2 | 651.4 | n/a | 670.3 | 9.48 | 22.85 | 27.1 GiB | 0 MiB | 0.01 |
| mixed | mixed | 1 | 40 | 40 | 0 | 0 | 10.9 | 144.3 | n/a | 157.9 | 15.84 | 0.74 | 27.1 GiB | 0 MiB | 0 |
| mixed | mixed | 5 | 40 | 40 | 0 | 0 | 12.8 | 162.8 | n/a | 223.5 | 20.45 | 2.81 | 27.1 GiB | 0 MiB | 2.17 |
| mixed | mixed | 10 | 40 | 40 | 0 | 0 | 12.4 | 164.8 | n/a | 176.1 | 20.45 | 1.03 | 27.1 GiB | 0 MiB | 1.96 |
| self_recall | direct | 1 | 100 | 100 | 0 | 0 | 2.6 | 3.3 | 3.5 | 4.5 | 20.19 | 0.05 | 27.1 GiB | 0 MiB | 1.44 |

Self-recall `self_recall`: own chunk in top-10 for 100/100 sampled chunks.

Scenarios: `bm25` — Search page, keyword mode (app adapter, document reference returned); `vector` — Search page, vector mode; `hybrid` — Search page default and RAG retrieval (hybrid, alpha 0.5, 10 chunks); `hybrid_year` — Hybrid + chunk yearIssued range filter; `hybrid_language` — Hybrid + chunk language filter; `hybrid_document_type` — Hybrid + documentType filter through the document reference; `hybrid_tag` — Hybrid + chunk tag reference filter (automatic or positive); `hybrid_user_collection` — Hybrid within a user collection (reference filter); `bm25_direct` — BM25 without references (database-level); `vector_direct` — near_vector without references; `hybrid_direct` — Hybrid without references; `chunk_context` — Two chunks before and after a chunk (span chat / context); `document_view` — Document view: all chunks of a document with collection membership; `corpus_overview` — Corpus overview aggregates over Documents (uncached); `mixed` — Interleaved user-like mix; `self_recall` — Recall check: each sampled chunk in the top 10 for its own vector
