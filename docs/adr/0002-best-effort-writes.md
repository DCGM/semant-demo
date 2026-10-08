# ADR 0002 - Best-effort writes with visible partial outcomes

Status: decision adopted; best-effort and partial-outcome behavior implemented across #201–#209. Some suggested envelope details remain future refinements.
Date: 2026-10-07.

## Decision

Multi-write workflows are not assumed atomic. Keep completed changes; report failures
and incomplete execution. Do not build automatic rollback, repair jobs, sagas, or an
outbox for the current application. Prefer idempotent membership operations and explicit
user-triggered retries. Authorization/identity must not fail open.

The service owns workflow reporting. An adapter reports a failed storage operation rather
than turning it into a false success. Catch expected item failures where work is independent;
stop dependent steps or systemic outages when proceeding would be misleading or wasteful.
Never loop indefinitely over a page whose failed items cannot be removed.

## Contract principles and further refinements

A bulk result carries `outcome` (`complete`, `partial`, or `failed`), successful item IDs,
item/step errors, unattempted work, and uncertain outcomes where a timed-out write may
have landed. Counts describe acknowledged outcomes, not guessed database state. Errors
have safe codes/messages and a request ID. Do not expose inaccessible resource details.

Example: '18 of 20 chunk links saved; 2 failed' is not 'document fully added'. When a
single item's workflow has several writes, record the failed step as well as the item.
A stream reports the same distinctions through events; abnormal EOF means incomplete.

Choose an explicit response model for bulk endpoints. Do not return a failure body with
204, return an unqualified success boolean, or silently alter an existing generated-client
contract. Coordinate API and UI updates in a behavior-change PR.

## Limits

A timeout is not proof that nothing was written. Retry only when the operation's semantics
make it safe. For generated spans, exact-duplicate prevention needs an explicit identity
rule; do not pretend calling the model again is idempotent.

Validate authorization before mutation. Prefer one authoritative write for sharing/ownership;
a partial permission update must not widen access. No distributed transaction is implied.
Manual investigation or a one-off migration may occasionally be authorized, but routine
operation does not depend on repair infrastructure.
