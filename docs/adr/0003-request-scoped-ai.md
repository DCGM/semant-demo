# ADR 0003 - Request-scoped generation with persistent results

Status: direction agreed in discussion; events implemented in #207; retry/regeneration
policy still proposed.
Date: 2026-10-07, updated 2026-10-08 (#207).

## Context and decision

The current proposal path persists `auto` spans and streams saved results. Keep that
model: generation is request-scoped and non-durable; saved proposals are durable data.
This is not a durable background job. Work may be lengthy without needing a queue.

Extract orchestration into an annotation service. Route code serializes typed events.
Bound concurrency, validate provider output, save each valid proposal, then announce the
saved span ID. Distinguish empty results, rejected invalid output, provider failures,
and persistence failures. A terminal event summarizes the run when the connection survives.

Cancel and await remaining local work when the request disconnects or is cancelled.
Keep previously saved proposals. Do not promise cancellation instantly reverses an
upstream call or an in-flight database write. Reload saved spans on returning to the
page; missing completion is not success and does not mean automatic resume.

## Proposed UI and retry behavior

Give each request a context/run token for event routing, not a persisted job record.
A previous request cannot overwrite the current document, collection, loading state,
or sidebar context. Display saved automatic annotations immediately in Document view;
this is the confirmed local 'real-time' behavior, not cross-user synchronization.
Show partial completion and a way to retry deliberately.

Proposed default: preserve human approvals and rejections; do not delete all spans before
regeneration. Suppress exact duplicate proposals within the same authorized scope and
text revision where known. Semantically different proposals may coexist. Re-running an
LLM is not exactly-once execution; settle the desired regeneration policy before adding
retries that create data. A run-history table is not required by this decision.

## Implemented in #207

- Workflow `features/annotations/suggestions.py`; routes only encode NDJSON. Lines are
  `{"event": "result", "chunk_id", "spans", "error", "unsaved"}` (spans only after their
  write was acknowledged) and a final `{"event": "end", "outcome", "saved", "rejected",
  "save_failures", "search_tag_failures", "provider_failures", "error"}`. `outcome` is
  `complete` (no failure; invalid proposals may have been rejected), `partial` or `failed`
  (nothing saved and no provider call fully completed). `cancelled` is reported only to
  workflow callers and the log, since the stream is gone. No `end` line means interrupted.
- Run token: the frontend gives each run a token; changing document or collection aborts
  the run and ignores its late events, errors and loading-state changes.
- Concurrency: at most 10 Topicer calls per run; not bounded across requests yet.

**Duplicate proposals (current behavior, documented before any retry logic):** proposals
are not compared with stored spans. Running suggestions again stores another `auto` span
for a proposal identical (chunk, tag, start, end) to an existing span of any type,
including approved (`pos`) and rejected (`neg`) ones, and a provider returning the same
proposal twice in one run stores it twice. Runs never change or delete existing spans, so
human approvals and rejections are preserved. Users remove unresolved duplicates with
"Clear unresolved" (`/api/ai/auto_spans/delete`). Suppressing exact duplicates (as
proposed above) needs a lookup per chunk and tag and a decision whether a proposal matching
a rejected span is suppressed; settle it before adding automatic retry or regeneration.

## Consequences

No progress recovery or continued execution after browser/server termination is promised.
Removing legacy jobs must preserve SQL user infrastructure and request-scoped concurrency.
A durable worker is a separate future decision only when continuation after disconnect
or restart is an actual requirement, not a consequence of storing results.

Evidence: [current AI routes](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/ai_assistance_routes.py).
