# Contributing to SemANT

Draft for adoption, updated 2026-10-07. Applies to human and agent-authored changes.
Repository baseline: `375caa5f7f68defba25a56cccbb7dbc7fdf99a13`; documented targets are
not necessarily implemented yet.

## 1. Working on a change

Read the affected code, callers, and tests, plus the relevant parts of
[Target architecture](docs/TARGET_ARCHITECTURE.md) and
[Refactor plan](docs/REFACTOR_PLAN.md). [ADRs](docs/adr/README.md) record decisions;
do not reopen settled product behavior or treat a proposal as implemented code.

Keep one primary purpose per PR. Separate mechanical moves from behavior changes;
do not mix unrelated upgrades, broad formatting, or schema redesign into cleanup.
Coordinate cross-feature contracts and shared files. Include required tests and generated
client changes with the API change that needs them.

## 2. Setup and commands

Use an isolated checkout and development services, never production credentials or data.
The inspected backend requires Python 3.12+. Use the frontend toolchain agreed by the team;
R0 must align and pin its runtime/tool versions rather than upgrading them in feature PRs.

From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r semant_demo_backend/requirements.txt
python -m pip install -e semant_demo_backend
cd semant_demo_backend
python -m pytest tests/ -q
```

In a separate terminal, from the repository root:

```sh
cd semant_demo_frontend
npm ci
npm run lint
npm run dev
```

With isolated services configured, run the backend from `semant_demo_backend` using
`python -m uvicorn semant_demo.main:app --reload`. SQL defaults to a relative `tasks.db`;
set `SQL_DB_URL` to use another database. Tests build apps with `create_app(Config(environ=...))`.

For normal development, use the local development databases described in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Mutable development database state
belongs under `local_data/` and must not be committed.

Fast tests must not depend on this database snapshot. Real-store automated tests
must use test-owned data as described in the testing contract.

Do not use shared server or production databases unless the task explicitly
requires it.

These entry points were inspected, not executed in the documentation review. Backend
resolution is not yet locked. **`npm test` is currently a success-only placeholder, not
test evidence.** Proposed root `make` targets are listed in
[R0](docs/REFACTOR_PLAN.md#r0---reproducible-baseline-and-test-infrastructure);
use them only after implementation. Report actual commands, not assumed passes.

## 3. Code and API rules

- Routes handle HTTP and authentication; service functions enforce resource access and
  coordinate work. Shared users may edit annotations, **not collection membership**.
  Keep those permission checks separate.
- Concrete persistence code belongs in `adapters/`, not in a duplicate feature repository.
  Keep SDK objects out of services. Classes, ports, and additional model layers are optional.
  Cross-feature calls use supported service/access functions and must not create cycles.
- Type changed public inputs/outputs. Use `UUID` internally and existing naming conventions.
  Preserve wire fields, nullability, operation IDs, canonical text, and stored offsets
  during moves. See the target architecture for feature ownership and roadmap contracts.

Never hand-edit `src/generated/api/`. The existing generation command is
`npm run sync-client-dev` in the frontend directory with the backend environment and
generator runtime available. Preserve the existing generator pin and frontend lockfile
unless explicitly upgrading. Review generated diffs; API changes include caller updates
and contract tests. Stream events also need tests: generation alone does not validate them.

## 4. Testing contract

**Test changed behavior at the lowest layer that proves it.** Each bug fix needs a
regression test; new behavior needs relevant success, denial, failure, and boundary cases.
A pure move may reuse existing coverage. Do not add a test at every layer by default.

| Change | Required evidence |
| --- | --- |
| Service or access rule | Fast tests with fakes; denied calls cannot read protected data, mutate, or call AI. |
| HTTP/schema contract | API validation, status/serialization tests, and API/client drift check. |
| Weaviate query or mutation | Real isolated-store test; include annotation-to-chunk-tag consistency where affected. |
| Store, composable, component | Frontend behavior tests; rendering/events where relevant. |
| Selection, streaming, navigation | Targeted browser test when browser behavior is essential. |
| Prompt/model/retrieval quality | Deterministic contract checks; a recorded small quality evaluation for intentional quality changes. |

Use pytest and retain existing unittest tests. Proposed frontend tools are Vitest/Vue Test
Utils and a small Playwright suite; R0 must verify compatible versions. Detailed fixtures,
regression cases, async guidance, and evaluation rules live in
[ADR 0005](docs/adr/0005-testing-contract.md).

Every test must run alone and in any order. Fixtures own mutable state and clean up their
resources. Fast checks must be offline: no keys, live providers, GPUs, or model downloads.
Use fixed vectors and test-owned stores for integration tests. Live tests and benchmarks
are separately marked, explicitly opted into, and not ordinary PR gates.

Assert observable outcomes, not private implementation details. Do not encode known bugs
as intended behavior, rely on exact LLM wording, or use reruns to conceal flakiness. No
arbitrary overall coverage percentage is required; changed access and mutation paths
still need meaningful tests. Required suites must not pass by selecting nothing or
silently skipping. Record unavailable checks honestly.

## 5. Data, failures, and safety

Keep successful steps in best-effort operations and report failed or uncertain steps;
no automatic rollback or repair system. A timed-out write is not necessarily absent.
AI generation is request-scoped: persist results incrementally, cancel/await remaining
work on disconnect, and retain saved results. See [ADR 0002](docs/adr/0002-best-effort-writes.md)
and [ADR 0003](docs/adr/0003-request-scoped-ai.md).

Storage/schema changes need an explicit, reviewed migration and compatibility plan.
Never mutate schema during a normal request. The current schema-reset script drops
collections; do not use it on shared stores. Removing old jobs must not delete users or
`tasks.db`. Data cleanup is separately reviewed, with a dry run and backup where destructive.

Do not commit secrets or log tokens/private text/prompts by default. Treat retrieved text
and AI output as untrusted data, not authorization or instructions to broaden scope.

## 6. Review and merge

Run fast checks for code PRs, relevant real-store tests for adapter/schema/search changes,
and browser tests for affected critical flows. Run the full isolated integration/smoke
suite before release. Documentation-only changes need link/format checks, not application
or provider runs. Required CI failures block merge/deploy; no blanket `continue-on-error`.

PRs state the purpose, behavior/API/schema changes, actual checks/results, unavailable
checks, and compatibility/migration notes. Add screenshots or a recording for meaningful
UI changes. A human reviews agent-authored work; access, destructive data changes, and
deployment changes require explicit human review. Keep CI execution isolated from
production credentials and deploy the tested artifact.
