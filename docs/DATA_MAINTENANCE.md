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
