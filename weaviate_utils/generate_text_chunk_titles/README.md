# Generate Titles for Text Chunks

This folder contains a small pipeline for generating short titles for text chunks.

## Workflow overview

1. Export chunk data from Weaviate into `chunks.jsonl`.
2. Build LLM batch requests with `aicaller`.
3. Send batch requests to the API and save generated titles.
4. Merge generated titles back into chunk JSONL files.
5. (Optional) Update Weaviate chunk records with `title` and `order`.

## Prerequisites

- Python environment with dependencies used by the scripts (for example `weaviate-client`, `tqdm`).
- `aicaller` installed and available in `PATH`.
- Access to a running Weaviate instance (for step 1 and optional step 5).
- Configured API endpoint in `api.yaml`.

## 1) Load text chunks from Weaviate

Run `load_text_chunks.py` and redirect output to `chunks.jsonl`:

```bash
python load_text_chunks.py > chunks.jsonl
```

Optional connection args:

```bash
python load_text_chunks.py --host localhost --http_port 8080 --grpc_port 50051 > chunks.jsonl
```

Note: this step is currently used to create `chunks.jsonl`. In the future, the pipeline is expected to consume prepared JSONL files directly.

## 2) Create batch requests for the LLM

Generate `batch.jsonl` from `chunks.jsonl`:

```bash
./create_batch.sh
```

This script uses `create_batch_file.yaml` (model, prompt template, and loader settings).

## 3) Send batch to API

Submit requests and save outputs:

```bash
./send_to_api.sh
```

This script uses:

- `api.yaml` for API settings
- `batch.jsonl` as input
- `api_results.jsonl` as result file
- `api_request.txt` for request/process logs

## 4) Add generated titles to chunk JSONL files

Use `add_title_to_chunks.py` to merge generated titles into document chunk files:

```bash
python add_title_to_chunks.py api_results.jsonl <input_chunks_directory> <output_chunks_directory>
```

Example:

```bash
python add_title_to_chunks.py api_results.jsonl ./chunks_without_titles ./chunks_with_titles
```

Notes:

- Input directory must contain per-document JSONL files (for example `DOC_ID.jsonl`).
- Output directory must be empty or not exist yet.
- Use `--allow_missing_titles` if partial outputs are acceptable.

## 5) Optional: update Weaviate database

If you want to write `title` and `order` back to Weaviate:

```bash
python update_database.py <chunks_with_titles_directory> --chunk-collection Chunks_test
```

Optional connection args:

```bash
python update_database.py <chunks_with_titles_directory> --chunk-collection Chunks_test --host localhost --http_port 8080 --grpc_port 50051
```

This step is optional when you process data as part of a JSONL-based pipeline and do not need immediate DB updates.

## Typical command sequence

```bash
python load_text_chunks.py > chunks.jsonl
./create_batch.sh
./send_to_api.sh
python add_title_to_chunks.py api_results.jsonl <input_chunks_directory> <output_chunks_directory>
# optional:
python update_database.py <output_chunks_directory> --chunk-collection Chunks_test
```

