# ADR 0003 - Request-scoped generation with persistent results

Status: direction agreed in discussion; event and retry details proposed.
Date: 2026-10-07.

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

## Consequences

No progress recovery or continued execution after browser/server termination is promised.
Removing legacy jobs must preserve SQL user infrastructure and request-scoped concurrency.
A durable worker is a separate future decision only when continuation after disconnect
or restart is an actual requirement, not a consequence of storing results.

Evidence: [current AI routes](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/ai_assistance_routes.py).
