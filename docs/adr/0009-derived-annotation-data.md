# ADR 0009 - Derived annotation text, positions and vectors

Status: proposed with #328 (implementation in review); store rollout pending an operator step.
Date: 2026-10-18. Refines ADR 0006 (canonical text) and ADR 0008 (annotation storage) for the
collection workspace (#311, #323); prerequisite of the basic KWIC API (#329, Stage 1 #323) and of
lexical/semantic/hybrid annotation search (#332, Stage 2 #324).

## Context

Concordance (KWIC) rows, word-distance queries and similarity search need each annotation's
text, surrounding context, document position and a vector, without reading source chunks for
every hit. Source text is immutable here; chunk orders may have gaps (missing text); chunks
outside a collection are still part of the document.

## Decision

- Store derived fields on the same `Annotation` object; the anchor chunk, tag and UTF-16
  half-open local offsets stay authoritative. No separate concordance write path: creates and
  offset changes go through the Annotations service, which writes span and derived text in one
  write, then the vector.
- Positions are relative to a **continuity segment** (the gap-free run of chunk orders containing
  the span, identified by its first `order`), in UTF-16 units and in words. Distances exist only
  within a document and segment; nothing is invented across missing text. Excluded chunks count.
- Words: runs of Unicode letters, marks, digits and format characters; all else separates
  (hyphenated compounds are two words); partially covered words belong to the span. Not tokens.
- Context: up to 200 code points per side within the segment, trimmed to whole words; versioned
  (`derivationVersion`) so a new policy is a backfill, not a silent mix.
- One contextual named vector embeds the context with the span marked (`{left}<<<{text}>>>{right}`);
  tag, type and AI metadata are not embedded, so changing them never re-embeds. Its configuration
  `id` is stored per vector; span-only vectors are later evaluation.
- Freshness: `revision` counts offset changes; derived data names the revision, derivation policy
  (`derivationVersion`) and vector config it was computed for and counts only while they match; a
  vector also only while the text is current, and re-deriving the text marks the vector pending.
  A vector is written only if the revision is unchanged (per-span lock within the process). Provider or read failures keep the edit with an
  explicit `failed` status and a `partial` write result (ADR 0002); saving again or the bounded
  operator backfill retries. No background job, watcher or automatic repair.
- Document metadata (title, year) is joined per page of rows, not copied, so it needs no refresh path.
- The backend writes derived properties only when the collection has them; adding them is an
  explicit operator command, never startup or a request.

## Consequences

Span writes read the document's chunk texts (as #376 measures) and call the embedder; reads of rows
and vectors need no chunk reads. With several backend processes a late vector can still land, but
it is recognizable as stale and never returned. The revision check is not atomic across processes,
so store-wide backfills (rollout, a policy or vector configuration change) run with every backend and
other writer stopped; no cross-process conditional write is implemented. Spans saved before #328
have no derived data until the backfill. Corpus re-ingestion is not required.

## Verification

Shared offset fixtures and derivation cases (`tests/test_annotation_derivation.py`), service
behavior with fakes (`tests/test_annotation_enrichment.py`: tag/status edits never embed, failures,
out-of-order embeddings, backfill), and real Weaviate 1.40.1
(`tests/integration/test_annotation_enrichment.py`: API writes, vector kept by patches, stale vectors
excluded, schema addition to a pre-#328 collection and backfill).
