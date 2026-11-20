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

`store.py` implements it (`open_store(spec)`):

- **Instance.** With `StoreSpec.host`, that instance; otherwise the container `spec.name` with the
  volume `<name>-data`, both labelled `org.semant.purpose=search-benchmark`, on loopback ports
  (the spec's, or free ones), reused when it exists (`container.py`). A container or volume of
  that name without the label, or with another image, is refused. Nothing deletes it: recreate a
  store with `docker rm -f <name> && docker volume rm <name>-data`.
- **Ownership.** The token is in `spec.token_file` (created with mode 0600); the marker collection
  `SemantSearchBenchmarkStore` holds its SHA-256 and the store's records (dataset, vectors). Only
  an instance without any collection is claimed, and every write checks the marker first.
- **Corpus.** `Chunks` keep the chunk's text, title, order, language and document year, and
  `documentPublic: true` (anonymous search selects it, #793); the page properties a search hit
  requires are made up (a UUID page id, page 1), searchable as in the application's schema so
  BM25 searches the same properties. `Documents` keep title, year and type, `public: true`. The
  store's dataset identity is the dataset id, version and the SHA-256 of `corpus.jsonl`, so the
  generator's corpus-only dataset and the final dataset with the same corpus are one load.
- **Vectors.** `ensure_vector` adds the named vector (self-provided, HNSW, cosine) and embeds
  `VectorSpec.document_template` rendered with `{text}` and `{title}` (the chunk's own title,
  empty without one) through the OpenAI-compatible endpoint, in batches with bounded concurrency
  and retries (transport errors, 429, 5xx). Embeddings are cached in `cache_dir` by (model,
  dimensions, template) and the SHA-256 of the rendered text; only chunks without the vector are
  embedded or written, a failed chunk gets none and is counted by failure class.
- **Search.** `searcher` runs `search_passages` anonymously without filters, with the
  configuration's mode, alpha, fusion, BM25 `properties` (`name^boost`), query prefix and depth
  (the retrieval limit), and reads the first 20 passages in full, as the application's first page.
  Scores are Weaviate's (BM25, hybrid) or the cosine similarity (vector), recorded by the search
  repository's `record_scores` option; `embed_ms` is the query embedding, `search_ms` the rest.

Its integration tests (`tests/integration/test_search_benchmark_store.py`) run against the test
run's throwaway Weaviate, telling `open_store` to tolerate the tests' own marker
(`tolerated_collections`); one test starts its own container when Docker already has the image.

## Runner

`runner.py` (#727) searches every selected query of a frozen dataset with every configuration of
an experiment config in the benchmark store, and writes a run directory:

```sh
cd semant_demo_backend
CONFIG=semant_demo/configs/search_benchmark/runner.example.yaml
python -m semant_demo.benchmarks.search_relevance.runner list-configurations --config $CONFIG
python -m semant_demo.benchmarks.search_relevance.runner run --config $CONFIG --dry-run   # touches no store
python -m semant_demo.benchmarks.search_relevance.runner run --config $CONFIG [--run-id ID] [--out RUNS_DIR] \
    [--configurations ID,...] [--retry-failed]
```

It opens the store, loads the dataset (a no-op when it is loaded), ensures one named vector per
vector used (document embeddings are cached in `cache_dir`; the query prefix never changes them),
then runs the searches with at most `budget.concurrency` in flight and at most `budget.max_qps`
started per second. Each result keeps the hits (truncated to the depth, each chunk once), the
query embedding and search times, or the failure's exception class (never its message or the
query). The manifest's `environment` records the git revision, host, the config file's path and
SHA-256, the store spec and `describe()` (Weaviate version, schema), the embedding endpoints
(the key's variable name, never a key), load and vector reports, the budget, start and end
times, and `sessions`: the environments of earlier sessions of the same run.

### Experiment config

`runner_config.py` defines the fields; `semant_demo/configs/search_benchmark/runner.example.yaml`
is a complete example. Relative paths are relative to the config file; unknown fields are refused.

```yaml
dataset: ~/semant-search-benchmark/datasets/v1
runs_dir: ~/semant-search-benchmark/runs
cache_dir: ~/.cache/semant-demo/search-benchmark/embeddings
store: {name: semant-search-benchmark}          # store_api.StoreSpec
endpoints:                                      # by vector id; a key only by its variable's name
  qwen: {base_url: "http://localhost:8000/v1", api_key_env: null, timeout: 60, batch_size: 32, concurrency: 4}
vectors:                                        # one named vector each
  qwen:
    model: Qwen/Qwen3-Embedding-0.6B
    target_vector: Qwen3_Embedding_0_6B
    document_template: "{text}"                 # another template needs another vector
    query_prefixes: {instruct: "Instruct: ...\nQuery:", none: ""}   # variants of one vector
bm25_properties: {default: null, text-title: {text: 1.0, title: 2.0}}
depth: 100
grid:
  modes: [text, vector, hybrid]
  alphas: [0.25, 0.5, 0.75]
  fusions: [relativeScore, ranked]
  query_prefixes: {qwen: [instruct, none]}      # default: every variant
  properties: [default, text-title]
configurations:                                 # by hand, in addition to the grid
  - {configuration_id: vector.qwen.depth-20, mode: vector, vector: qwen, query_prefix: instruct, depth: 20}
budget: {languages: null, intents: null, max_intents: null, max_queries: null, seed: 0, concurrency: 4, max_qps: 20}
```

Grid configurations get ids from their settings, so adding a value to the grid never renames
one: `text`, `text.b-text-title`, `vector.qwen.p-instruct`,
`hybrid.qwen.a0.5.ranked.p-instruct`, `hybrid.qwen.a0.5.ranked.p-instruct.b-text-title`
(`b-` only for a non-default BM25 property set). The same id with other settings, or the same
settings under two ids, is refused. The budget's subsets are deterministic for a seed: whole
intents first (`intents`, `max_intents`, so translations stay together), then `languages`, then
`max_queries`. Metadata filters are not configurable: the benchmark measures relevance only.

### Incremental runs

A run is identified by its run id (default: the config file's name) under the runs directory.
While it runs, each finished search is appended to `results.partial.jsonl`, and
`run.partial.json` names the dataset and configurations. Running again with the same run id:

- skips every (configuration, query) already in the run or the partial log, so an interrupted
  run resumes where it stopped (a line cut short by the interruption is dropped);
- adds configurations new to the config, or those named with `--configurations`, to the run;
- searches failed queries again only with `--retry-failed`;
- refuses a run (or partial log) of another dataset or dataset version, and a configuration id
  whose settings changed: give a changed configuration a new id, or start a new run.

The run is then written again with all its results through `write_run` (hashes and counts
stay right) and the partial files are removed. Nothing to do opens no store.

### Safety

- The runner reaches Weaviate only through `BenchmarkStore` (`store.open_store`), which writes
  only to an instance holding the benchmark's ownership marker; never point `store.host` at a
  development, test or production instance.
- Keys are given as environment variable names; a missing variable stops the run before the
  store is opened. Neither keys nor query text are written to errors, logs or the manifest.
- Datasets, runs and the embedding cache hold production-derived text: keep them outside Git.
- `--dry-run` and `list-configurations` read only the config and the dataset.
- The tests use a fake store (`tests/test_search_benchmark_runner.py`); they need no Weaviate,
  model or network.
