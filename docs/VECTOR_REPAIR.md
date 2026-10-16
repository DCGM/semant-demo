# Temporary vector-index repair (#375)

This is a **best-effort, short-lived repair** for the existing 3,584-dimensional
`Chunks_test` / `default` index. The embeddings and indexes will be replaced soon.
It is **not** necessary to repair all 8.28 million chunks. Do not spend significant
resources perfecting the obsolete index.

## Important limitation

Weaviate supports partial updates of an object's named vector. However, it is
**not established** that an update with *identical* vector values will rebuild a
missing compressed-vector entry on the deployed Weaviate 1.34.4. Do not run the
bulk pass unless a small probe proves that the missing entry becomes searchable.
Updates can also rewrite LSM objects and grow disk use until compaction.

The command only updates stored vectors, not text, metadata or references.
It does not generate embeddings or change schemas or index configuration.

## Run on the host

From `semant_demo_backend/`, with the backend Python 3.12 environment and
the same Weaviate connection settings as the application:

```bash
# PROBE (this performs writes on up to five previously missing objects)
python -m semant_demo.maintenance.vector_repair \
  --confirm-endpoint localhost:8080 --execute \
  probe --report /var/tmp/vector-repair-probe.json

# Only if the probe report says success=true, start 200 objects at a time
python -m semant_demo.maintenance.vector_repair \
  --confirm-endpoint localhost:8080 --execute \
  run --probe-report /var/tmp/vector-repair-probe.json \
      --checkpoint /var/tmp/vector-repair-progress.json --limit 200

# Re-run the same command to resume from the saved cursor.
# Increase --limit to e.g. 2000 per invocation after checking resource use.
```

Use the actual endpoint of production, not necessarily `localhost:8080`.
The supplied endpoint must match the live configuration. Global options appear
*before* the `probe` or `run` subcommand.

The first command probes a handful of vectors that an ID-filtered own-vector
query did not retrieve, then updates the same stored vectors and polls for their
return. If it cannot confirm an improvement, it records a failed report and
**the bulk command refuses to run**. A success is only proof that at least some
previously missing entries became searchable, not that every entry is fixed.

The bulk pass uses cursor pagination over chunk UUIDs, with conservative
defaults: 20 objects/page, 2 concurrent update calls, one second between pages,
200 objects per invocation. At most 10,000 objects can be requested in one
invocation. It uses the stored named `default` vector, not the embedding service.

## Interruption and progress

- **Ctrl-C or stopping the process is acceptable.** The checkpoint advances
  only after an entire page was accepted by Weaviate. An interrupted page may
  be partially updated; the same page will be retried on the next invocation.
- The checkpoint records the endpoint, physical collection, vector name, last
  UUID, scanned/rewritten/skipped counts and update time. Keep it locally;
  never commit it (it contains an internal object ID).
- Accepted vector updates may be queued for asynchronous indexing. Index work
  can continue **after the command stops**; a successful API call does not mean
  the vector is instantly searchable.
- This is **not transactional**: stopping or resuming cannot roll back already
  completed writes. Retain an existing usable recovery point before bulk work.
  No production-sized staging copy or formal downtime window is required.
- If the CLI stops on an error, examine it and run again with the same
  checkpoint. Do not start another instance concurrently against the same
  checkpoint.

## Monitoring and stop conditions

Watch `docker stats`, available RAM, Weaviate OOM/restart events, disk space,
ZFS ARC, CPU, and vector indexing queue length (nodes verbose API).
Do not preemptively cap ZFS ARC; it normally reclaims memory under pressure.
If memory/disk pressure or errors grow, stop between pages and keep the saved
checkpoint. The recently freed 25 GB is additional headroom, not a guarantee.

Before and after a representative number of updates, check whether semantic
retrieval is improving:

```bash
python -m semant_demo.maintenance.db_benchmark inventory \
  --coverage-sample 300 --out /var/tmp/vector-repair-coverage
```

The random coverage check is approximate; small repaired fractions may be below
its resolution. For the probe itself, the saved report records the exact
previously missing objects' retrieval improvements. If the probe is ineffective
or bulk work ceases to be useful, stop and focus on the planned replacement.
