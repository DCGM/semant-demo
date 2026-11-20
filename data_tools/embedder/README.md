# semantembedder

`semantembedder` is a configurable pipeline that computes embeddings of Weaviate records (e.g. text chunks) with your own embedding model served through an OpenAI-compatible API (vLLM) and stores them in the database as a **named vector**.

Each record lists its stored named vectors in the `haveVector` property (#805). A run embeds only the records whose list lacks the vector's name and adds the name with the vector, so it is resumable: you can interrupt it at any time (Ctrl+C, crash, lost connection) and simply run it again to continue.

## Installation

```bash
pip install -e .
```

## Features

- **Selection by `haveVector`** (#816): a run reads only the records whose list lacks the vector's name (`contains_none`), so embedding a few new records does not read the whole collection. A selected record that already stores the vector only gets the name, without an embedding request.
- **Asynchronous**: Several embedding requests run concurrently (`max_concurrent_requests`). Database reading, embedding and writing overlap.
- **Safe writes**: Each vector is written with its name added to `haveVector` in one PATCH update, several at once. Other properties, references, vectors and listed names of the record are kept.
- **On-the-fly vector creation**: If the named vector doesn't exist, it is added to the collection schema as a self-provided vector (vectorizer `none`) with the configured index type and distance metric.
- **Templated input**: The embedded text is a Jinja2 template over the record fields, which is also useful for instruction prefixes (e.g. `passage: {{ text }}`).
- **Configured via YAML**: Uses the `classconfig` library, the same as `semantmetaenricher`.

## Quick Start

1. Start your embedding model with vLLM. Configuration used during development:
   ```bash
   vllm serve \
    --model Qwen/Qwen3-Embedding-0.6B \
    --runner pooling \
    --host 0.0.0.0 \
    --port 10435 \
    --max-model-len 32768 \
    --max-num-batched-tokens 32768 \
    --gpu-memory-utilization 0.8
   ```
2. Generate a template configuration file (or edit the provided `config.yaml`):
   ```bash
   python run.py --init config.yaml
   ```
3. Edit `config.yaml`: set the Weaviate connection, the collection, `vector_name`, and the embedder `base_url`, `model_name` and `input_template`.
4. Run the pipeline, confirming the Weaviate endpoint of the config (`weaviate_host:weaviate_port`):
   ```bash
   python run.py config.yaml --confirm-endpoint localhost:8080
   ```
   Run the same command again to continue after an interruption.

Every run writes (the vectors, and the schema with `create_vector`), so a pipeline run and
`--create-test-collection` are refused with exit code 2, before connecting, unless
`--confirm-endpoint HOST:PORT` equals the configured endpoint. This holds for `localhost`
too: the production backfill reaches its Weaviate as `localhost` on the server.
`--init` needs no confirmation.

To see what a run would do first, add `--check`: it reads the records a run would select and
prints how many it would embed, how many already store the vector (a run only adds the name)
and how many have an empty input, without changing the schema, sending embedding requests or
writing. It reads the selected records like a run, but since it writes nothing, beyond
`max_excluded` of them it reads the rest with the cursor (see *How it works*). Exit code 0 when a run
would write nothing, 1 when it would, 2 when the check fails (e.g. a missing collection) or a
run would be refused (`haveVector` missing or declared otherwise, or the vector missing and
`create_vector` disabled, even in an empty collection). A check that a run would refuse says
why and stops without reading the records, so it prints no counts. `max_records` does not limit it. Since it only reads, `--check` needs no `--confirm-endpoint` and ignores one
given, like the read-only modes of the maintenance commands.

```bash
python run.py config.yaml --check
```

To try it out, you can create a small `EmbedderTest` collection (it uses the connection from the config):

```bash
python run.py --create-test-collection config.yaml --confirm-endpoint localhost:8080
```

Without a config it uses `localhost:8080`, which has to be confirmed the same way.

An existing `EmbedderTest` collection is refused and left unchanged; add `--force` to delete it and create it again.

## Using the vector in the application

The application never creates or fills vectors; it queries the ones listed in
the file of `SEARCH_VECTORS_CONFIG` (#217; default
`semant_demo_backend/semant_demo/configs/search_vectors_qwen.yaml`).
After a run has filled the vector for the whole collection, add an entry there:

- `target_vector`: this tool's `vector_name`;
- `embedding.provider: openai` with the same `base_url` and `model` (`model_name` here) and
  the same `dimensions`;
- `query_prefix` / `document_prefix`: what the model expects before a query and a document.
  The documents were embedded with this tool's `input_template`, so the document side must
  match it (e.g. `passage: {{ text }}` here means `document_prefix: "passage: "`).

Search and RAG name a target vector in every vector and hybrid query, so adding a vector does
not break the existing ones. Until a vector is listed, it is unused.

`config.qwen.yaml` is the template of the production backfill of the Qwen vector (#385):
it writes `Qwen3_Embedding_0_6B` into `Chunks_test` through the embedding service of
`deploy/docker-compose.embedder.yml`, truncating chunks to the server's 2048 tokens.

**Production.** Adding a vector rewrites every chunk object and needs memory for another
vector index (see `docs/WEAVIATE_AUDIT_2026-10.md`, *Named vectors*). Do not add one to the
production `Chunks` collection before its current vector index is complete (#375) and the
memory is reserved, and only with the operator's approval. Try it on a copy or a test store
first; `create_vector: true` adds the vector to the configured collection on the first run.

## How it works

1. The collection must declare `haveVector`; otherwise the run is refused before any change. The named vector is created in the schema if it's missing (`create_vector`).
2. The run reads again and again the first `scan_batch_size` records with `haveVector contains_none([name])`, with their properties and the target vector. A record written leaves the selection; the records read and not yet written (being embedded or written, or with an empty input) are left out of the next query by id (`by_id().contains_none`). A record that already stores the vector gets only the name before the next query. Weaviate's cursor (`after`) cannot be combined with a filter, and keyset paging (sorted by `_id`) costs minutes a page when most records are selected (measured in #816). On an older copy of production (8.3 M chunks, Weaviate 1.34) a query took about 0.06 s with nothing left out and 0.15 s with 5000 ids left out.
   When more than `max_excluded` ids would be left out (many empty inputs, or `--check`, which writes nothing), the rest is read with the cursor: `scan_batch_size` ids and `haveVector` lists per request, and the records of each page lacking the name again by id (`by_id().contains_any`) with their properties and the vector. On the copy that reads the whole collection in about 18 minutes, against about 31 for reading every record with the vector.
3. The texts are rendered with `input_template` and sent in requests of `embed_batch_size` texts to the embedder, with up to `max_concurrent_requests` requests in flight. Records whose rendered text is empty are skipped; they stay selected and every run reports them.
4. Each embedding is written with the extended `haveVector` list in one PATCH update, with up to `max_concurrent_writes` updates at once. A list read as absent or `null` counts as empty.

The progress bar counts the records done; it has no total, since counting the selection costs minutes on a large collection (measured in #816). The counters show how many records were embedded in this run, already stored the vector, or had empty input.

The remaining counters show where records are waiting right now, which helps to find the bottleneck:

- `queued`: records waiting in the queue for an embedding request. It stays near its maximum (`2 × max_concurrent_requests × embed_batch_size`) when the embedder is the bottleneck, and near zero when reading the database is.
- `embedding`: records in running embedding requests, at most `max_concurrent_requests × embed_batch_size`.
- `writing`: records whose embeddings are being written to the database. If it stays high, the database writes are the bottleneck (try a higher `max_concurrent_writes`).

## Configuration Schema

- Connection properties: `weaviate_host`, `weaviate_port`, `weaviate_grpc_port`, `weaviate_api_key`, `weaviate_headers`
- Database collection target: `collection`
- Target vector: `vector_name`, `create_vector`, `vector_index_type` (`hnsw`, `flat`, `dynamic`), `distance_metric` (`cosine`, `dot`, `l2-squared`, ...). The index type and metric are used only when the vector is created.
- Record selection: `return_properties` (fields available in the template; default is all), `max_records` (limit per run)
- Execution: `scan_batch_size`, `max_excluded` (default 5000; ids left out of the selection query before the run reads the rest with the cursor), `embed_batch_size`, `max_concurrent_requests`, `max_concurrent_writes`, `max_retries`, `retry_delay`
- Embedder: `embedder` (select `VLLMEmbedder` via the `cls` field)
  - `base_url`, `api_key`, `model_name`
  - `input_template`: Jinja2 template of the embedded text
  - `dimensions`: output dimension for Matryoshka models
  - `truncate_prompt_tokens`: vLLM option that truncates too long inputs instead of failing
  - `extra_body`: any additional request parameters
  - `timeout`, `max_retries`: request timeout and retries (with exponential backoff)

A new embedder backend can be added by subclassing `Embedder` and implementing `render` and `embed_batch`.

## Important notes

- **The collection must declare `haveVector`** (`text[]`, `field` tokenization, filterable, not searchable), and the records that already store the vector must list it, or they are embedded again. The backend's `chunk_have_vector` declares and fills it (`docs/DATA_MAINTENANCE.md`, #805); it ran on the shared test store and production on 2026-11-19. A local development store seeded before #816 has no `haveVector`: `make dev-reset CONFIRM=yes` reseeds it, or `chunk_have_vector --write` once per vector declares and fills it. `--create-test-collection` declares it.
- **One run per collection at a time.** A write replaces the whole `haveVector` list, so concurrent runs for different vectors (or `chunk_have_vector`) can drop each other's names.

- **The collection must use named vectors.** Weaviate can add a named vector only to a collection that was created with named vectors. A collection with the legacy unnamed vector (for example, one created by an older server without `vector_config`) is refused with an error and has to be migrated first. Weaviate ≥ 1.34 creates collections without a vector config as a named vector called `default`.
- **Queries must name their target vector once a collection has more than one vector.** `near_vector` and `hybrid` without `target_vector` fail with `class ... has multiple vectors, but no target vectors were provided`. Inserting with an unnamed vector fails as well. The application does both since #217; other scripts that query or insert chunk vectors must use `target_vector="default"` and `vector={"default": ...}` for the original vector.
- A request that keeps failing (e.g. an input longer than the model's context) stops the pipeline. Set `truncate_prompt_tokens`, or fix the record, and run again.

## Tests

`semant_demo_backend/tests/integration/test_embedder_tool.py` runs the pipeline against the
test-owned Weaviate (`make test-integration`, and in CI) with a fake OpenAI-compatible
endpoint: vector creation, preservation of properties, references and other vectors,
resuming, write failures, refused collections (also without `haveVector`), the guarded test
collection, Search over the filled vector, the read-only `--check` and the selection by
`haveVector` (only records lacking the name are read, empty inputs beyond `max_excluded` are
read with the cursor, a stored vector gets only the name, a chunk inserted by `chunk_ingest` is
embedded). `semant_demo_backend/tests/test_embedder_cli.py`
(fast, no Weaviate) covers the endpoint confirmation of the CLI. The tool's dependencies are part of the
backend's development lock.
