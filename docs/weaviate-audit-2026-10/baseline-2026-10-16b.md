# Weaviate benchmark run

- Created: 2026-10-16T12:57:55+00:00
- Target: `localhost:8080` (Weaviate 1.34.4), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v2, git `f4cfaab`
- Profile: `baseline` (fingerprint `38e2705497ecc09a`), seed 374, max 20.0 req/s, 40 requests or 20.0 s per point, timeout 30.0 s, warm-up 5 requests per scenario
- Inputs: sampled_chunks 100, with_vector 100, vector_dimensions 3584, vector_name default, with_terms 100, documents 100, tags 20, filter_values_checked {'tag': 84, 'user_collection': 11}, user_collections 10, document_types 10, sampling_seconds 12.89, query_set 716d6939397d; note: document_view skips 7 sampled documents with more than 2000 chunks
- Resource source: Weaviate container cgroup v2
- Heavy profile opt-in: False
- Inputs per level: every concurrency level runs the same inputs; levels after the first re-run them
- Id hashes: keyed, key id `968d574b`

| scenario | layer | conc. | ok | non-empty | errors | timeouts | p50 ms | p95 ms | p99 ms | max ms | req/s | Weaviate CPU cores | anon max | disk read | host IO PSI max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | adapter | 1 | 40 | 40 | 0 | 0 | 14.5 | 24.4 | n/a | 36 | 20.37 | 0.53 | 3.5 GiB | 3839 MiB | 3.96 |
| bm25 | adapter | 5 | 40 | 40 | 0 | 0 | 3.9 | 8.2 | n/a | 12.8 | 20.47 | 0.1 | 3.5 GiB | 0 MiB | 3.1 |
| bm25 | adapter | 10 | 40 | 40 | 0 | 0 | 4 | 8.7 | n/a | 11.2 | 20.47 | 0.1 | 3.5 GiB | 0 MiB | 2.08 |
| vector | adapter | 1 | 40 | 40 | 0 | 0 | 9.7 | 15 | n/a | 23.7 | 20.4 | 1.01 | 3.6 GiB | 3199 MiB | 2.66 |
| vector | adapter | 5 | 40 | 40 | 0 | 0 | 4 | 5.3 | n/a | 5.9 | 20.47 | 0.09 | 3.6 GiB | 0 MiB | 1.96 |
| vector | adapter | 10 | 40 | 40 | 0 | 0 | 4 | 4.9 | n/a | 6.2 | 20.47 | 0.09 | 3.6 GiB | 0 MiB | 1.31 |
| hybrid | adapter | 1 | 40 | 40 | 0 | 0 | 121.3 | 147.6 | n/a | 185.1 | 8.09 | 22.37 | 3.6 GiB | 62281 MiB | 2.7 |
| hybrid | adapter | 5 | 40 | 40 | 0 | 0 | 29 | 48.9 | n/a | 72.4 | 20.39 | 7.66 | 3.9 GiB | 12240 MiB | 2.65 |
| hybrid | adapter | 10 | 40 | 40 | 0 | 0 | 11.5 | 13.8 | n/a | 24.2 | 20.39 | 1.01 | 3.9 GiB | 149 MiB | 2.35 |
| hybrid_year | adapter | 1 | 40 | 40 | 0 | 0 | 72.8 | 133.9 | n/a | 165.1 | 12.62 | 9.41 | 3.9 GiB | 29615 MiB | 3.79 |
| hybrid_year | adapter | 5 | 40 | 40 | 0 | 0 | 32 | 101.9 | n/a | 149.4 | 20.26 | 2.19 | 3.9 GiB | 720 MiB | 3.83 |
| hybrid_year | adapter | 10 | 40 | 40 | 0 | 0 | 31.7 | 105.3 | n/a | 147.6 | 20.33 | 1.81 | 3.8 GiB | 1 MiB | 2.56 |
| hybrid_language | adapter | 1 | 40 | 40 | 0 | 0 | 85 | 134.7 | n/a | 141.2 | 11.17 | 12.77 | 3.8 GiB | 37960 MiB | 4.15 |
| hybrid_language | adapter | 5 | 40 | 40 | 0 | 0 | 27.5 | 88.5 | n/a | 98.7 | 20.38 | 2.94 | 3.8 GiB | 4560 MiB | 4.3 |
| hybrid_language | adapter | 10 | 40 | 40 | 0 | 0 | 15.9 | 84.2 | n/a | 100.1 | 20.37 | 1.35 | 3.8 GiB | 0 MiB | 3.18 |
| hybrid_document_type | adapter | 1 | 40 | 36 | 0 | 0 | 10.4 | 992.5 | n/a | 1027 | 5.88 | 5.97 | 3.8 GiB | 10878 MiB | 2.63 |
| hybrid_document_type | adapter | 5 | 40 | 36 | 0 | 0 | 17.9 | 1477.7 | n/a | 1851.4 | 11.95 | 9.45 | 4.0 GiB | 11 MiB | 2.15 |
| hybrid_document_type | adapter | 10 | 40 | 36 | 0 | 0 | 21.8 | 1528.6 | n/a | 1940.4 | 12.01 | 9.73 | 4.0 GiB | 12 MiB | 1.18 |
| hybrid_tag | adapter | 1 | 40 | 40 | 0 | 0 | 3.1 | 14 | n/a | 18.6 | 20.48 | 0.15 | 3.9 GiB | 830 MiB | 0.83 |
| hybrid_tag | adapter | 5 | 40 | 40 | 0 | 0 | 2.3 | 4.1 | n/a | 6.8 | 20.48 | 0.07 | 3.9 GiB | 0 MiB | 0.67 |
| hybrid_tag | adapter | 10 | 40 | 40 | 0 | 0 | 2.5 | 5.1 | n/a | 6.7 | 20.48 | 0.08 | 3.9 GiB | 5 MiB | 0.45 |
| hybrid_user_collection | adapter | 1 | 40 | 40 | 0 | 0 | 2.8 | 9.2 | n/a | 20.5 | 20.47 | 0.1 | 3.9 GiB | 211 MiB | 0.24 |
| hybrid_user_collection | adapter | 5 | 40 | 40 | 0 | 0 | 2.8 | 4.1 | n/a | 4.6 | 20.48 | 0.08 | 3.9 GiB | 0 MiB | 0.16 |
| hybrid_user_collection | adapter | 10 | 40 | 40 | 0 | 0 | 2.7 | 4.9 | n/a | 7.3 | 20.48 | 0.08 | 3.9 GiB | 0 MiB | 0.13 |
| bm25_direct | direct | 1 | 40 | 40 | 0 | 0 | 3.5 | 7 | n/a | 11.8 | 20.49 | 0.16 | 3.9 GiB | 637 MiB | 0.24 |
| bm25_direct | direct | 5 | 40 | 40 | 0 | 0 | 1.6 | 4.8 | n/a | 8 | 20.49 | 0.07 | 3.9 GiB | 0 MiB | 0.34 |
| bm25_direct | direct | 10 | 40 | 40 | 0 | 0 | 1.7 | 4.5 | n/a | 8.9 | 20.49 | 0.07 | 3.9 GiB | 0 MiB | 0.28 |
| vector_direct | direct | 1 | 40 | 40 | 0 | 0 | 4.4 | 7.2 | n/a | 13.6 | 20.46 | 0.31 | 3.9 GiB | 1139 MiB | 0.33 |
| vector_direct | direct | 5 | 40 | 40 | 0 | 0 | 2.2 | 2.8 | n/a | 3.9 | 20.48 | 0.08 | 3.9 GiB | 0 MiB | 0.27 |
| vector_direct | direct | 10 | 40 | 40 | 0 | 0 | 2.1 | 3.1 | n/a | 3.4 | 20.48 | 0.07 | 3.9 GiB | 0 MiB | 1.94 |
| hybrid_direct | direct | 1 | 40 | 40 | 0 | 0 | 81.9 | 122.5 | n/a | 142.8 | 11.99 | 22.11 | 3.9 GiB | 40813 MiB | 2.93 |
| hybrid_direct | direct | 5 | 40 | 40 | 0 | 0 | 18.8 | 124.6 | n/a | 148.2 | 20.43 | 10.23 | 3.8 GiB | 12701 MiB | 3.12 |
| hybrid_direct | direct | 10 | 40 | 40 | 0 | 0 | 6.8 | 11.1 | n/a | 14.6 | 20.43 | 0.89 | 3.8 GiB | 10 MiB | 2.6 |
| chunk_context | adapter | 1 | 40 | 40 | 0 | 0 | 304.3 | 1465.9 | n/a | 2604 | 2.23 | 1.1 | 3.8 GiB | 49152 MiB | 2.26 |
| chunk_context | adapter | 5 | 40 | 40 | 0 | 0 | 102.2 | 303.1 | n/a | 2319.6 | 14.51 | 4.43 | 3.8 GiB | 1966 MiB | 2.21 |
| chunk_context | adapter | 10 | 40 | 40 | 0 | 0 | 91.3 | 224.5 | n/a | 2266.6 | 14.5 | 4.45 | 3.8 GiB | 0 MiB | 1.21 |
| document_view | adapter | 1 | 40 | 40 | 0 | 0 | 35.9 | 289.5 | n/a | 1803.5 | 6.81 | 0.8 | 3.7 GiB | 10689 MiB | 0.81 |
| document_view | adapter | 5 | 40 | 40 | 0 | 0 | 40.5 | 286.2 | n/a | 714.6 | 16.22 | 1.3 | 3.7 GiB | 13 MiB | 1.2 |
| corpus_overview | adapter | 1 | 40 | 0 | 0 | 0 | 475.9 | 496 | n/a | 510.5 | 2.1 | 5.98 | 3.7 GiB | 2 MiB | 2.35 |
| corpus_overview | adapter | 5 | 40 | 0 | 0 | 0 | 1500 | 1605.6 | n/a | 1637 | 3.12 | 10.81 | 3.7 GiB | 0 MiB | 1.77 |
| mixed | mixed | 1 | 40 | 40 | 0 | 0 | 64.2 | 156.3 | n/a | 166.2 | 11.85 | 9.06 | 3.7 GiB | 22740 MiB | 3.07 |
| mixed | mixed | 5 | 40 | 40 | 0 | 0 | 12.9 | 89.2 | n/a | 108.9 | 20.44 | 1.35 | 3.7 GiB | 4 MiB | 2.69 |
| mixed | mixed | 10 | 40 | 40 | 0 | 0 | 13.5 | 94.6 | n/a | 119.7 | 20.46 | 1.13 | 3.7 GiB | 0 MiB | 2.97 |
| self_recall | direct | 1 | 100 | 0 | 0 | 0 | 7 | 9.5 | 14.8 | 15.6 | 20.16 | 0.68 | 3.7 GiB | 5791 MiB | 4.9 |

Self-recall `self_recall`: own chunk in top-10 for 0/100 sampled chunks.

Scenarios: `bm25` — Search page, keyword mode (app adapter, document reference returned); `vector` — Search page, vector mode; `hybrid` — Search page default and RAG retrieval (hybrid, alpha 0.5, 10 chunks); `hybrid_year` — Hybrid + chunk yearIssued range filter; `hybrid_language` — Hybrid + chunk language filter; `hybrid_document_type` — Hybrid + documentType filter through the document reference; `hybrid_tag` — Hybrid + chunk tag reference filter (automatic or positive); `hybrid_user_collection` — Hybrid within a user collection (reference filter); `bm25_direct` — BM25 without references (database-level); `vector_direct` — near_vector without references; `hybrid_direct` — Hybrid without references; `chunk_context` — Two chunks before and after a chunk (span chat / context); `document_view` — Document view: all chunks of a document with collection membership; `corpus_overview` — Corpus overview aggregates over Documents (uncached); `mixed` — Interleaved user-like mix; `self_recall` — Recall check: each sampled chunk in the top 10 for its own vector
