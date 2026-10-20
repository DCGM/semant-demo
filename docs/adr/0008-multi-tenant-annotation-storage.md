# ADR 0008 - One annotation tenant per user collection

Status: storage, access, lifecycle and migration tooling implemented in #327; production and
the shared test store were migrated on 2026-10-18. Enabling idle deactivation is pending.
Date: 2026-10-18. Agreed in the collection-workspace plan (#311, #323); refines ADR 0004's
storage of span annotations, not its chunk tag search. Derived annotation data on the same
objects: [ADR 0009](0009-derived-annotation-data.md) (#328).

## Context

Span annotations were one single-tenant `Span` collection whose spans reached their
collection through their tag. The collection workspace (#311) needs collection-local
annotation queries and enrichment (#328) for the same annotations the document view edits.

## Decision

- Store all span annotations in one multi-tenant Weaviate collection, `Annotation`, with one
  tenant per semANT user collection. The tenant name is the collection's UUID, never a user
  id: sharing grants access to the same tenant and copies nothing; renaming or transferring a
  collection keeps it. No physical collection per user collection, tag or attribute.
- Keep span UUIDs, tags, anchor chunks, UTF-16 half-open offsets and `pos`/`auto`/`neg`
  semantics. Store `tagId`, `chunkId` and `documentId` as filterable UUID properties; keep
  Tags, Chunks and Documents where they are. The chunk tag projection used by search (ADR 0004)
  is unchanged and derived from the tag's collection tenant.
- The service authorizes the collection before it uses its tenant (ADR 0007). A caller's
  tenant or span id is no credential: span-id routes carry the collection explicitly, ids are
  looked up only in its tenant, and nothing scans tenants to locate a span.
- Tenants are created lazily by the first annotation write; reads of a collection without a
  tenant return nothing and create none. Tenants activate on access. An idle-deactivation
  command exists but stays disabled until backup and restore of inactive tenants are rehearsed
  on the deployed version and a benefit is measured. Deleting a collection removes its tenant
  through the best-effort cascade (ADR 0002); removal counts only when a lookup confirms it.
- Existing spans move by an explicit, operator-run, checkpointed migration during a write
  pause, never at startup. No dual writes. The legacy collection stays unchanged for rollback;
  a rollback after new writes reconciles them first.

## Consequences

Span updates, deletions and span chat requests name their collection (an API change made
together with the frontend). Collection statistics filter the tenant through a `text_chunk`
reference, because Weaviate 1.40 cannot return references of multi-tenant objects to
collections without tenants. Deploying the release requires the migration on every store it
uses. Capacity for many tenants is not inferred from tenant counts; measurements are recorded
in [DATA_MAINTENANCE.md](../DATA_MAINTENANCE.md#annotation-tenants-annotation_tenants-327).

## Verification

Owner, shared, unrelated and anonymous access, guessed ids of other tenants and mixed-tenant
batches, lazy creation, concurrent creation and activation, idle deactivation, deletion
failures and retry, backup/restore of active and inactive tenants, and the migration (dry run,
skipped records, resume, conflicts, verification) are tested against disposable Weaviate
1.40.1 (`tests/integration/test_annotation_tenants.py`, `test_annotation_migration.py`).
