# ADR 0013 - No chunk tag references; no tag-filtered chunk search

Status: implemented with #733. Maintainer decision of 2026-11-17: tag-filtered chunk search
is dropped from the roadmap.
Date: 2026-11-17. Supersedes the chunk-tag projection and tag-filtered search decision of
[ADR 0004](0004-storage-and-annotation-search.md) and the search part of confirmed decision
Q2 ([README](README.md#confirmed-decisions)). ADR 0004 still applies to keeping documents,
chunks and vectors in Weaviate and to SQL identity storage.

## Context

ADR 0004 kept a projection of the span annotations on the `Chunks` objects: the references
`automaticTag`, `positiveTag` and `negativeTag`, re-derived after every span write (#204,
#206), so that `POST /api/search` could filter chunks by tag. Its only reader was that legacy
search filter, and no client in the repository used it (the search page, RAG pipelines, the
passage and document search APIs and MCP never sent a nonempty tag filter).

Keeping the projection consistent was expensive and still unreliable (#422): a filtered read
during concurrent span updates misses objects, so a re-derivation can read too few spans,
and concurrent `reference_add` / `reference_delete` on one object lose writes. Production
needed a write pause to repair 6,678 inconsistent entries, and new ones kept appearing.
Fixing both would need per-chunk locking and a read strategy robust to concurrent writes.

## Decision

- `Chunks` hold no searchable annotation-tag projection. Spans in the annotation tenants
  ([ADR 0008](0008-multi-tenant-annotation-storage.md)) are the only stored form of
  annotations; document view, annotation lists, concordance, exports and annotation search
  read spans.
- Span writes are not followed by any chunk write; the `update_chunk_tags` step, the
  repair endpoint and the audit command are removed. Tag deletion deletes the tag's spans and
  the tag, without touching chunks.
- `POST /api/search` has no tag filter. `tag_uuids`, `positive` and `automatic` are not part
  of the advertised request schema. Older clients may still send their former no-op values
  (`[]` / `false`); a request with an active filter (nonempty `tag_uuids`, or `positive` or
  `automatic` true) is refused with 422 rather than answered with unfiltered results.
- No replacement annotation-filtered chunk search is introduced. A future need is a separate
  product decision.

## Existing stores

The three reference properties and their stored references remain in existing stores
(production, shared test, development snapshots) and are inert: no application code reads
or writes them. This decision does not include a data repair, reference clearing, schema
change, migration or write pause. Physical cleanup, if ever worthwhile, is a separately
reviewed issue based on measured storage/index benefit and verified Weaviate support.
New stores (`weaviate_utils/build_db/create_schema.py`, the test stores) are created without
the properties. Utilities that import older exports may drop the legacy properties, labeled
as such.

## Consequences

- One write per span change instead of two; no partial outcome for search references and no
  per-pair lock.
- Tag-filtered search, if ever wanted again, needs its own design (for example a span query
  per collection) rather than a projection on shared chunk objects.
- Historical records (ADR 0004, the #422 run records and audit reports) stay as history.
