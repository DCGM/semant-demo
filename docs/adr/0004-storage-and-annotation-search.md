# ADR 0004 - Preserve chunk-based tag search in Weaviate

Status: chunk-based storage and search adopted; consistency implemented in #204–#206.
Broader search redesign and existing-data repair remain separate reviewed work.
Date: 2026-10-07. Updated after the Q2 clarification; supersedes the initial proposal
for approved-only defaults and historical whole-chunk compatibility.

## Decision

Keep documents, chunks, vectors, and search-relevant membership/tag information in
Weaviate. Keep SQL identity storage. Do not introduce a SQL split, an unbounded ID-list
bridge, or a new annotation-search representation as part of cleanup.

Search uses tags stored in chunk attributes/references. Preserve that contract and the
existing search options. Do not replace it with span traversal or redesign retrieval
without a separately reviewed product and compatibility decision.

There is no supported category of historical whole-chunk tags without backing annotations.
Such entries are **database inconsistencies**, not a feature to preserve. They should be
removed from the database through a separately reviewed cleanup, not supported forever.

Document view, export, and concordances must allow selection of **manual annotations,
automatic annotations, or both**. This is not an approved-only default imposed on search.
Use the existing application meaning of these categories. Do not silently equate an
approval state with origin, reinterpret stored values, or introduce a provenance schema
merely to move code. Define any necessary selector-to-storage mapping in the feature PR;
it does not block unrelated development.

## Correctness work, not a search redesign

The pinned review found chunk `positiveTag`/`automaticTag` reads and Span create/update
paths that did not maintain those references. This is a likely integration defect in the
inspected code; the deployed database was not tested. The clarification settles the
intended representation, not whether the current implementation maintains it correctly.

Keep span annotations and their chunk-level searchable tag data consistent through the
normal mutation path. Cover creation, status/tag changes, and deletion. Removing one of
several qualifying annotations must not remove a still-valid chunk tag. Preserve existing
cross-chunk scope and annotation-category semantics while extracting the code.

A failed second write is a reported partial outcome under ADR 0002. No background repair
infrastructure or stronger atomicity guarantee is implied. Fix the mutation defect in a
focused behavior-change PR so cleanup does not immediately recreate the same inconsistency.

## Existing-data cleanup

Provide a one-off audit/dry run identifying chunk tag entries with no backing annotation
under the actual scope/category rules. Review the report, back up affected data, and
remove only entries proved inconsistent. Recheck backing annotations before removal;
a failed lookup is not evidence of absence. Do not delete valid spans, tags, or chunks.

This documentation update does not execute or authorize a production cleanup. Keep data
maintenance explicit and separate from application startup, user requests, and tests.
A full production audit is not a prerequisite for moving unrelated modules.

## Verification

Real-Weaviate tests should prove filtered-search compatibility and mutation-to-search
consistency for the changed paths, including multiple backing annotations and final
removal. Cleanup tests prove invalid entries are removed and valid ones retained.
Add manual/automatic/both selector tests in document-view/export/concordance work as
those features are implemented. That future UI work should be scoped and tested when implemented.

Sources from the pinned review: [search](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/weaviate_utils/text_chunk.py),
[span writes](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/weaviate_utils/span.py).
The confirmed product contract comes from the development discussion, not inferred
compatibility with inconsistent data.
