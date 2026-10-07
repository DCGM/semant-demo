# Agent instructions

Status: draft for adoption, updated 2026-10-07. These rules supplement, not replace,
[CONTRIBUTING.md](CONTRIBUTING.md).

During the architecture refactor, read docs/REFACTOR_STATUS.md before making changes. Update it when a refactor issue is completed, when a temporary architectural exception is introduced or removed, or when a newly discovered problem affects later refactor steps. Create/link a GitHub issue for substantive deferred work rather than describing it only in the status file.

## Before editing

Read [TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md), the assigned step in
[REFACTOR_PLAN.md](docs/REFACTOR_PLAN.md), affected callers/tests, and relevant
[ADRs](docs/adr/README.md). Treat proposed decisions as unresolved, not permission
to choose product behavior. Inspect current branch state; preserve unrelated changes.
Keep the assigned scope small. Identify cross-feature contract changes before editing.

## Refactor branch workflow

`197-refactor---base` is the integration branch for the architecture refactor.
Do not implement numbered refactor issues directly on this branch.

For each refactor issue:

1. Fetch the latest repository state and start from the current
   `origin/197-refactor---base`, not from a stale local copy.
2. Create a dedicated branch for that issue, for example
   `198-bootstrap-config` or `199-fast-checks-ci`.
3. Make only the changes required for that issue on the issue branch.
4. Run the required checks and update `docs/REFACTOR_STATUS.md` as appropriate.
5. Open a pull request from the issue branch into `197-refactor---base`.
6. Do not merge the pull request or push commits directly to
   `197-refactor---base` unless explicitly instructed.

After the issue branch is reviewed and merged, the integration branch becomes
the base for the next issue.

Do not create the next issue branch from an unmerged issue branch unless the
issues are explicitly intended to be stacked.

## Handoff

Report changed behavior and files, commands actually executed, results, unrun checks,
and remaining risks/decisions. Do not claim a test, browser check, migration, or deployment
was performed unless it was. Update relevant contracts/docs in the same PR. 

Pushing the assigned issue branch and opening a pull request into
`197-refactor---base` are part of the normal refactor workflow.

Do not push commits directly to `197-refactor---base` or `main`.
Do not merge pull requests, deploy, or change production/shared data unless
explicitly authorized for the current task.

## Architecture

- Use thin HTTP routes and service functions. Classes and ports are optional, not a template requirement.
- Enforce resource access in the service. Shared users may edit annotations, not document/chunk membership. Use separate checks; authentication alone is not authorization.
- Concrete repositories belong under `adapters/weaviate/` or `adapters/sql/`. Do not duplicate them inside features.
- Other features may call supported service functions; do not bypass them through another feature's adapters. Avoid cycles.
- Keep SDK filters/objects out of feature logic. A concrete adapter type annotation may be used initially; introduce a narrow Protocol only when useful.
- Do not create mandatory CRUD methods that raise `NotImplementedError`, speculative layers, generic event buses, or a new job framework.

## Behavior to preserve

Multi-write operations are best effort: keep completed work and report incomplete/failed
steps honestly. Do not add automatic rollback, repair infrastructure, or silent success.
Do not treat an uncertain timed-out write as definitely absent. Prefer safe explicit retries.

AI proposal generation is request-scoped with incremental persistence. Cancel/await
remaining work on disconnect; retain saved proposals. Persisted results do not imply a
durable job. Do not delete SQL user infrastructure with legacy task code.

Keep search on chunk tag attributes in Weaviate; no SQL split, large ID-list bridge, or
new span-based query design during cleanup. Entries without backing annotations are data
inconsistencies, not supported legacy features. Review data cleanup separately; never
execute it as an incidental refactor.

Preserve canonical text and cross-chunk offsets. Document view/export/concordances support
manual/automatic/both annotation selection when those feature changes land; do not impose
approved-only defaults or redesign category/provenance fields during moves.

Search chat uses retrieved results or their explicitly selected subset, never an implicit
query rerun or wider context. Local real-time UI means streamed AI annotations appear in
Document view, not live multi-user synchronization. Line-level ALTO mapping may be frontend-
only; polygon storage is optional future work. These roadmap features are not prerequisites
for unrelated refactoring. Respect context and late-response guards.

## Tests and safety

Use CONTRIBUTING.md for test selection and [ADR 0005](docs/adr/0005-testing-contract.md)
for detailed cases/fixtures. Add regression tests for bugs and behavior changes. Use isolated stores and deterministic providers; no production endpoints, real
user text, paid calls, GPU downloads, or live evaluations without explicit authorization.
Do not execute destructive schema/bootstrap scripts against an unverified endpoint.

Never manually edit generated API files, commit secrets, weaken assertions, bypass CI,
or add blanket skips merely to produce a green result. A placeholder `npm test` is not
a test pass. `make setup`, `make check` and `make api-generate` exist; other proposed
`make` targets are unavailable until the refactor step that implements them.

For ordinary development and refactoring, use only the local database environment documented in `docs/DEVELOPMENT.md`.

Do not connect to or modify shared server Weaviate, shared preview databases, or production databases unless explicitly instructed for the current task.

Before running a destructive Weaviate/schema/data-cleanup command, verify that the configured endpoint is the local development instance. Do not infer that an endpoint is safe merely because it is called "test".



## Local environment

The repository Python environment is `.venv` at the repository root. Use it for backend commands. Do not create another Python environment unless the assigned task specifically requires it.
