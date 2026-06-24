# semantmetaenricher

`semantmetaenricher` is a fully configurable pipeline tool for enriching metadata in Weaviate database records. It allows you to query records from a local or remote Weaviate database, run them through an AI model (either local Hugging Face Transformers or any OpenAI-compatible API) with custom prompts, and save the generated metadata back into the database.

It also supports creating new fields on-the-fly and custom record filtering.

## Installation

Activate your Conda environment and install the package in editable mode:

```bash
conda activate semantdemo
pip install -e .
```

## Features

- **Select/Filter database records**: Define custom query filters to target specific subsets of records (e.g. only processing records where complexity field is empty).
- **Multitask Field Mapping**: Map multiple Weaviate properties to different classification tasks (e.g. `complexity_field` to the `complexity` task and `emotional_tone_field` to the `emotional_tone` task). Classification for all tasks is computed and written to Weaviate in a single transaction.
- **Local Multitask Models**: Loads the converted ModernBERT multitask classifier model locally and runs only the specific linear classification heads mapped in the config.
- **On-the-fly field creation**: Automatically detects if any of the target database fields are missing in the Weaviate collection and creates them with the appropriate datatypes.
- **Configured via YAML**: Uses the `classconfig` library to auto-validate configurations directly on the execution pipeline class.

## Quick Start

1. Generate a template configuration file:
   ```bash
   python run.py --init config.yaml
   ```
2. Edit `config.yaml` to specify your Weaviate connection, filters, field-to-task mappings, prompts, and model configurations.
3. Run the pipeline:
   ```bash
   python run.py config.yaml
   ```

## Configuration Schema

The configuration file is a flat YAML file mapped directly to the `EnrichmentPipeline` class parameters:

- Connection properties: `weaviate_host`, `weaviate_port`, `weaviate_grpc_port`, `weaviate_api_key`, `weaviate_headers`
- Database collection target: `collection`
- Data mapping: 
  - `field_tasks`: Dict mapping Weaviate field names to classification tasks.
- Filtering and execution: `filters`, `batch_size`, `max_records`
- Model definition: `model` (can select `LocalHFClassifierModel` via the `cls` field)
