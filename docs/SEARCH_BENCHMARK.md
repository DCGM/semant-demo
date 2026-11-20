# Search relevance benchmark (#712)

A reproducible benchmark of semANT passage retrieval: a frozen dataset of real corpus chunks,
information needs phrased in Czech, English and German, and graded relevance judgements
(qrels), searched in a Weaviate owned by the benchmark with configurable embedding models and
search settings, and reported offline.

| Stage | Issue | Command | Reads | Writes |
|---|---|---|---|---|
| Generator | [#726](https://github.com/DCGM/semant-demo/issues/726) | `python -m semant_demo.benchmarks.search_relevance.generate` | a semANT store (read only), models | a **dataset** directory |
| Dataset v1 | [#730](https://github.com/DCGM/semant-demo/issues/730) | the generator, run once and frozen | production (read only) | dataset `v1`, outside Git |
| Runner | [#727](https://github.com/DCGM/semant-demo/issues/727) | `python -m semant_demo.benchmarks.search_relevance.runner` | a dataset, embedding endpoints | a **run** directory |
| Reports | [#728](https://github.com/DCGM/semant-demo/issues/728) | `python -m semant_demo.benchmarks.search_relevance.report` | datasets and runs | Markdown, plots, JSON/CSV |

The stages are separate commands that exchange only the files below
(`semant_demo/benchmarks/search_relevance/contracts.py`). None imports another stage, and none
builds on a maintenance tool (`chunk_ingest`, `data_tools/embedder`, `db_benchmark`). They share
only libraries: `LlmGateway`, the passage search (`features/search/service.py`), the embedding
clients, `connect_weaviate`, `CollectionNames` and `Config`, and the benchmark's own
`contracts`, `store_api`, `llm` and `languages` modules.

Production-derived corpus text, queries and grades stay **outside Git**. The tests use the
synthetic fixture `tests/search_benchmark_fixture.py`
(`python -m tests.search_benchmark_fixture OUT` writes it).

## Dataset

```text
dataset/
  manifest.json   identity, provenance, file hashes and counts, pooling methods, judges, limitations
  corpus.jsonl    CorpusChunk: one sampled chunk per line, with its text
  intents.jsonl   Intent: an information need, its style and source chunk(s)
  queries.jsonl   Query: one formulation of an intent in one language
  qrels.jsonl     Qrel: the graded relevance of a chunk to an intent
```

| Record | Fields |
|---|---|
| `CorpusChunk` | `chunk_id`, `document_id`, `order` (as in the source corpus), `language` (ISO 639-3), `text`, `title` (the chunk's, if any), `document` (`title`, `year`, `document_type`), `attributes` (sampling and slicing values: `stratum`, `period`, `ocr_quality`, `context_of`, …) |
| `Intent` | `intent_id`, `style` (`keywords`, `question`, `entity`, …), `need` (the information need in a sentence; what the judge grades against), `source_chunk_ids`, `source_language`, `origin` (`generated`, `imported`) |
| `Query` | `query_id`, `intent_id`, `language`, `text`, `origin` (`generated`, `translated`, `imported`), `translated_from` |
| `Qrel` | `intent_id`, `chunk_id`, `grade` (0 not relevant, 1 partly, 2 relevant), `judge` (a judge id of the manifest), `pooled_by` (pooling method ids; `source` for a source chunk), `language_grades` (when judged per query language), `consistent` (false when those disagree) |

Grades belong to an **intent**: its translations share them. When the generator judges
per query language, `language_grades` keeps those grades, `grade` is their documented aggregate
and `consistent: false` marks a disagreement.

The manifest (`DatasetManifest`) holds `schema_version` (`search-benchmark-dataset/1`),
`dataset_id`, `version`, `created`, the generator and its configuration with its SHA-256,
`seeds`, `source` (never a credential), `languages`, `styles`, model provenance by role,
`pooling` methods, `judges`, the `store_schema` pooled in, `files` (SHA-256 and record count of
each file), `counts`, automated `checks` and `limitations`.

## Run

```text
runs/<run_id>/
  manifest.json   the dataset (id, version, manifest SHA-256), configurations, environment, file hashes
  results.jsonl   RunResult: the ranked chunks of one query in one configuration
```

A `RunConfiguration` names its `mode` (`text`, `vector`, `hybrid`), `alpha` and `fusion`
(`relativeScore`, `ranked`) for hybrid, the `vector` searched (`VectorSpec`: model, named
vector, query prefix, document template), the BM25 `properties` with boosts and the `depth`
kept. A `RunResult` has the `hits` (chunk id and score, best first, each chunk once), the query
embedding and search times in milliseconds, or an `error` (a class or short reason, never text)
and no hits. `environment` records the git revision, Weaviate version, store schema and
embedding endpoints.

## Guarantees

- Every file is written before its manifest, and the manifest names each file's SHA-256 and
  record count: a directory without a manifest is incomplete, and a file changed afterwards is
  refused when it is loaded (`load_dataset`, `load_run`).
- Records are validated when written and read; unknown fields are refused, so a newer schema
  needs newer code.
- A dataset is referentially complete: every source chunk, graded chunk and query intent exists,
  every intent has a query, every source chunk is graded, each (intent, chunk) is graded once,
  and every judge and pooling method is declared.
- A run names the exact dataset manifest it ran on; loading it with another version, or with a
  dataset changed since, is refused.

## Benchmark store

`store_api.py` declares the Weaviate the generator pools in and the runner searches: owned by the
benchmark (an ownership marker and token; it never drops, resets or writes to another
instance), the application's collections, one dataset's corpus with its original ids, one named
vector per model with document embeddings cached on disk, and the application's own passage
search per configuration (fusion type and BM25 properties included). The schema is the test
schema's shape, not production's exact one (#128); `describe()` records it in the manifests.

## Reports

`semant_demo/benchmarks/search_relevance/report.py` (#728) renders reports from a dataset and
saved runs only: no Weaviate, model or network. Plots need `matplotlib` (a development
dependency, `requirements-dev.txt`).

```sh
cd semant_demo_backend
python -m semant_demo.benchmarks.search_relevance.report report \
    --dataset DATASET --run RUN [--run RUN2 ...] --out OUT [--exclude-inconsistent] [--examples 2]
python -m semant_demo.benchmarks.search_relevance.report compare \
    --dataset DATASET --run RUN [--run RUN2] --a CONFIG --b CONFIG --out OUT
```

Every run must be of exactly the dataset given (id, version and manifest SHA-256); another is
refused. A configuration is named by its id, or `run_id/configuration_id` when several runs
share an id. `--bootstrap N` (default 2000, 0: no CIs) and `--seed` (default 728) set the
bootstrap; the same inputs and seed give the same numbers.

- `report` writes `report.md` (summary, a conclusions placeholder for the reviewer,
  provenance, configurations, metric definitions, overall table with CIs, the query language ×
  source language matrices, same/cross language, query style, source chunk properties such as
  `ocr_quality` or a chunk title, latency, best and worst examples, limitations),
  `plots/*.png|svg` (nDCG@10 by configuration, language matrices, latency), `report.json`
  (everything), `summary.csv` (every slice and metric), `queries.csv` (every query's status and
  metrics) and `latency.csv`.
- `compare` writes `comparison.md`, `comparison.json`, `comparison.csv` and plots: A and B side
  by side with the delta B − A and its paired CI, overall and per slice, sample sizes, judged
  coverage and the latency trade-off.

The reports quote corpus text in their examples: write production-derived reports outside Git.

### Metrics

A query is scored against the qrels of its intent (its translations share them; the shared
`grade` is used also when `consistent` is false).

| Metric | Definition |
|---|---|
| nDCG@10 (primary) | DCG of the top 10 with gain 2^grade − 1 and discount log2(rank + 1), over the DCG of the ideal ranking of **all** the intent's qrels |
| P@10, P@10 (grade 2) | share of the 10 slots holding a chunk graded ≥ 1 (≥ 2); missing slots count as misses |
| Hit@10 (source) | 1 when one of `Intent.source_chunk_ids` is in the top 10 |
| Recall@20, Recall@50 | share of the intent's judged relevant chunks (grade ≥ 1) in the top 20 / 50 |
| unjudged@10 | share of the returned top-10 chunks without a qrel for the intent |

An intent without a relevant qrel has no nDCG, P or recall, and one without a source chunk no
Hit@10; those values are left out of the means and counted. Failed searches
(`RunResult.error`) and queries missing from a run are counted per configuration and left out
of the means. A query is scored with its own language's grade where a qrel was judged per query
language, otherwise with the intent's `grade`; the examples show the same grades.
`--exclude-inconsistent` leaves out intents with a `consistent: false` qrel; the report always
says how many such intents there are and how many were left out.

**Unjudged results.** Pooled, LLM-judged qrels are incomplete. The **standard** variant
(primary) counts an unjudged chunk as not relevant, a lower bound; the **condensed** variant
removes unjudged chunks from the ranking before scoring (and tends to overestimate). Both are
reported with the unjudged rate, which shows how much a score may be understated.

**Uncertainty.** A mean is over the scored queries. Its 95% CI is a percentile bootstrap that
resamples **intents** with replacement, keeping all formulations of an intent together, since
its translations are not independent. `compare` pairs the queries both configurations scored
and bootstraps the mean delta over the same resampled intents. Latency is reported as p50 and
p95 of `embed_ms`, `search_ms` and their sum over successful searches; it is measured on the
benchmark's isolated store and does not predict production-scale latency.
