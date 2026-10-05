# semantembedder

`semantembedder` is a configurable pipeline that computes embeddings of Weaviate records (e.g. text chunks) with your own embedding model served through an OpenAI-compatible API (vLLM) and stores them in the database as a **named vector**.

The pipeline is resumable: records that already have the vector are skipped, so you can interrupt it at any time (Ctrl+C, crash, lost connection) and simply run it again to continue.

## Installation

```bash
pip install -e .
```

## Features

- **Resumable**: The collection is scanned in batches and records that already have the target named vector are skipped.
- **Asynchronous**: Several embedding requests run concurrently (`max_concurrent_requests`). Database reading, embedding and writing overlap.
- **Safe writes**: Vectors are written with concurrent PATCH updates that set only the target vector. Properties, references and other vectors of the record are kept.
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
4. Run the pipeline:
   ```bash
   python run.py config.yaml
   ```
   Run the same command again to continue after an interruption.

To try it out, you can create a small `EmbedderTest` collection (it uses the connection from the config):

```bash
python run.py --create-test-collection config.yaml
```

## How it works

1. The named vector is created in the schema if it's missing (`create_vector`).
2. The whole collection is scanned with a cursor (`scan_batch_size` records per request). Each request fetches the properties and the target vector. Records that already have the vector are skipped.
3. The texts are rendered with `input_template` and sent in requests of `embed_batch_size` texts to the embedder, with up to `max_concurrent_requests` requests in flight. Records whose rendered text is empty are skipped.
4. Each embedding is written as a PATCH update of the named vector, with up to `max_concurrent_writes` updates at once.

The progress bar counts all records in the collection. The counters show how many records were embedded in this run, already filled, or had empty input.

The remaining counters show where records are waiting right now, which helps to find the bottleneck:

- `queued`: records waiting in the queue for an embedding request. It stays near its maximum (`2 × max_concurrent_requests × embed_batch_size`) when the embedder is the bottleneck, and near zero when reading the database is.
- `embedding`: records in running embedding requests, at most `max_concurrent_requests × embed_batch_size`.
- `writing`: records whose embeddings are being written to the database. If it stays high, the database writes are the bottleneck (try a higher `max_concurrent_writes`).

## Configuration Schema

- Connection properties: `weaviate_host`, `weaviate_port`, `weaviate_grpc_port`, `weaviate_api_key`, `weaviate_headers`
- Database collection target: `collection`
- Target vector: `vector_name`, `create_vector`, `vector_index_type` (`hnsw`, `flat`, `dynamic`), `distance_metric` (`cosine`, `dot`, `l2-squared`, ...). The index type and metric are used only when the vector is created.
- Record selection: `return_properties` (fields available in the template; default is all), `max_records` (limit per run)
- Execution: `scan_batch_size`, `embed_batch_size`, `max_concurrent_requests`, `max_concurrent_writes`, `max_retries`, `retry_delay`
- Embedder: `embedder` (select `VLLMEmbedder` via the `cls` field)
  - `base_url`, `api_key`, `model_name`
  - `input_template`: Jinja2 template of the embedded text
  - `dimensions`: output dimension for Matryoshka models
  - `truncate_prompt_tokens`: vLLM option that truncates too long inputs instead of failing
  - `extra_body`: any additional request parameters
  - `timeout`, `max_retries`: request timeout and retries (with exponential backoff)

A new embedder backend can be added by subclassing `Embedder` and implementing `render` and `embed_batch`.

## Important notes

- **The collection must use named vectors.** Weaviate can add a named vector only to a collection that was created with named vectors. A collection with the legacy unnamed vector (for example, one created by an older server without `vector_config`) is refused with an error and has to be migrated first. Weaviate ≥ 1.34 creates collections without a vector config as a named vector called `default`.
- **Queries must name their target vector once a collection has more than one vector.** `near_vector` and `hybrid` without `target_vector` fail with `class ... has multiple vectors, but no target vectors were provided`. Inserting with an unnamed vector fails as well. Use `target_vector="default"` and `vector={"default": ...}` in code that uses the original vector.
- A request that keeps failing (e.g. an input longer than the model's context) stops the pipeline. Set `truncate_prompt_tokens`, or fix the record, and run again.
