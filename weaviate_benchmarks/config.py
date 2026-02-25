"""
Configuration for Weaviate benchmarks.
All connection parameters can be overridden via environment variables.
"""

import os

# ── Weaviate connection ─────────────────────────────────────────────────────
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_REST_PORT = int(os.getenv("WEAVIATE_REST_PORT", 8080))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", 50051))

# ── Benchmark identifiers (used as prefixes so cleanup is safe) ─────────────
BENCH_PREFIX = "__bench_"  # all benchmark-created objects use this prefix

# ── Benchmark parameters ────────────────────────────────────────────────────
# Concurrency levels to sweep
CONCURRENCY_LEVELS = [1, 2, 4, 8, 16, 32]

# Number of operations per measurement point
OPS_PER_MEASUREMENT = 50

# "Fullness" levels: how many tags / collections are attached to each chunk
# before we measure the *next* operation
FULLNESS_LEVELS = [0, 5, 10, 20, 50]

# How many chunks to pick for reference-attachment benchmarks
CHUNK_SAMPLE_SIZE = 20

# Output directories
RESULTS_DIR = os.getenv("BENCH_RESULTS_DIR", os.path.join(os.path.dirname(__file__), "results"))
PLOTS_DIR = os.getenv("BENCH_PLOTS_DIR", os.path.join(os.path.dirname(__file__), "plots"))
