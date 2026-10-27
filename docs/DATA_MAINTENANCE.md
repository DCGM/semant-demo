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
delete data (for example `delete_*.py`, `build_db/create_schema.py`) and connect to a
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
affected collections are verified at the end. A removed document is restored by importing its chunks
again with the same UUIDs ([`chunk_ingest`](#chunk-import-chunk_ingest-313)) and then its metadata
(`metadata_sync`); collection memberships are not restored automatically (the manifest lists them).

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

## Chunk positions (`chunk_positions`, #463)

Annotation text, context and positions are derived from the anchor chunk's stored position
in its document (`Chunks.startChar`, `startWord`, `wordOpenAtStart`,
[DATABASE.md](DATABASE.md#collection-chunks)) and the chunks next to it, never from the whole
document. Chunks without positions leave every new or moved annotation on them with failed
derived data (`derive_annotation`), so run this command on a store before deploying #463 there.
New chunks get their positions when they are inserted ([`chunk_ingest`](#chunk-import-chunk_ingest-313),
which needs this backfill done first: it continues from the stored tail).

```bash
python -m semant_demo.maintenance.chunk_positions --check check.json             # read-only
python -m semant_demo.maintenance.chunk_positions --write write.json --confirm-endpoint HOST:PORT
python -m semant_demo.maintenance.chunk_positions --check check_after.json       # expect exit 0
```

It goes through the documents in id order; for each one it counts the chunks and their least
and greatest `order`, reads the chunks in windows of 200 orders (order, text and positions,
never vectors), and computes the positions in order with the shared calculator
(`features/documents/positions.py`, the one the import uses). Only a fully valid document is
written, and only its chunks without positions:

- `consistent` / `missing`: every chunk stores the computed position / some store none (written);
- `conflict`: a chunk stores a different or partial position — reported, nothing of the
  document written, never overwritten;
- `nonconsecutive`: a gap or a duplicate `order` — reported, nothing written; such a document
  violates the text model and is not renumbered or split (non-append resegmentation is
  [#354](https://github.com/DCGM/semant-demo/issues/354));
- `no_chunks`: a document without chunks ([#281](https://github.com/DCGM/semant-demo/issues/281)).

`--write` first declares the missing properties (`startChar`, `startWord` `int`;
`wordOpenAtStart` `boolean`), an additive schema change through the alias's collection; a
declared property of another type is refused before any write. A write is a merge of these
three properties: text, references, vectors, memberships and annotations are not touched,
and annotations are neither rewritten nor re-embedded (on documents with consecutive orders
their #328 positions are already the absolute ones). Written positions are read back. Both
modes are checkpointed per page of documents and resumable (documents whose read or write
failed are planned again first); a finished checkpoint is refused. Reported documents go to
`CHECKPOINT.manifest.jsonl`. A complete pass compares the chunks reached through documents
with all chunks of the collection (`chunks_not_reached`: chunks without a valid `document`
reference are not positioned). Exit 0 only when every chunk was reached and stores its
computed position, nothing is left to retry and no document was reported.

Procedure on a shared store (authorized per task): back up, stop every writer of chunks (no
import, no backend writing annotations during `--write`), rehearse on a copy of the
development snapshot and compare its counts with a `--check` of the target, run `--check`,
`--write`, then `--check` again with a new checkpoint, and restart the backend: it reads the
positions only when `Chunks` declares them at startup (`bootstrap.detect_chunk_positions`).
Record counts, reported documents and the backup id on the issue. A development store seeded
before #463 is completed by the same command, or by `make dev-reset`.

## Chunk import (`chunk_ingest`, #313)

The one supported way to add text chunks: append-only, into the **existing** collections. It
only inserts absent `Chunks` objects and, before the first chunk of a new document, an absent
`Documents` object without properties. It never updates or deletes an existing object and
only reads the schema (a missing collection, property or type is refused before any write;
the schema itself is #128).

```bash
python -m semant_demo.maintenance.chunk_ingest --check check.json chunks/*.jsonl       # read-only plan
python -m semant_demo.maintenance.chunk_ingest --write write.json --confirm-endpoint HOST:PORT \
    --backup-id BACKUP chunks/*.jsonl                                                  # or --offline-backup NOTE
```

**Input.** One JSON object per line and chunk; files are read in sorted path order.

- Required: `id` (chunk UUID), `document` (document UUID), `order` (int) and `text` (may be empty).
- Optional source fields, each only if `Chunks` declares it with that type: `start_page_id`, `language`
  (str), `from_page`, `to_page` (int), `end_paragraph` (bool).
- Ignored and counted (`ignored_fields`), never written:
  - the document description of the old `db_insert_jsonl.py` format (`title`, `year`, `author`, `date`,
    `source`, ...);
  - precomputed vectors (`vector`, `vector_index`).
- Anything else rejects the whole document: an unknown key, a position property, an invalid value, a
  duplicate chunk id, or orders that are not consecutive in input order.

**Plan per document**, from what is stored (never from the checkpoint alone):

- `new`: no chunks stored. A missing document object is created empty, and the chunks get
  positions from the document start; the first order may be any integer.
- `append`: the input continues the stored chunks `s..m`; it may repeat their suffix `a..m`,
  which must equal what is stored, including the computed positions. Chunks after `m` get
  positions computed from the stored tail with the shared calculator
  (`features/documents/positions.py`), so their `order` is exactly the previous one + 1.
- `replayed`: everything is stored; nothing is written. Repeating a completed import inserts nothing.
- `rejected` (reported, nothing of the document is written):
  - `gap`, `before_start`;
  - `conflict` (another text, source field, position, document or order);
  - `nonconsecutive_store`;
  - `positions_missing` (run `chunk_positions --write` first);
  - `dangling_document`;
  - `invalid_input`.

**Writing.**

- Each chunk is inserted on its own: Weaviate's single-object insert refuses an existing id,
  while a batch insert would silently replace it. A chunk is read back before the next chunk of
  its document; documents are written in parallel (`--concurrency`).
- `--bulk` is for a **new store** whose chunk collection is empty at the start (refused otherwise,
  before any write):
  - it batch-inserts the chunks in rounds of one next chunk from each of up to 100 documents, each
    round read back before the next;
  - documents are still created with single inserts, because a batch insert could replace an
    existing document with its metadata;
  - an interrupted bulk run is finished without `--bulk`: by then the collection is no longer empty,
    so nothing already stored is ever written in a batch.
- A failed or uncertain write blocks only the rest of that document (`blocked`); running the same
  command again retries it, planned again from the store.
- A created document whose chunks did not all arrive is listed as `incomplete_document` and never
  deleted (#281).
- The checkpoint holds the endpoint, the resolved collections, the input files (size, SHA-256), the
  cursor, the blocked documents and, for every write run, its backup and whether it used `--bulk`
  (`runs`), recorded before anything is written. A finished checkpoint, or one for other input, is refused.
- Backups:
  - `--backup-id` must be a successful `backup-filesystem` backup holding the chunks and documents
    collections; this is checked.
  - `--offline-backup NOTE` describes an offline copy of the data directory made with Weaviate stopped;
    it is recorded as given and not checked.
  - `--check` takes neither, nor `--bulk`.
- Reported documents and invalid lines go to `CHECKPOINT.manifest.jsonl`.
- Exit 0 only when nothing was rejected, invalid or blocked.

**Afterwards**, as separate commands:

1. `metadata_sync` fills the new documents' metadata.
2. `chunk_year --write` copies their year to the chunks.
3. `data_tools/embedder` computes the `Qwen3_Embedding_0_6B` vectors; until then the new chunks
   are missing from vector and hybrid search.

The import does none of this, nor anything to existing annotations: their positions stay valid,
and context near the former document end keeps its old right boundary.

Procedure on a shared store (authorized per task):
1. Back up.
2. Stop other chunk writers.
3. Run `--check` and review the plan and the manifest.
4. Run `--write`.
5. Run `--check` again with a new checkpoint (expect `replayed` only).
6. Run the follow-up commands.

Record the counts and the backup id on the issue.

## Annotation derived data (`annotation_enrichment`, #328)

Span creates and offset changes store the span's text, context, positions and contextual
vector ([DATABASE.md](DATABASE.md#collection-annotation-multi-tenant-327)) once the
`Annotation` collection has the derived properties. Spans saved before, spans whose
derivation or embedding failed, and vectors of another `ANNOTATION_VECTOR_CONFIG` `id` are
completed by this explicit command.

```bash
python -m semant_demo.maintenance.annotation_enrichment add-schema                      # dry run: what is missing
python -m semant_demo.maintenance.annotation_enrichment add-schema --execute --confirm-endpoint HOST:PORT
python -m semant_demo.maintenance.annotation_enrichment status [--collection ID ...]     # read-only counts
python -m semant_demo.maintenance.annotation_enrichment backfill --limit 500 [--collection ID ...] \
  [--no-vectors] --execute --confirm-endpoint HOST:PORT                                 # without --execute: status
```

- `add-schema` adds the missing derived properties and the named vector (`target_vector` of
  the configured vector) to the existing collection; it changes no object and is idempotent.
  Restart the backend afterwards: it decides at startup what it stores and logs an error while
  properties or the vector are missing.
- Contextual annotation vectors may set `max_input_chars` to limit the rendered embedding input.
  The Qwen config uses a 2048-character limit. Inputs under the limit are unchanged; longer
  inputs shorten context first, then the end of the span while keeping its start and markers.
  Existing successful vectors remain current. Failed or incomplete vectors can be retried during
  the next scheduled annotation enrichment maintenance; no immediate backfill is required.
- `status` counts each tenant's spans by text state (`current`, `outdated` derivation policy,
  `missing`, `failed`, `invalid`) and vector state (`current`, `pending`, `failed`, `stale`),
  and `incomplete` (what a backfill would write). Reading a tenant activates it.
- `backfill` writes only derived properties of at most `--limit` incomplete spans, never offsets,
  chunk, tag, type or revision, and deletes nothing. It reports `processed`, `text_written`,
  `vector_written`, `not_processed` (incomplete spans skipped because of `--limit`),
  `remaining_incomplete` (every span still incomplete for the configured vector when the run
  ended, read again afterwards: not processed ones, failed steps and, with `--no-vectors`, vectors
  still to embed) and `failed`. Text re-derived under a new derivation policy marks its vector
  `pending`, so `--no-vectors` never leaves an old vector counted as current. Each document is read
  once per tenant; each vector is one call to the configured embedding provider (with
  `--no-vectors`, none). `invalid` spans (offsets that no longer describe the document's text,
  or whose chunk is gone) are recorded once and left for review, not repaired. Exits 1 when
  steps failed (`failed`); run it again to retry.
- The revision check before each backfill write is atomic only within the command's own process,
  not against a running backend (`superseded` counts only the changes it happens to see). **Run
  `backfill` only while nothing else writes the annotation store.**

Rollout on an existing store (needs authorization for that store). The application stays
**stopped for the whole procedure**:

1. Stop every writer of the target annotation store: all backend instances (also other app or
   preview instances configured for the same Weaviate), Topicer-driven suggestion runs and any
   other background job or script. Confirm that none is running.
2. Back up the store (`backup-filesystem` backup or an offline copy, [safety rules](#safety-rules-all-commands))
   and record the backup id or path.
3. `add-schema` (dry run), then `add-schema --execute --confirm-endpoint HOST:PORT` if anything is
   missing.
4. `status`, then `backfill --limit N --execute --confirm-endpoint HOST:PORT` **with vectors**
   (not `--no-vectors`) in bounded runs until it reports `remaining_incomplete: 0` and no
   `failed`; retry failed steps by running it again.
5. Verify with `status`: `incomplete: 0` for every tenant; review any `invalid` spans separately.
6. Only then start the new application release.

The same procedure applies to a later change of `DERIVATION_VERSION` or of the vector
configuration `id`: readers treat older derived data as absent until the backfill has completed.
Rolling back the release needs no data change (older releases ignore the
derived properties). Rehearsed only on disposable Weaviate 1.40.1
(`tests/integration/test_annotation_enrichment.py`); production counts and duration are unknown
until `status` runs there.

## Annotation provenance (`annotation_provenance`, #460)

Span writes record who created, reviewed and last changed each annotation, its origin and an
`editVersion` that refuses writes based on an outdated copy
([DATABASE.md](DATABASE.md#collection-annotation-multi-tenant-327)), once the `Annotation`
collection has the provenance properties. Collections created by the migration have them; an
existing collection gets them from this command:

```bash
python -m semant_demo.maintenance.annotation_provenance add-schema                      # dry run: what is missing
python -m semant_demo.maintenance.annotation_provenance add-schema --execute --confirm-endpoint HOST:PORT
```

- `add-schema` adds the missing properties; it changes no object and is idempotent. Existing
  annotations keep `origin` unknown (no actor or time) and version 0: no backfill, nothing is
  invented.
- Until the properties exist and the backend has been restarted, it records no provenance and
  checks no versions (it logs an error at startup). Adding properties does not disturb a
  running backend, so no write pause is needed; restart every backend instance afterwards.
- The version check runs under a per-span lock within one backend process: with several
  processes a conflicting write is detected but the check and write are not atomic (as for the
  revision check, [ADR 0009](adr/0009-derived-annotation-data.md)).

Rolling back the release needs no data change (older releases ignore the properties).
Rehearsed only on disposable Weaviate 1.40.1 (`tests/integration/test_annotation_provenance.py`).

## Collection attributes (`annotation_attributes`, #331)

Accepted attribute values are stored on each annotation (`attributeValues`, `attributeVersion`;
[ADR 0011](adr/0011-collection-attributes.md)) once the `Annotation` collection has the
properties. Collections created by the migration have them; an existing collection gets them
from this command (definitions live in SQL and need nothing):

```bash
python -m semant_demo.maintenance.annotation_attributes add-schema                      # dry run: what is missing
python -m semant_demo.maintenance.annotation_attributes add-schema --execute --confirm-endpoint HOST:PORT
```

- `add-schema` adds the missing properties; it changes no object and is idempotent. Existing
  annotations have no accepted values and version 0: no backfill.
- Until the properties exist and the backend has been restarted, attribute definitions work but
  assignments are refused (503; the backend logs an error at startup). Adding properties does not
  disturb a running backend; restart every instance afterwards.
- Back up the SQLite database together with Weaviate: the definitions (names of attributes and
  values) and the change records exist only there.

Rolling back the release needs no data change (older releases ignore the properties and tables).
Rehearsed only on disposable Weaviate 1.40.1 (`tests/integration/test_annotation_attributes.py`).
Applied to production (`localhost:8080`) and the shared test store (`localhost:8082`) on
2026-10-25, before the backends with #331 started (`v0.1.30`, `test-main`), so no extra restart
was needed; both added `attributeValues` and `attributeVersion` and the SQL tables appeared at startup.

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
   [DEVELOPMENT.md](DEVELOPMENT.md#53-start-the-snapshot-weaviate) command, changing only
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
