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
`contracts`, `store_api`, `llm` and `languages` modules. The benchmark changes none of the
application's code: what the application does not offer (hybrid fusion, BM25 boosts, scores,
batched document embeddings) lives in the benchmark package (`search.py`, `embeddings.py`).

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
and `consistent: false` marks a disagreement (exactly then: the contract refuses a `consistent` that
contradicts the per-language grades).

The manifest (`DatasetManifest`) holds `schema_version` (`search-benchmark-dataset/1`),
`dataset_id`, `version`, `created`, the generator and its configuration with its SHA-256,
`seeds`, `source` (never a credential), `languages`, `styles`, model provenance by role,
`pooling` methods, `judges`, the `store_schema` pooled in, `files` (SHA-256 and record count of
each file), `counts`, automated `checks` and `limitations`.

## Generator (#726)

```sh
cd semant_demo_backend
python -m semant_demo.benchmarks.search_relevance.generate budget CONFIG [--work WORK] [--source-* as for run]   # no model call; only the steps run would redo
python -m semant_demo.benchmarks.search_relevance.generate run CONFIG --work WORK [--out DATASET] \
    [--from STEP] [--until STEP] [--force] [--source-host H --source-port P --source-grpc-port G]
python -m semant_demo.benchmarks.search_relevance.generate validate DATASET   # load_dataset + summary
```

One YAML configuration (`benchmarks/search_relevance/config.py`; unknown keys are refused;
example: `semant_demo/configs/search_benchmark_generator.yaml`, the shape of v1) holds the
seeds, sizes, languages, styles and their shares, pooling methods, judge settings and a
`models` catalog in the `ModelCatalog` format declaring `search_benchmark_intents`,
`search_benchmark_translation` and `search_benchmark_judge`. Provider endpoints and keys come
from the environment, as for the backend. The source store is the config's `source`, the
`--source-*` options or the environment (`WEAVIATE_HOST`, …); the options are part of the
`sample` step's inputs, so another store reruns the sampling. The manifest describes the source
by `source.description` and never names its host. A pooling endpoint's `api_key_env` is the
*name* of an environment variable (`[A-Za-z_][A-Za-z0-9_]*`; a pasted key is refused at load),
and `run` refuses (exit 2) to pool while a named variable is not set. A `text` pooling method
takes no `vector` or `endpoint`, and methods sharing a vector `id` must give the same whole
`VectorSpec`. The steps write to the work directory:

| Step | Does | Output (`WORK/<step>/`) |
|---|---|---|
| `sample` | Reads the source store **read only**: language inventory, random-cursor batches after random UUIDs, language-filtered windows for a short language; per language toward its target, round-robin over (period, document type) strata, at most `max_per_document` per document (a language the cap or the strata leave short draws again toward its shortfall, up to 8 rounds within `max_draws`); neighbours of a share of the chunks as context (`attributes.context_of`); near-duplicates kept and marked; mixed/unknown/other languages, short and documentless chunks excluded and counted | `corpus.jsonl` |
| `intents` | Spreads `count` intents evenly over the corpus languages and by style shares; the model writes the `need` (one English sentence) and a query in the source language; a query repeating more than `max_copied_words` consecutive passage words is regenerated once, then the intent moves to a spare chunk. Optional `import` of JSONL intents (`question`/`query`, `language`, optional `corpus_id`, `need`, `style`; e.g. #41), whose source chunks the sample adds (the selected ids are part of the `sample` step's inputs, so a changed file, `limit`, intents seed or query languages resamples; a source chunk without text, document or a usable language is reported in `imported_sources_missing`) | `intents.jsonl`, `queries.jsonl` |
| `translate` | Each query into the other query languages; flags a translation equal to its source, a doubtful language (stopword/diacritic heuristic) and, for `back_translate_fraction`, a low back-translation word overlap; drops an intent missing a language (`require_all_languages`) | `intents.jsonl`, `queries.jsonl` |
| `pool` | Loads the corpus into the benchmark store (`store_api`), ensures the methods' vectors, searches every query with every method; per intent the union with its source chunks, capped (sources kept, then by best rank and number of methods) and fitted to `max_judgments` (refused when the source chunks alone exceed it) | `pools.jsonl` |
| `judge` | Grades every (intent, candidate) 0/1/2 against the need and the source-language query, with the document title and the text cut at `max_chars` (the prompt says so); `per_language_fraction` of intents per query language (`language_grades`, `consistent`; `grade` is their median, the lower one of an even count, or `min`/`source`); every failed judgement (intent, chunk, language) is counted in `failed_judgements`; when only some languages fail, `language_grades`, `grade` and `consistent` cover the judged languages and the pair counts as `per_language.incomplete` (a manifest limitation), except that with `aggregation: source` a pair without its source-language grade is unjudged; unjudged pairs are left out and counted; an intent whose source chunk stays unjudged is dropped; a source graded 0 is flagged | `qrels.jsonl` |
| `write` | `write_dataset` with the manifest (config and SHA-256, git revision, seeds, source, models and prompt versions by role, pooling methods, judge, `store_schema`, checks, usage and limitations) and `summary.md` | `--out` |

Each step records the hash of its inputs (its configuration, models, prompt versions and the
outputs of the earlier steps) in `WORK/<step>/state.json` and is skipped while they and its
outputs are unchanged; `--from STEP` reruns a step and the later ones, `--force` all. Every model
call is cached in `WORK/calls/<feature>.jsonl` by the SHA-256 of its prompt version, model and
messages (a judgement thus by need, query, chunk text and judge), so a rerun asks nothing it
asked before; identical asks in flight at once share one call. `budget --work` counts a step as
done only when `run` would skip it (the same `state.json` check, against the models the
environment and catalog give now, after only up-to-date steps): a changed judge model, for
example, estimates the judge calls again. The work directory and the dataset hold corpus text: keep them outside Git.
Prompts and their versions are in `benchmarks/search_relevance/prompts.py`; changing a prompt
changes its version.

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
  benchmark's `BenchmarkChunkSearch` (`search.py`); `embed_ms` is the query embedding, `search_ms`
  the rest. `BenchmarkChunkSearch` is the application's `ChunkSearchRepository` with only the
  ranking query replaced (adding fusion, BM25 properties and score metadata); the access filter
  and everything else stay the application's. A unit test checks that with default settings it
  sends Weaviate the same query as the application, so a change of the application's ranking
  shows up as a failing test. Document embeddings use the benchmark's batched client
  (`embeddings.py`), query embeddings the application's own client.

Its integration tests (`tests/integration/test_search_benchmark_store.py`) run against the test
run's throwaway Weaviate, telling `open_store` to tolerate the tests' own marker
(`tolerated_collections`); one test starts its own container when Docker already has the image.
