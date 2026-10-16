# Weaviate benchmark run

- Created: 2026-10-16T10:09:11+00:00
- Target: `localhost:8080` (Weaviate 1.34.4), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v1, git `985a269`
- Profile: `baseline` (fingerprint `2f81b722cce82ed1`), seed 374, max 20.0 req/s, 40 requests or 20.0 s per point, timeout 30.0 s, warm-up 5 requests per scenario
- Inputs: sampled_chunks 100, with_vector 100, vector_dimensions 3584, vector_name default, with_terms 100, documents 100, tags 20, user_collections 10, document_types 10, sampling_seconds 13.01, query_set 8e519190f939; note: document_view skips 7 sampled documents with more than 2000 chunks
- Resource source: Weaviate container cgroup v2
- Heavy profile opt-in: False
- Inputs per level: each concurrency level ran the next inputs (tool version 1): levels differ in queries as well as concurrency
- Id hashes: keyed, key id `968d574b` (keyed from unkeyed version 1 hashes)

| scenario | layer | conc. | ok | non-empty | errors | timeouts | p50 ms | p95 ms | p99 ms | max ms | req/s | Weaviate CPU cores | anon max | disk read | host IO PSI max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bm25 | adapter | 1 | 40 | 40 | 0 | 0 | 14.6 | 24 | n/a | 27.1 | 20.29 | 0.74 | 3.6 GiB | 3699 MiB | 4 |
| bm25 | adapter | 5 | 40 | 40 | 0 | 0 | 11.2 | 19.2 | n/a | 19.8 | 20.39 | 0.45 | 3.6 GiB | 2890 MiB | 2.98 |
| bm25 | adapter | 10 | 40 | 40 | 0 | 0 | 7.8 | 18.3 | n/a | 206.2 | 20.45 | 0.39 | 3.7 GiB | 1521 MiB | 2.18 |
| vector | adapter | 1 | 40 | 40 | 0 | 0 | 10.6 | 25.5 | n/a | 76.5 | 20.11 | 0.98 | 3.7 GiB | 3565 MiB | 1.64 |
| vector | adapter | 5 | 40 | 40 | 0 | 0 | 9.8 | 13.5 | n/a | 17 | 20.42 | 0.98 | 3.7 GiB | 3180 MiB | 1.24 |
| vector | adapter | 10 | 40 | 40 | 0 | 0 | 5.8 | 11.3 | n/a | 21.2 | 20.46 | 0.49 | 3.7 GiB | 1451 MiB | 0.98 |
| hybrid | adapter | 1 | 40 | 40 | 0 | 0 | 133.1 | 176.7 | n/a | 224.6 | 7.71 | 19.32 | 3.7 GiB | 62279 MiB | 3.27 |
| hybrid | adapter | 5 | 40 | 40 | 0 | 0 | 512.9 | 893.5 | n/a | 959.6 | 8.31 | 25.88 | 3.7 GiB | 66527 MiB | 3.83 |
| hybrid | adapter | 10 | 40 | 40 | 0 | 0 | 1080.3 | 1818.5 | n/a | 2166.3 | 8.16 | 26.41 | 3.7 GiB | 67316 MiB | 4.58 |
| hybrid_year | adapter | 1 | 40 | 40 | 0 | 0 | 104.3 | 203.8 | n/a | 315.4 | 7.99 | 9.2 | 3.6 GiB | 42173 MiB | 6.23 |
| hybrid_year | adapter | 5 | 40 | 40 | 0 | 0 | 254.9 | 846.7 | n/a | 1009.3 | 13.44 | 23.36 | 3.6 GiB | 34477 MiB | 7.46 |
| hybrid_year | adapter | 10 | 40 | 40 | 0 | 0 | 371.5 | 1087.4 | n/a | 1524.5 | 14.58 | 22.41 | 3.7 GiB | 31412 MiB | 6.17 |
| hybrid_language | adapter | 1 | 40 | 40 | 0 | 0 | 125.3 | 226.7 | n/a | 289.9 | 7.6 | 11.81 | 3.7 GiB | 48931 MiB | 6.69 |
| hybrid_language | adapter | 5 | 40 | 40 | 0 | 0 | 382.5 | 870.6 | n/a | 1083.3 | 10.61 | 26.13 | 3.7 GiB | 49174 MiB | 5.57 |
| hybrid_language | adapter | 10 | 40 | 40 | 0 | 0 | 775.3 | 1255.3 | n/a | 1835.7 | 10.66 | 26.45 | 3.8 GiB | 50777 MiB | 5.38 |
| hybrid_document_type | adapter | 1 | 40 | 36 | 0 | 0 | 14.6 | 1078.5 | n/a | 1102.3 | 5.5 | 5.87 | 3.8 GiB | 15632 MiB | 4.74 |
| hybrid_document_type | adapter | 5 | 40 | 36 | 0 | 0 | 32.5 | 2407.7 | n/a | 2649.6 | 9.71 | 11.81 | 4.0 GiB | 19184 MiB | 4.35 |
| hybrid_document_type | adapter | 10 | 40 | 36 | 0 | 0 | 30.7 | 2140.5 | n/a | 2535.7 | 10.53 | 11.56 | 4.1 GiB | 12797 MiB | 4.49 |
| hybrid_tag | adapter | 1 | 40 | 0 | 0 | 0 | 1.4 | 2 | n/a | 13.3 | 20.49 | 0.04 | 4.1 GiB | 33 MiB | 3.81 |
| hybrid_tag | adapter | 5 | 40 | 0 | 0 | 0 | 1.6 | 3 | n/a | 7.2 | 20.49 | 0.05 | 4.1 GiB | 34 MiB | 2.55 |
| hybrid_tag | adapter | 10 | 40 | 0 | 0 | 0 | 1.3 | 1.9 | n/a | 2 | 20.49 | 0.04 | 4.1 GiB | 0 MiB | 2.73 |
| hybrid_user_collection | adapter | 1 | 40 | 25 | 0 | 0 | 2.3 | 11.5 | n/a | 18.3 | 20.47 | 0.12 | 4.1 GiB | 233 MiB | 4.12 |
| hybrid_user_collection | adapter | 5 | 40 | 25 | 0 | 0 | 2.5 | 11.4 | n/a | 16.5 | 20.47 | 0.32 | 4.1 GiB | 84 MiB | 2.76 |
| hybrid_user_collection | adapter | 10 | 40 | 25 | 0 | 0 | 2.1 | 7.2 | n/a | 104.2 | 20.47 | 0.23 | 4.0 GiB | 151 MiB | 2 |
| bm25_direct | direct | 1 | 40 | 40 | 0 | 0 | 4.1 | 8.6 | n/a | 12.3 | 20.46 | 0.24 | 4.0 GiB | 1110 MiB | 1.09 |
| bm25_direct | direct | 5 | 40 | 40 | 0 | 0 | 4.1 | 9.3 | n/a | 13.2 | 20.47 | 0.26 | 4.0 GiB | 1257 MiB | 0.73 |
| bm25_direct | direct | 10 | 40 | 40 | 0 | 0 | 3.2 | 7.9 | n/a | 196.1 | 20.48 | 0.31 | 4.2 GiB | 661 MiB | 0.82 |
| vector_direct | direct | 1 | 40 | 40 | 0 | 0 | 6.6 | 18.5 | n/a | 28.6 | 20.41 | 0.64 | 4.2 GiB | 2210 MiB | 0.55 |
| vector_direct | direct | 5 | 40 | 40 | 0 | 0 | 6.7 | 10.2 | n/a | 14.8 | 20.44 | 0.62 | 4.2 GiB | 2185 MiB | 0.63 |
| vector_direct | direct | 10 | 40 | 40 | 0 | 0 | 3.1 | 8.5 | n/a | 11 | 20.49 | 0.33 | 4.2 GiB | 987 MiB | 0.51 |
| hybrid_direct | direct | 1 | 40 | 40 | 0 | 0 | 114.2 | 154.6 | n/a | 168.6 | 9.08 | 19.34 | 4.2 GiB | 51089 MiB | 2.97 |
| hybrid_direct | direct | 5 | 40 | 40 | 0 | 0 | 502.4 | 661 | n/a | 875.8 | 9.33 | 26.35 | 3.8 GiB | 58717 MiB | 3.81 |
| hybrid_direct | direct | 10 | 40 | 40 | 0 | 0 | 923.6 | 1544.5 | n/a | 1796.4 | 9.32 | 26.91 | 3.9 GiB | 59553 MiB | 4.1 |
| chunk_context | adapter | 1 | 40 | 40 | 0 | 0 | 223 | 1495.4 | n/a | 2627.1 | 2.36 | 1.11 | 3.8 GiB | 43850 MiB | 3.89 |
| chunk_context | adapter | 5 | 40 | 40 | 0 | 0 | 299.1 | 906.8 | n/a | 4007.5 | 7.07 | 3.75 | 3.8 GiB | 38063 MiB | 2.85 |
| chunk_context | adapter | 10 | 40 | 40 | 0 | 0 | 544.4 | 2661.6 | n/a | 3654.7 | 7.49 | 6.87 | 3.8 GiB | 40772 MiB | 2.27 |
| document_view | adapter | 1 | 40 | 40 | 0 | 0 | 110.6 | 1216.1 | n/a | 2206.5 | 3.34 | 0.86 | 3.8 GiB | 37553 MiB | 2.24 |
| document_view | adapter | 5 | 40 | 40 | 0 | 0 | 188.3 | 914.3 | n/a | 2588.1 | 11.76 | 3.19 | 3.7 GiB | 35412 MiB | 2.4 |
| corpus_overview | adapter | 1 | 40 | 0 | 0 | 0 | 468.2 | 488 | n/a | 492 | 2.13 | 6.36 | 3.7 GiB | 640 MiB | 2.2 |
| corpus_overview | adapter | 5 | 40 | 0 | 0 | 0 | 1480.6 | 1595.7 | n/a | 1610.7 | 3.15 | 10.89 | 3.7 GiB | 0 MiB | 0.33 |
| mixed | mixed | 1 | 40 | 37 | 0 | 0 | 71.4 | 360.3 | n/a | 495.2 | 8.67 | 6.78 | 3.7 GiB | 28594 MiB | 1.81 |
| mixed | mixed | 5 | 40 | 38 | 0 | 0 | 149.7 | 1369.5 | n/a | 3868.7 | 8.91 | 10.75 | 3.7 GiB | 33313 MiB | 2.37 |
| mixed | mixed | 10 | 40 | 37 | 0 | 0 | 128.3 | 897.8 | n/a | 2245.4 | 10.39 | 9.78 | 3.7 GiB | 23693 MiB | 1.96 |
| self_recall | direct | 1 | 100 | 0 | 0 | 0 | 6 | 8.2 | 13.7 | 13.9 | 20.17 | 0.57 | 3.7 GiB | 5060 MiB | 1.6 |

Self-recall `self_recall`: own chunk in top-10 for 0/100 sampled chunks.

**No request returned results in `hybrid_tag`: these timings are not representative of the scenario (for example a filter that matches nothing).**

Scenarios: `bm25` — Search page, keyword mode (app adapter, document reference returned); `vector` — Search page, vector mode; `hybrid` — Search page default and RAG retrieval (hybrid, alpha 0.5, 10 chunks); `hybrid_year` — Hybrid + chunk yearIssued range filter; `hybrid_language` — Hybrid + chunk language filter; `hybrid_document_type` — Hybrid + documentType filter through the document reference; `hybrid_tag` — Hybrid + chunk tag reference filter (automatic or positive); `hybrid_user_collection` — Hybrid within a user collection (reference filter); `bm25_direct` — BM25 without references (database-level); `vector_direct` — near_vector without references; `hybrid_direct` — Hybrid without references; `chunk_context` — Two chunks before and after a chunk (span chat / context); `document_view` — Document view: all chunks of a document with collection membership; `corpus_overview` — Corpus overview aggregates over Documents (uncached); `mixed` — Interleaved user-like mix; `self_recall` — Recall check: each sampled chunk in the top 10 for its own vector
