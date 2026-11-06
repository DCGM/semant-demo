# Generate titles for text chunks (retired)

The export-based scripts of the historical title batch (#80) were retired in #575: their
write-back rewrote chunk `order` and added properties to the schema, and the generation ran
outside the repository's model configuration.

Generate chunk titles with the maintenance command instead:

```bash
cd semant_demo_backend
python -m semant_demo.maintenance.chunk_titles --check check.json \
    --models-config semant_demo/configs/chunk_titles_ollama.yaml
```

It writes only `Chunks.title`, never changes the schema, and is resumable. Its prompt is the
one these scripts used (`chunk-title-v1`). See
[DATA_MAINTENANCE.md](../../docs/DATA_MAINTENANCE.md#chunk-titles-chunk_titles-575) and
`python -m semant_demo.maintenance.chunk_titles --help`. The removed scripts are in the git
history before #575.
