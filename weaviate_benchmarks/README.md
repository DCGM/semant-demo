# Weaviate Benchmarks

Focused benchmark suite for measuring **tag-reference operations on document
chunks** against a live Weaviate instance with real data.

**The benchmarks do NOT modify existing data.** All benchmark-created Tags use
a `__bench_` prefix and are fully cleaned up at the end of each run (and before
the next run starts).

## Quick start

```bash
cd weaviate_benchmarks
pip install -r requirements.txt

# Run benchmarks (Weaviate must be reachable at localhost:8080 / 50051)
python -m weaviate_benchmarks

# Utility commands
python -m weaviate_benchmarks --plots    # regenerate plots from existing results
python -m weaviate_benchmarks --cleanup  # remove stale benchmark data
```

## Configuration

| Env variable          | Default     | Description              |
|-----------------------|-------------|--------------------------|
| `WEAVIATE_HOST`       | `localhost` | Weaviate host            |
| `WEAVIATE_REST_PORT`  | `8080`      | REST API port            |
| `WEAVIATE_GRPC_PORT`  | `50051`     | gRPC port                |
| `BENCH_RESULTS_DIR`   | `./results` | Where JSON results go    |
| `BENCH_PLOTS_DIR`     | `./plots`   | Where PNG/SVG plots go   |

Tune benchmark parameters in `config.py`:
- `CONCURRENCY_LEVELS` — concurrency sweep values (default: 1, 2, 4, 8, 16, 32)
- `OPERATION_COUNT` — refs inserted / deleted per measurement (default: 50)
- `FULLNESS_LEVELS` — pre-existing refs per chunk (default: 0, 1, 5, 10, 25, 50)
- `CHUNK_SAMPLE_SIZE` — chunks sampled for benchmarks (default: 500)
- `CHUNKS_COLLECTION` — name of the chunks collection (default: `Chunks`)
- `TAG_COLLECTION` — name of the tag collection (default: `Tag`)
- `READ_BATCH_SIZE` — chunks per batch-read call (default: 100)

## What is benchmarked

All benchmarks focus on **tag references to chunks** — the core operation used
when tagging documents. An efficient incremental-fullness flow is used: tags are
inserted once, then references are added incrementally to reach each fullness
level without redundant setup/teardown.

| Benchmark | Conditions varied |
|-----------|-------------------|
| Read chunk with refs (concurrent) | fullness, concurrency |
| Read chunk with refs (batch `contains_any`) | fullness |
| Ref-add concurrent (`reference_add`) | fullness, concurrency |
| Ref-add batch (`reference_add_many`) | fullness |
| Ref-remove concurrent (read-modify-write) | fullness, concurrency |
| Ref-remove batch (read-modify-write) | fullness |

## Reported metrics

For each benchmark point:
- **Mean** latency (ms)
- **Median** latency (ms)
- **P90** latency (ms)
- **P99** latency (ms)
- **Throughput** (chunks/sec) — wall-clock based, counting all concurrent ops

## Output

- `results/tag_benchmarks.json` — raw benchmark data
- `plots/*.png` and `plots/*.svg` — charts
- `report/benchmark_report.tex` — LaTeX report (compile with `latexmk -pdf`)

## Cleanup guarantee

Every benchmark function creates data with a `__bench_` prefix and cleans up
after itself. A safety cleanup also runs before and after the full suite.
The only Weaviate collections touched are the configured Tag and Chunks
collections (reference properties only). No chunk content or document data is
ever modified.
