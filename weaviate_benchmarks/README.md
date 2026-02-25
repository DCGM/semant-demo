# Weaviate Benchmarks

Self-contained benchmark suite for measuring Tag and UserCollection operation
latencies and throughput against a live Weaviate instance with real data.

**The benchmarks do NOT modify existing data.** All benchmark-created Tags and
UserCollections use a `__bench_` prefix and are fully cleaned up at the end of
each run (and before the next run starts).

## Quick start

```bash
cd weaviate_benchmarks
pip install -r requirements.txt

# Run all benchmarks (Weaviate must be reachable at localhost:8080 / 50051)
python -m weaviate_benchmarks

# Or run individually
python -m weaviate_benchmarks --tags     # tag benchmarks only
python -m weaviate_benchmarks --cols     # collection benchmarks only
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
- `CONCURRENCY_LEVELS` — concurrency sweep values
- `OPS_PER_MEASUREMENT` — operations per data point
- `FULLNESS_LEVELS` — number of existing refs per chunk
- `CHUNK_SAMPLE_SIZE` — chunks used for reference benchmarks

## What is benchmarked

### Tag operations
| Benchmark | Conditions varied |
|-----------|-------------------|
| Single insert | — |
| Concurrent insert | concurrency: 1–32 |
| Batch insert | — |
| Fetch all (prefix filter) | — |
| Fetch by ID | — |
| Fetch compound filter | — |
| Fetch `contains_any` | batch size |
| Reference add to chunk | fullness: 0–50 existing refs |
| Reference add to chunk | concurrency: 1–32 |
| Reference remove from chunk | — |
| Single delete | — |
| Batch delete (`delete_many`) | — |
| Chunk query by tag ref (`fetch_objects`) | — |
| Chunk query by tag ref (`bm25`) | — |
| Chunk query by tag ref (ID + ref filter) | — |

### UserCollection operations
| Benchmark | Conditions varied |
|-----------|-------------------|
| Single insert | — |
| Concurrent insert | concurrency: 1–32 |
| Batch insert | — |
| Fetch by user ID | — |
| Fetch by ID | — |
| Fetch name + user filter | — |
| Fetch `contains_any` | batch size |
| Reference add to chunk | fullness: 0–50 existing refs |
| Reference add to chunk | concurrency: 1–32 |
| Reference remove from chunk | — |
| Single delete | — |
| Batch delete | — |
| Chunk query by collection ref (`fetch_objects`) | — |
| Chunk query by collection ref (name filter) | — |
| Chunk query by collection ref (ID + ref filter) | — |

## Reported metrics

For each benchmark point:
- **Mean** latency (ms)
- **Median** latency (ms)
- **P90** latency (ms)
- **P99** latency (ms)
- **Throughput** (ops/sec)

## Output

- `results/*.json` — raw benchmark data
- `plots/*.png` and `plots/*.svg` — charts

## Cleanup guarantee

Every benchmark function creates data with a `__bench_` prefix and cleans up
after itself. A safety cleanup also runs before and after the full suite.
The only Weaviate collections touched are `Tag`, `UserCollection`, and `Chunks`
(reference properties only). No chunk content or document data is ever modified.
