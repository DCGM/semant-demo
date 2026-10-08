# Agent instructions

These instructions supplement [CONTRIBUTING.md](CONTRIBUTING.md) for ordinary
development. Base new work on the latest `origin/main` and open pull requests
against protected `main`.

## Before editing

Read [ARCHITECTURE.md](docs/ARCHITECTURE.md), the relevant
[ADRs](docs/adr/README.md) and [TODO / issue index](docs/TODO.md), plus affected
callers and tests. Preserve unrelated changes and identify cross-feature/API
contracts before editing.

## Branch and PR workflow

1. Fetch and inspect `origin/main`; create a dedicated short-lived topic branch
   **from `origin/main`** for each assigned change. Do not start from a previous
   unmerged topic branch unless stacking is explicitly requested.
2. Limit the branch to its issue/scope. Run appropriate checks described in
   [CONTRIBUTING.md](CONTRIBUTING.md), update relevant active docs and any
   generated API client, and report results accurately.
3. Merge recent `origin/main` into the topic branch when needed and resolve
   conflicts locally. Open the PR **against `main`**, request review, and wait
   for required checks. Do not treat a review or one green unit test as a full
   release verification.
4. Do not push directly to `main`, force-update protected branches, merge PRs,
   deploy, or change shared/production data without explicit authorization.
   Agents may push their own assigned topic branch and open its PR for review.

## Handoff

Report scope, changed behavior/files, tests actually run, unrun checks, and
remaining risks/decisions. Link newly discovered actionable gaps to a GitHub
issue and update the relevant active documentation.

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
execute it as incidental cleanup.

Preserve canonical text and cross-chunk offsets. Document view/export/concordances support
manual/automatic/both annotation selection when those feature changes land; do not impose
approved-only defaults or redesign category/provenance fields during moves.

Search chat uses retrieved results or their explicitly selected subset, never an implicit
query rerun or wider context. Local real-time UI means streamed AI annotations appear in
Document view, not live multi-user synchronization. Line-level ALTO mapping may be frontend-
only; polygon storage is optional future work. These roadmap features are not prerequisites
for unrelated changes. Respect context and late-response guards.

## Tests and safety

Use CONTRIBUTING.md for test selection and [ADR 0005](docs/adr/0005-testing-contract.md)
for detailed cases/fixtures. Add regression tests for bugs and behavior changes. Use isolated stores and deterministic providers; no production endpoints, real
user text, paid calls, GPU downloads, or live evaluations without explicit authorization.
Do not execute destructive schema/bootstrap scripts against an unverified endpoint.

Never manually edit generated API files, commit secrets, weaken assertions, bypass CI,
or add blanket skips merely to produce a green result. A placeholder `npm test` is not
a test pass. `make setup`, `make check`, `make api-generate`, `make test-integration` and
`make test-e2e` exist (the last two need Docker); `make dev` does not.

For ordinary development, use the local database environment documented in `docs/DEVELOPMENT.md`.

Do not connect to or modify shared server Weaviate, shared preview databases, or production databases unless explicitly instructed for the current task.

Before running a destructive Weaviate/schema/data-cleanup command, verify that the configured endpoint is the local development instance. Do not infer that an endpoint is safe merely because it is called "test".



## Local environment

The repository Python environment is `.venv` at the repository root. Use it for backend commands. Do not create another Python environment unless the assigned task specifically requires it.
