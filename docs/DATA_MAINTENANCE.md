# Data maintenance

Reviewed, explicitly run commands that audit or correct stored data. Nothing here runs at
application startup, during requests or as part of a deployment.

The commands live in `semant_demo_backend/semant_demo/maintenance/` and run from
`semant_demo_backend/` with the repository `.venv`. Each module docstring (`--help`) is the
authoritative reference for its options, report fields and refusal rules; this page gives
the purpose, the safety requirements and the usual sequence. Detailed notes and the dated
2026 run results are [archived](archive/data-maintenance-2026/RUN_RECORDS.md).

## Safety rules (all commands)

- The default mode only reads. Every write needs a separate, explicit step with
  `--confirm-endpoint HOST:PORT` equal to the configured `WEAVIATE_HOST` /
  `WEAVIATE_REST_PORT` (and to the endpoint recorded in the report or checkpoint).
- Verify the endpoint before running anything that writes. A name such as "test" does not make
  an endpoint safe; the deployed test Weaviate is shared by `test-main` and all PR previews.
- Writing to the shared test or production stores needs explicit authorization for that task.
  Practise on a copy of the development snapshot first (below).
- Back up first (`backup-filesystem` backup or an offline copy); `document_cleanup --delete`
  refuses to run without a verified backup id.
- Run while nothing else writes the affected data (ingestion, metadata edits): the checks and
  the writes are not atomic. Checkpointed runs resume by running the same command again.
- Keep the reports, checkpoints and manifests; record outcomes (counts, backup ids, failures)
  on the GitHub issue or PR, not in these docs.

The scripts in `weaviate_utils/` are older standalone tools; several drop collections or
delete data (for example `db_insert_jsonl.py --delete-old`, `delete_*.py`) and connect to a
hard-coded or configured endpoint. The same rules apply.

## Chunk tag audit (`chunk_tag_audit`)

Compares the chunk `automaticTag` / `positiveTag` / `negativeTag` references with the spans
([ADR 0004](adr/0004-storage-and-annotation-search.md)): `unbacked` references (no matching
span) and `missing` references (a span whose chunk lacks the reference, invisible to
tag-filtered search).

```bash
python -m semant_demo.maintenance.chunk_tag_audit --report chunk_tags.json   # read-only
python -m semant_demo.maintenance.chunk_tag_audit --apply chunk_tags.json \
  --remove-unbacked --confirm-endpoint localhost:8080
```

Add `--add-missing` only when the reviewed repair also needs to create absent references.
Applying re-derives every listed (chunk, tag) pair from the spans stored at that moment.

## Documents without chunks (`document_cleanup`, #281)

Finds documents that no chunk references. `--audit CHECKPOINT` is read-only and resumable; it
writes `CHECKPOINT.candidates.jsonl`, the manifest of candidate UUIDs with their collection ids.
Collection membership does not protect a document; documents created less than
`--min-age-hours` (default 24) before the audit, failed lookups and documents with other
incoming references are never candidates.

```bash
python -m semant_demo.maintenance.document_cleanup --audit audit.json
python -m semant_demo.maintenance.document_cleanup --delete audit.json \
  --confirm-endpoint HOST:PORT --backup-id BACKUP
```

Set the actual endpoint and verified backup id before running; optional `--limit N` and
`--rate N` control the scope and load.
Deleting refuses to start unless the audit finished on the same endpoint and schema, the total
chunk count is unchanged (checked again before every batch) and `BACKUP` holds documents,
chunks and user collections. Each document is re-checked before deletion and read back after;
affected collections are verified at the end. A removed document is restored by importing it
again with the same UUID (`weaviate_utils/db_insert_jsonl.py`); collection memberships are
not restored automatically (the manifest lists them).

## Kramerius metadata sync (`metadata_sync`, #257)

Copies document metadata from the Kramerius PostgreSQL mirror (`meta_records`, maintained
by the `librarymetadata` project) to `Documents`. The field mapping is in
[DATABASE.md](DATABASE.md#document-metadata-from-the-kramerius-mirror).

**Source library only.** Each document takes values only from the mirror row of its own
library, `(id, library)`, never from another library's row. The library comes from, in order:
an approved correction (`--library-override`), a verified map (`--library-map`), chunk
start-page ancestry in the mirror (`--infer-library-from-pages`), the stored `library` (unless
`--distrust-stored`), and, for documents without page evidence, the mirror
(`--infer-library-from-mirror`). Among several candidate libraries, `--prefer-library-with-metadata`
and then `--library-priority` decide. Documents without a decidable library are `unresolved`.
`library` and `public` always follow the selected row; other values are filled when empty and
replaced only with `--overwrite`; nothing is cleared.

Modes:

- `--report FILE` (default, read-only), with `--inferred FILE` to sample inferred libraries;
- `--add-library-property --confirm-endpoint HOST:PORT`: declares the text `library` property
  (a reviewed, additive schema change required by the writing modes);
- `--apply REPORT --confirm-endpoint HOST:PORT [--accept-incomplete]`: writes a reviewed report,
  only where the stored values still equal the report's, and reads them back;
- `--sync --confirm-endpoint HOST:PORT --checkpoint FILE`: plans and writes one page of 100
  documents at a time, resumable, with a manifest of unresolved and failed ids (#259).

A changed `yearIssued` reaches the search only after `chunk_year --write` (below).

Prerequisites: the PostgreSQL driver (`../.venv/bin/pip install "psycopg[binary]"`, not an
application dependency) and `KRAMERIUS_METADATA_DSN`, a SQLAlchemy URL such as
`postgresql+psycopg://librarymetadata_all@127.0.0.1:5888/librarymetadata_all` through an SSH
tunnel you are authorized to use. Keep passwords out of command lines and the repository; the
command only reads the mirror and never prints the password.

Known metadata limitations, including mirror rows without MODS metadata, are tracked
on [#259](https://github.com/DCGM/semant-demo/issues/259).

## Document year on chunks (`chunk_year`, #153)

The search filters years on `Chunks.yearIssued`, a copy of the referenced document's
`yearIssued` ([SEARCH_FILTERS](SEARCH_FILTERS.md#4-applying-filters-in-search)). This command
keeps the copy equal to the document's: it sets missing years, replaces differing ones and
removes a chunk's year when its document has none. Chunks without exactly one existing
document and document years that are not whole numbers are listed in the manifest and left
unchanged. It reads only ids, years and the document reference; a write is a merge that keeps
text, vectors, references and other properties.

```bash
python -m semant_demo.maintenance.chunk_year --check check.json             # read-only
python -m semant_demo.maintenance.chunk_year --write write.json --confirm-endpoint HOST:PORT
python -m semant_demo.maintenance.chunk_year --check check_after.json       # expect exit 0
```

`--write` first declares `Chunks.yearIssued` (`int`, range index) when the collection lacks
it, an additive schema change through the alias's collection, then writes only differing
chunks and reads every page's writes back. An existing `yearIssued` without a range index is
refused before any write: its index settings cannot be changed in place, so it needs a separate,
reviewed schema or collection migration. Both modes are checkpointed and resumable (writes
that failed or did not read back are retried first); a finished checkpoint is refused, so every
new check or write takes a new checkpoint file name. A complete pass compares the chunk counts
that the search predicates find for several year ranges with those expected from the
documents; a check exits 0 only when nothing is left to write and every range matches.

Run it on every store before deploying the chunk-year search (a store without the property
answers year-filtered searches with an error), and again after ingesting chunks or changing
document years (for example after `metadata_sync`) until ingestion keeps the copy itself
([#313](https://github.com/DCGM/semant-demo/issues/313)).

## Annotation migration (`annotation_migration`, #327)

Copies the spans of the legacy single-tenant `Span` collection into the multi-tenant
`Annotation` collection, one tenant per user collection, keeping every span's UUID, tag,
anchor chunk, offsets, type and AI metadata ([DATABASE.md](DATABASE.md#collection-annotation-multi-tenant-327)).
A release with #327 reads and writes **only** `Annotation`: deployed on a store that was not
migrated, it shows no annotations and cannot save any (startup logs an error). The legacy
collection is only read and stays unchanged for rollback.

```bash
python -m semant_demo.maintenance.annotation_migration backfill --state dry.json          # read-only
python -m semant_demo.maintenance.annotation_migration backfill --state run.json --execute \
  --confirm-endpoint HOST:PORT --offline-backup /path/of/the/copy    # or --backup-id BACKUP
python -m semant_demo.maintenance.annotation_migration verify --report verify.json        # read-only
```

The dry run is the inventory: legacy and per-collection counts (`would_copy`,
`anchor_not_in_collection`), skipped records by reason (no or several tag/chunk references —
Weaviate 1.40 returns no reference to a deleted object, so spans of deleted tags or chunks
appear here —, tags without exactly one collection, chunks without a document, unknown types,
offsets that are not `0 <= start < end`) with their ids, and the tag inventory. Skipped spans
are never assigned to a guessed collection; review them before the cutover. Their chunk tag
references become unbacked and are then reported by `chunk_tag_audit`.

`--execute` creates `Annotation` when missing and the tenants it needs, inserts only spans
absent from their tenant (a differing copy is a reported `conflict`, never overwritten), saves
its cursor after every batch and resumes from `STATE`; run the same command again after an
interruption. `verify` compares every valid legacy span with its copy and lists the tenants'
spans without a legacy original. The module docstring (`--help`) is the reference.

### Cutover (production, test store)

Needs explicit authorization for the store. The deployed Weaviate instances enable the
`backup-filesystem` module (`--backup-id`); an offline copy of the data directory, or an
existing backup recorded with `--offline-backup`, also qualifies. Production serves `Chunks`,
`Tag`, `Documents`, `UserCollection` and `Span` as aliases of `*_test` collections: the
backfill creates `Annotation` itself (no alias), with its `text_chunk` reference targeting the
collection behind `Chunks`, since Weaviate refuses a reference to an alias.

1. Before the pause, on the running store: `backfill --state dry.json` and
   `chunk_tag_audit --report audit-before.json`. Review the skipped records, the tag inventory
   and the counts; expect the pause to take about as long as the dry run plus writing (the
   rehearsal wrote ~16,000 spans/s into existing tenants and created ~16 tenants/s).
2. **Write pause:** stop the backend (`./update.sh app-down`, for the test store every app
   instance that uses it: `test-main` and the PR previews). Topicer and maintenance commands
   must not write either. The release with #327 must not be started before the backfill
   finished: until then it cannot read annotations, and once `Annotation` exists it writes there.
3. Back up: stop Weaviate (`./update.sh database-down`), copy its data directory, start it again.
4. With the new release's code (its image or a checkout with its `.venv`) and `WEAVIATE_*` set
   to the store: `backfill --state run.json --execute --confirm-endpoint HOST:PORT
   --offline-backup PATH`, until it exits 0 (`failed` and `conflict` empty).
5. `verify --report verify.json` must report no `missing`, `different`, `target_only` or
   `orphan_tenants`; `chunk_tag_audit --report audit-after.json` must report what
   `audit-before.json` reported plus the references of skipped spans.
6. Deploy and start the new release. Check the document view (annotations, AI suggestions,
   approve/reject), collection statistics, tag-filtered search and a span discussion.
7. Keep `Span`, the copy, the state, the reports and the audits; record counts, the copy
   and the outcome on the issue.

**Rollback.** Before any annotation was written in the new store, redeploy the previous
release: it reads `Span`, which the migration did not change (`Annotation` can stay; the old
release ignores it). After writes in the new store, switching back would lose them: run
`verify --report`, which lists the spans created (`target_only`), changed (`different`) and
deleted (`missing`) since the cutover, and reconcile them into `Span` in a separately reviewed
step (no tool is provided), or roll forward. The chunk tag references follow the new store's
writes, so run `chunk_tag_audit` against whichever store is current. Restoring the offline
copy also returns to the pre-migration state, losing every later write in all collections.

**Rehearsed** on disposable Weaviate 1.40.1 (2026-10-18; `tests/integration/test_annotation_migration.py`
and a command-line run on a bind-mounted store): dry run, refusal without a backup, execute,
idempotent rerun, interrupted and resumed backfill, conflicts, verify before and after
application writes, an offline copy of a migrated store with active and inactive tenants
(restored with their statuses and spans), and the pre-migration copy as rollback target. Not
rehearsed at production size; the production span count and duration are unknown until the
dry run.

## Annotation tenants (`annotation_tenants`, #327)

Lists the annotation tenants with their status and last recorded use, and deactivates idle
ones. An inactive tenant keeps its data on disk; the next read or write activates it again.

```bash
python -m semant_demo.maintenance.annotation_tenants status [--counts]       # read-only
python -m semant_demo.maintenance.annotation_tenants deactivate-idle         # dry run
python -m semant_demo.maintenance.annotation_tenants deactivate-idle --execute --confirm-endpoint HOST:PORT
```

The backend and the maintenance commands record each tenant use in the SQL table
`annotation_tenant_activity`, so the command needs the application's `SQL_DB_URL` (the same
SQLite file as the backend). `--execute` is refused unless
`ANNOTATION_TENANT_DEACTIVATION_ENABLED=true` and the idle time
(`ANNOTATION_TENANT_IDLE_SECONDS`, default 3600, or `--idle-seconds`) is at least three
`ANNOTATION_TENANT_TOUCH_SECONDS`. A tenant without a record gets one and is deactivated only a
full idle time later; each candidate's record is read again right before it is deactivated; a
request that starts in that instant can still meet a deactivating tenant (it fails or waits for
the activation and can be repeated). `status --counts` activates every tenant it counts.

**Keep deactivation disabled** until backup and restore of active and inactive tenants have
been rehearsed on the deployed store's version and a measurement shows a benefit. Rehearsed on
disposable Weaviate 1.40.1 (2026-10-18, 32 cores; `tests/integration/test_annotation_tenants.py`
and the `benchmark` test `test_annotation_tenant_rehearsal.py`, `-m benchmark`):

- filesystem backup and restore keep active and inactive tenants with their spans and
  statuses (1,007 tenants, 953 inactive, 42,007 spans: backup 2.0 s, restore 1.0 s); an
  offline data-directory copy does too (above);
- reads and writes activate an inactive tenant: first read 10–21 ms for tenants of 0 to 30,000
  spans, 50 concurrent activations of small tenants 196 ms median, 368 ms max; deactivation
  15–98 ms;
- creating a tenant takes 60–150 ms (~16/s in batches of 100);
- container memory grew from ~120 MiB (5 tenants, 41,000 spans) to ~357 MiB with 1,000 more
  small active tenants and did **not** decrease within 20 s after deactivating them.

These are single-machine measurements, not capacity limits; no claim is made for many more
tenants (for example 100,000) from them.

## Practising on a copy of the development snapshot

Never run a writing step against the only copy of `local_data/weaviate_semant_test/`.
`make test-integration` does not use `local_data/`.

1. Stop the development Weaviate (`docker stop semant-weaviate-dev`) so the files are
   consistent, check free disk space, and copy the snapshot through a container (some files
   are owned by the container's root user):

   ```bash
   COPY=$(mktemp -d "$(pwd)/local_data/maintenance-copy-XXXXXX")
   docker run --rm --entrypoint sh \
     --mount type=bind,source="$(pwd)/local_data/weaviate_semant_test",target=/src,readonly \
     --mount type=bind,source="$COPY",target=/dst \
     cr.weaviate.io/semitechnologies/weaviate:1.40.1 -c 'cp -a /src/. /dst/'
   ```

2. Restart the development Weaviate and start the copy as a second instance with the
   [DEVELOPMENT.md](DEVELOPMENT.md#3-start-local-weaviate) command, changing only
   `--name semant-weaviate-maintenance-copy -p 127.0.0.1:18080:8080 -p 127.0.0.1:15051:50051`
   and the mount source `"$COPY"`. Check `curl localhost:18080/v1/.well-known/ready` and the
   object counts.
3. In `semant_demo_backend/`:
   `export WEAVIATE_HOST=localhost WEAVIATE_REST_PORT=18080 WEAVIATE_GRPC_PORT=15051`.
4. Run the read-only step and review its report (counts, unresolved or `unknown_or_error`
   entries, samples of the planned changes).
5. Run the writing step with `--confirm-endpoint localhost:18080`, then run it again (it
   should find nothing left to do) and read the data back through the application.
6. `docker stop semant-weaviate-maintenance-copy`, delete `$COPY`, and confirm the
   development snapshot was not modified.
