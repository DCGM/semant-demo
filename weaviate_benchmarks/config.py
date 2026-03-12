"""
Configuration for Weaviate benchmarks.
All connection parameters can be overridden via environment variables.
"""

import os

# ── Weaviate connection ─────────────────────────────────────────────────────
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_REST_PORT = int(os.getenv("WEAVIATE_REST_PORT", 8080))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", 50051))

# ── Collection names (database-specific) ────────────────────────────────────
CHUNKS_COLLECTION = os.getenv("BENCH_CHUNKS_COLLECTION", "Chunks_test")
TAG_COLLECTION = os.getenv("BENCH_TAG_COLLECTION", "Tag_test")

# ── Benchmark identifiers (used as prefixes so cleanup is safe) ─────────────
BENCH_PREFIX = "__bench_"  # all benchmark-created objects use this prefix

# ── Benchmark parameters ────────────────────────────────────────────────────
# Concurrency levels to sweep
CONCURRENCY_LEVELS = [1, 2, 4, 8, 16]

# Number of references inserted/deleted per measurement point
OPERATION_COUNT = 50

# "Fullness" levels: how many tag references are already attached to each
# chunk before the next measurement round begins
FULLNESS_LEVELS = [0, 5, 10, 20, 50]

# How many chunks to pick for reference benchmarks.
# Chunks are sampled in a shuffled order to avoid database-order bias.
CHUNK_SAMPLE_SIZE = 50

# Maximum batch size when reading chunks (used by batch read test)
READ_BATCH_SIZE = 100

# Output directories
RESULTS_DIR = os.getenv("BENCH_RESULTS_DIR", os.path.join(os.path.dirname(__file__), "results"))
PLOTS_DIR = os.getenv("BENCH_PLOTS_DIR", os.path.join(os.path.dirname(__file__), "plots"))
