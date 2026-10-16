"""Read-only Weaviate inventory and bounded query benchmark (#374).

Inventory (configuration, counts, vector-index self-retrieval, disk per component, memory,
backups, log signals)::

    python -m semant_demo.maintenance.db_benchmark inventory --container semant-demo-weaviate-1 \\
        --data-dir <data dir> --container-files --out results/inventory

Benchmark a workload profile (``configs/db_benchmark/*.yaml``; default ``baseline``: 1/5/10
concurrent requests, at most 20 request starts per second)::

    python -m semant_demo.maintenance.db_benchmark run --profile baseline \\
        --container semant-demo-weaviate-1 --out results/baseline

Compare two runs, re-render a saved result, or make a copy fit for publication::

    python -m semant_demo.maintenance.db_benchmark compare A.json B.json --out results/compare
    python -m semant_demo.maintenance.db_benchmark report results/baseline.json
    python -m semant_demo.maintenance.db_benchmark sanitize results/baseline.json --out public/baseline

Only queries, aggregates and object reads are sent; nothing is written, no cache is flushed and
no service is restarted. Profiles above the production-safe limits (``profile.SAFE``) are
refused unless ``--allow-heavy`` is given. Results contain no query texts, vectors or object
ids (only keyed hashes for result overlap), host paths or backup ids. The endpoint comes from ``WEAVIATE_HOST`` /
``WEAVIATE_REST_PORT`` / ``WEAVIATE_GRPC_PORT`` or the ``--host``/``--rest-port``/``--grpc-port``
options. See docs/DB_BENCHMARK.md.
"""
