# Weaviate benchmark run

- Created: 2026-10-17T12:37:10+00:00
- Target: `localhost:8080` (Weaviate 1.40.1), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v2, git `8e22680`
- Profile: `baseline` (fingerprint `38e2705497ecc09a`), seed 374, max 20.0 req/s, 40 requests or 20.0 s per point, timeout 30.0 s, warm-up 5 requests per scenario
- Inputs: sampled_chunks 100, with_vector 100, vector_dimensions 1024, vector_name Qwen3_Embedding_0_6B, with_terms 100, documents 100, tags 20, filter_values_checked {'tag': 84, 'user_collection': 11}, user_collections 10, document_types 10, sampling_seconds 3.76, query_set 3a430f46af4b; note: document_view skips 7 sampled documents with more than 2000 chunks
- Resource source: Weaviate container cgroup v2
- Heavy profile opt-in: False
- Inputs per level: every concurrency level runs the same inputs; levels after the first re-run them
- Id hashes: keyed, key id `68464083`

| scenario | layer | conc. | ok | non-empty | errors | timeouts | p50 ms | p95 ms | p99 ms | max ms | req/s | Weaviate CPU cores | anon max | disk read | host IO PSI max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | adapter | 1 | 40 | 40 | 0 | 0 | 6.8 | 10.2 | n/a | 17.6 | 20.44 | 0.19 | 16.4 GiB | 1063 MiB | 2.1 |
| bm25 | adapter | 5 | 40 | 40 | 0 | 0 | 2.9 | 9.4 | n/a | 15.2 | 20.47 | 0.07 | 16.4 GiB | 0 MiB | 1.4 |
| bm25 | adapter | 10 | 40 | 40 | 0 | 0 | 2.9 | 11 | n/a | 14.2 | 20.48 | 0.07 | 16.5 GiB | 0 MiB | 1.09 |
| vector | adapter | 1 | 40 | 40 | 0 | 0 | 5.3 | 13.1 | n/a | 15 | 20.37 | 0.1 | 16.5 GiB | 152 MiB | 0.73 |
| vector | adapter | 5 | 40 | 40 | 0 | 0 | 4.4 | 5.6 | n/a | 5.9 | 20.47 | 0.07 | 16.5 GiB | 0 MiB | 0.49 |
| vector | adapter | 10 | 40 | 40 | 0 | 0 | 4.4 | 5.6 | n/a | 5.8 | 20.46 | 0.07 | 16.5 GiB | 0 MiB | 1.81 |
| hybrid | adapter | 1 | 40 | 40 | 0 | 0 | 16.9 | 20.1 | n/a | 20.5 | 20.33 | 2.51 | 16.5 GiB | 4725 MiB | 1.58 |
| hybrid | adapter | 5 | 40 | 40 | 0 | 0 | 10 | 12.9 | n/a | 15.4 | 20.41 | 0.45 | 16.6 GiB | 0 MiB | 1.29 |
| hybrid | adapter | 10 | 40 | 40 | 0 | 0 | 10.9 | 12.7 | n/a | 18.1 | 20.41 | 0.47 | 16.6 GiB | 0 MiB | 0.86 |
| hybrid_year | adapter | 1 | 40 | 40 | 0 | 0 | 31.4 | 41 | n/a | 48 | 20.23 | 1.9 | 17.4 GiB | 2252 MiB | 0.65 |
| hybrid_year | adapter | 5 | 40 | 40 | 0 | 0 | 28.5 | 36 | n/a | 42.2 | 20.24 | 1.08 | 18.1 GiB | 0 MiB | 0.53 |
| hybrid_year | adapter | 10 | 40 | 40 | 0 | 0 | 28.4 | 40.9 | n/a | 43.3 | 20.21 | 1.13 | 18.8 GiB | 0 MiB | 0.36 |
| hybrid_language | adapter | 1 | 40 | 40 | 0 | 0 | 13.5 | 60 | n/a | 189.9 | 18.58 | 0.85 | 18.9 GiB | 862 MiB | 0.24 |
| hybrid_language | adapter | 5 | 40 | 40 | 0 | 0 | 14.1 | 70.5 | n/a | 186.8 | 20.38 | 0.69 | 19.1 GiB | 0 MiB | 0.16 |
| hybrid_language | adapter | 10 | 40 | 40 | 0 | 0 | 14 | 57.5 | n/a | 209.3 | 20.41 | 0.7 | 19.3 GiB | 0 MiB | 0.1 |
| hybrid_document_type | adapter | 1 | 40 | 40 | 0 | 0 | 10.8 | 1090.3 | n/a | 1211.6 | 6 | 6.1 | 24.6 GiB | 842 MiB | 0.05 |
| hybrid_document_type | adapter | 5 | 40 | 40 | 0 | 0 | 11.2 | 1435.5 | n/a | 1678.3 | 12.27 | 14.04 | 27.0 GiB | 0 MiB | 0.74 |
| hybrid_document_type | adapter | 10 | 40 | 40 | 0 | 0 | 11 | 1334.9 | n/a | 1384.3 | 12.76 | 13.96 | 27.3 GiB | 0 MiB | 0.5 |
| hybrid_tag | adapter | 1 | 40 | 40 | 0 | 0 | 2.9 | 6 | n/a | 7.1 | 20.48 | 0.1 | 27.3 GiB | 398 MiB | 1.54 |
| hybrid_tag | adapter | 5 | 40 | 40 | 0 | 0 | 2.2 | 4.3 | n/a | 10.5 | 20.49 | 0.06 | 27.3 GiB | 0 MiB | 1.26 |
| hybrid_tag | adapter | 10 | 40 | 40 | 0 | 0 | 2.2 | 5.4 | n/a | 6.3 | 20.49 | 0.07 | 27.3 GiB | 0 MiB | 0.84 |
| hybrid_user_collection | adapter | 1 | 40 | 40 | 0 | 0 | 3.7 | 5.9 | n/a | 14.4 | 20.47 | 0.14 | 27.3 GiB | 83 MiB | 0.56 |
| hybrid_user_collection | adapter | 5 | 40 | 40 | 0 | 0 | 4.3 | 5.4 | n/a | 5.6 | 20.47 | 0.15 | 27.3 GiB | 0 MiB | 0.37 |
| hybrid_user_collection | adapter | 10 | 40 | 40 | 0 | 0 | 4.3 | 6.3 | n/a | 9.8 | 20.45 | 0.14 | 27.3 GiB | 0 MiB | 0.25 |
| bm25_direct | direct | 1 | 40 | 40 | 0 | 0 | 1.3 | 5.1 | n/a | 8.8 | 20.5 | 0.05 | 27.3 GiB | 0 MiB | 0.16 |
| bm25_direct | direct | 5 | 40 | 40 | 0 | 0 | 1.3 | 4.6 | n/a | 8.3 | 20.49 | 0.05 | 27.3 GiB | 0 MiB | 0.29 |
| bm25_direct | direct | 10 | 40 | 40 | 0 | 0 | 1.3 | 4.5 | n/a | 8.4 | 20.49 | 0.05 | 27.3 GiB | 0 MiB | 0.37 |
| vector_direct | direct | 1 | 40 | 40 | 0 | 0 | 2.5 | 3.5 | n/a | 3.7 | 20.48 | 0.06 | 27.3 GiB | 0 MiB | 0.25 |
| vector_direct | direct | 5 | 40 | 40 | 0 | 0 | 2.7 | 3.6 | n/a | 6.3 | 20.47 | 0.06 | 27.3 GiB | 0 MiB | 0.16 |
| vector_direct | direct | 10 | 40 | 40 | 0 | 0 | 2.6 | 3.5 | n/a | 3.5 | 20.48 | 0.06 | 27.3 GiB | 0 MiB | 0.11 |
| hybrid_direct | direct | 1 | 40 | 40 | 0 | 0 | 7.6 | 9.4 | n/a | 11.1 | 20.44 | 0.38 | 27.3 GiB | 0 MiB | 0.25 |
| hybrid_direct | direct | 5 | 40 | 40 | 0 | 0 | 7.4 | 9.5 | n/a | 10.2 | 20.44 | 0.39 | 27.3 GiB | 0 MiB | 0.32 |
| hybrid_direct | direct | 10 | 40 | 40 | 0 | 0 | 7.2 | 9.4 | n/a | 10.3 | 20.43 | 0.39 | 27.3 GiB | 0 MiB | 0.39 |
| chunk_context | adapter | 1 | 40 | 40 | 0 | 0 | 138 | 331.2 | n/a | 1876.3 | 4.44 | 1.6 | 27.9 GiB | 0 MiB | 0.94 |
| chunk_context | adapter | 5 | 40 | 40 | 0 | 0 | 176.8 | 361.2 | n/a | 2170.8 | 14.7 | 6.08 | 28.0 GiB | 1 MiB | 0.42 |
| chunk_context | adapter | 10 | 40 | 40 | 0 | 0 | 180.3 | 353.4 | n/a | 2062.3 | 15.46 | 4.8 | 28.0 GiB | 0 MiB | 0.23 |
| document_view | adapter | 1 | 40 | 40 | 0 | 0 | 21.3 | 111.9 | n/a | 246.5 | 15.8 | 0.93 | 28.0 GiB | 0 MiB | 0.15 |
| document_view | adapter | 5 | 40 | 40 | 0 | 0 | 27.4 | 158.8 | n/a | 245.3 | 18.82 | 0.76 | 27.5 GiB | 0 MiB | 0.1 |
| corpus_overview | adapter | 1 | 40 | 0 | 0 | 0 | 273.7 | 291.8 | n/a | 357.4 | 3.6 | 6.36 | 27.5 GiB | 0 MiB | 0.05 |
| corpus_overview | adapter | 5 | 40 | 0 | 0 | 0 | 485.2 | 594.6 | n/a | 632.8 | 9.47 | 22.64 | 27.2 GiB | 0 MiB | 0.01 |
| mixed | mixed | 1 | 40 | 40 | 0 | 0 | 12.4 | 134.3 | n/a | 177.5 | 15.84 | 2.12 | 27.2 GiB | 0 MiB | 0 |
| mixed | mixed | 5 | 40 | 40 | 0 | 0 | 12.5 | 141.5 | n/a | 169.7 | 20.45 | 0.95 | 27.2 GiB | 0 MiB | 0 |
| mixed | mixed | 10 | 40 | 40 | 0 | 0 | 12.2 | 150.9 | n/a | 166.3 | 20.44 | 1.01 | 27.2 GiB | 0 MiB | 0 |
| self_recall | direct | 1 | 100 | 100 | 0 | 0 | 2.7 | 11.3 | 11.9 | 12.4 | 20.19 | 0.06 | 27.2 GiB | 79 MiB | 2.17 |

Self-recall `self_recall`: own chunk in top-10 for 100/100 sampled chunks.

Scenarios: `bm25` — Search page, keyword mode (app adapter, document reference returned); `vector` — Search page, vector mode; `hybrid` — Search page default and RAG retrieval (hybrid, alpha 0.5, 10 chunks); `hybrid_year` — Hybrid + chunk yearIssued range filter; `hybrid_language` — Hybrid + chunk language filter; `hybrid_document_type` — Hybrid + documentType filter through the document reference; `hybrid_tag` — Hybrid + chunk tag reference filter (automatic or positive); `hybrid_user_collection` — Hybrid within a user collection (reference filter); `bm25_direct` — BM25 without references (database-level); `vector_direct` — near_vector without references; `hybrid_direct` — Hybrid without references; `chunk_context` — Two chunks before and after a chunk (span chat / context); `document_view` — Document view: all chunks of a document with collection membership; `corpus_overview` — Corpus overview aggregates over Documents (uncached); `mixed` — Interleaved user-like mix; `self_recall` — Recall check: each sampled chunk in the top 10 for its own vector
