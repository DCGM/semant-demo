# semantmetaenricher

`semantmetaenricher` classifies text chunks in Weaviate: it runs the chunks that await classification through a model (a local Hugging Face multitask classifier or any OpenAI-compatible API), writes the classification fields they are missing and records which model classified them.

A run selects only chunks whose `classification_provenance` is `UNPROCESSED` (#590). `chunk_ingest` marks every chunk it inserts that way; chunks stored before the property was declared have no value and are never selected. After a successful classification the chunk's `classification_provenance` is the configured `provenance` identifier. The stored status is the state: interrupt a run at any time and run it again to continue.

## Installation

Activate your Conda environment and install the package in editable mode:

```bash
conda activate semantdemo
pip install -e .
```

## Features

- **Selection by status**: only `UNPROCESSED` chunks, optionally narrowed by `filters` (never on a mapped field or `classification_provenance`). Each page is the first page of what is left (no offset), so no chunk is skipped and no query reaches Weaviate's `QUERY_MAXIMUM_RESULTS`.
- **Missing fields only**: the model is asked only for the mapped fields a chunk is missing (absent, `null` or `[]`). Existing non-empty values are never overwritten.
- **One update per chunk**: the computed fields and the provenance are written together, and only when every missing field got a valid result (a non-empty list of the task's labels). Otherwise nothing is written and the chunk stays `UNPROCESSED` for the next run.
- **Stop on repeated failures**: after `max_consecutive_failures` failed chunks in a row (e.g. an unreachable model) the run stops instead of iterating the whole selection. After `max_failures` failed chunks in total it stops too: the ids of the failed chunks are excluded from every query and listed in the summary, so they must stay few.
- **Read-only schema**: a missing collection, a missing or non-`text[]` mapped field and a missing `classification_provenance` refuse the run. The schema is never changed; declare `classification_provenance` with the backend's `classification_provenance_schema --apply` ([DATA_MAINTENANCE.md](../../docs/DATA_MAINTENANCE.md#chunk-classification-status-classification_provenance_schema-590)). The collection may be an alias.
- **Local multitask models**: loads the converted ModernBERT multitask classifier and runs only the classification heads mapped in the config.
- **Configured via YAML**: uses the `classconfig` library to validate the configuration on the pipeline class.

## Quick Start

1. Generate a template configuration file (or edit the provided `config.yaml`, or use `--init-wizard`):
   ```bash
   python run.py --init config.yaml
   ```
2. Edit `config.yaml`: the Weaviate connection, the collection, `provenance`, the field-to-task mapping and the model.
3. See what a run would select:
   ```bash
   python run.py config.yaml --check
   ```
4. Run the pipeline, confirming the Weaviate endpoint of the config (`weaviate_host:weaviate_port`):
   ```bash
   python run.py config.yaml --confirm-endpoint localhost:8080
   ```
   Run the same command again to retry the chunks that failed.

A run writes, so a pipeline run and `--create-test-collection` are refused with exit code 2,
before connecting, unless `--confirm-endpoint HOST:PORT` equals the configured endpoint. This
holds for `localhost` too: a production store is reached as `localhost` on its server.
`--init`, `--init-wizard` and `--convert-ckpt` need no confirmation.

`--check` only reads: it checks the configuration and the schema and counts the `UNPROCESSED`
chunks a run would select (with the `filters`). It loads no model and needs no
`--confirm-endpoint`.

Both print a JSON summary: the resolved `collection`, `provenance`, `selected` (at the start),
`classified`, `filled` (fields written), `failed` (ids of the chunks that failed in this run),
`remaining` (`UNPROCESSED` chunks matching the filters at the end), `stopped` and `refused`,
and for a run the model's fingerprint (`model`). Exit code 0 when nothing selected is left
`UNPROCESSED`, 1 when chunks remain (failures, the stop, `max_records`, a check with chunks
pending), 2 when refused (endpoint, configuration, schema, a mapped task the model does not
know). An exception during a run (e.g. the model crashes) exits 1.

To try it out, create a small `MetaDataEnrichmentTest` collection (the default `collection` of
`config.yaml`) with 10 Czech historical records, the mapped fields and
`classification_provenance`, every record `UNPROCESSED`. It uses the connection and
`field_tasks` from the config:

```bash
python run.py --create-test-collection config.yaml --confirm-endpoint localhost:8080
```

Without a config it uses `localhost:8080`, which has to be confirmed the same way, and all
tasks. An existing `MetaDataEnrichmentTest` collection is refused and left unchanged; add
`--force` to delete it and create it again.

## Provenance

`provenance` is required and is written to `classification_provenance` of every classified
chunk. It identifies the model and its version, so change it whenever the model, its classes
or its prompts change. `UNPROCESSED` and empty values are refused. The shipped `config.yaml`
uses `mmbert-multitask-2026-07-15`, the converted mmBERT multitask model named by its
earliest known copy (2026-07-15).

The identifier is not checked against the model. The run summary therefore records what
actually ran (`model`): for `LocalHFClassifierModel` the SHA-256 of every file in
`model_path` with the input prompt and threshold, for `APIModel` the endpoint, model name,
sampling settings and the SHA-256 of the prompt templates and classes. Keep the summaries of
runs on shared stores.

## Configuration Schema

The configuration file is a flat YAML file mapped directly to the `EnrichmentPipeline` class parameters:

- Connection properties: `weaviate_host`, `weaviate_port`, `weaviate_grpc_port`, `weaviate_api_key`, `weaviate_headers`
- Database collection target: `collection` (a collection or an alias)
- `provenance`: the model/version identifier (see above)
- Data mapping: `field_tasks`, a dict mapping Weaviate field names (declared as `text[]`) to classification tasks
- Selection and execution: `filters`, `batch_size`, `max_records` (limit per run), `max_consecutive_failures`, `max_failures`, `max_retries`, `retry_delay` (database updates)
- Model definition: `model` (select `LocalHFClassifierModel` or `APIModel` via the `cls` field). `APIModel` treats a failed request, an unrenderable prompt or a refusal as no result, so the chunk is not written.

## Tests

`semant_demo_backend/tests/integration/test_classifier_tool.py` runs the pipeline against the
test-owned Weaviate (`make test-integration`, and in CI) with a fake model: the selection by
status, missing-only filling, invalid results, paging past failed chunks, the stop after
consecutive failures, `max_records`, filters, the alias, refusals, the check and the guarded
test collection. `semant_demo_backend/tests/test_classifier_cli.py` (fast, no Weaviate) covers
the endpoint confirmation, the exit codes, the provenance validation and the models' failure
results and fingerprints. The local model itself (`torch`) is not part of the tests.
