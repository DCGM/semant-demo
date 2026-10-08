# Contributing to SemANT

Draft for adoption, updated 2026-10-08 (after the architecture refactor #198–#210). Applies
to human and agent-authored changes. [ARCHITECTURE.md](docs/ARCHITECTURE.md) describes the
current code; [TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md) the intended direction.

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
Toolchain: Python 3.12 (backend), Node 22 (`semant_demo_frontend/.nvmrc`), and Java 11+
only for regenerating the API client. From the repository root:

| Command | What it does |
| --- | --- |
| `make setup` | Create `.venv` if missing, install `semant_demo_backend/requirements-dev.lock` and the backend package, run `npm ci`. |
| `make check` | Fast offline checks: backend Ruff and fast pytest suite, frontend ESLint, Vue type check and Vitest, generated-client drift. No keys, GPU, Weaviate or AI services. |
| `make api-generate` | Export the OpenAPI schema without connecting to services and regenerate `src/generated/api` from it. |
| `make test-integration` | Start a throwaway Weaviate container, run the `integration` tests against it, remove it. Needs Docker. |
| `make test-e2e` | Build the frontend and run the Playwright smoke suite against the deterministic backend profile (throwaway Weaviate, fixture corpus, fake AI providers). Needs Docker; installs Playwright's Chromium on first use. |

Set `PYTHON=...` to use another interpreter. Without Make, run the same commands:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r semant_demo_backend/requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e semant_demo_backend
(cd semant_demo_frontend && npm ci)

# make check
(cd semant_demo_backend && ../.venv/bin/python -m ruff check .)
(cd semant_demo_backend && ../.venv/bin/python -m pytest -m "not integration and not live and not benchmark")
(cd semant_demo_frontend && npm run lint && npm run typecheck && npm test)
(cd semant_demo_frontend && PYTHON=../.venv/bin/python npm run api-check)

# make api-generate
(cd semant_demo_frontend && PYTHON=../.venv/bin/python npm run api-generate)

# make test-integration
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && ../.venv/bin/python -m pytest -m integration'

# make test-e2e
(cd semant_demo_frontend && npx playwright install --only-shell chromium)
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_frontend && PYTHON=../.venv/bin/python npm run test:e2e'
```

Dependencies: `requirements.txt` holds runtime dependencies (used by the production image);
`requirements-dev.txt` adds test/lint tools; `requirements-dev.lock` pins the full set.
After changing either file, regenerate the lock with pip-tools
(`pip-compile --allow-unsafe --no-emit-index-url --strip-extras -o requirements-dev.lock
requirements-dev.txt` in `semant_demo_backend`) and review the diff. Frontend versions are
pinned by `package-lock.json`; Vitest 0.23 is the last line supporting the Vite 2 used by
`@quasar/app-vite` 1.

Known legacy findings are recorded, not hidden:

- `npm run typecheck` runs vue-tsc against `typecheck-baseline.json`, which is empty since
  #210. New errors fail; never add entries to make the check pass.
- Ruff enforces syntax errors, undefined names and unused imports (`pyproject.toml`).
  Widen the rule set as code is cleaned up rather than adding blanket ignores.
- ESLint warnings are reported but do not fail the check; errors do.

Run the backend from `semant_demo_backend` using
`python -m uvicorn semant_demo.main:app --reload` and the frontend with `npm run dev`.
SQL defaults to a relative `tasks.db`; set `SQL_DB_URL` to use another database. Tests
build apps with `create_app(Config(environ=...))`.

For normal development, use the local development databases described in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Mutable development database state
belongs under `local_data/` and must not be committed.

Fast tests must not depend on this database snapshot. Real-store automated tests
must use test-owned data as described in the testing contract.

Do not use shared server or production databases unless the task explicitly
requires it.

`make dev` (proposed in
[R0](docs/REFACTOR_PLAN.md#r0---reproducible-baseline-and-test-infrastructure)) does not
exist; run the backend and frontend as above. Report actual commands, not assumed passes.

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

Never hand-edit `src/generated/api/`. Regenerate it with `make api-generate`, which
generates into an empty directory so stale files are removed; `make check` fails when the
committed client differs from the backend schema. Preserve the existing generator pin
(`openapitools.json`) and frontend lockfile unless explicitly upgrading. Review generated diffs; API changes include caller updates
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

Use pytest and retain existing unittest tests. Tests without an `integration`, `live` or
`benchmark` marker are fast tests; `tests/conftest.py` refuses their network connections,
including loopback. Use `tests/fakes.py` for AI providers. Frontend unit/component tests
use Vitest and Vue Test Utils under `semant_demo_frontend/test/unit`.

Real-store tests live in `semant_demo_backend/tests/integration` (marked `integration`)
and use a test-owned Weaviate seeded with the synthetic corpus in
`tests/fixtures/corpus.json`, reset for every test. The Playwright smoke suite in
`semant_demo_frontend/test/e2e` reads the same corpus. See
[DEVELOPMENT.md](docs/DEVELOPMENT.md#11-testing-versus-development-data) for the store
ownership rules. Detailed fixtures, regression cases, async guidance, and evaluation rules
live in [ADR 0005](docs/adr/0005-testing-contract.md).

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
collections; do not use it on shared stores. The SQL database (`tasks.db` by default, a
historical name) holds user accounts and RAG feedback: never delete or recreate it as cleanup. Data cleanup is separately reviewed, with a dry run and backup where destructive.

Do not commit secrets or log tokens/private text/prompts by default. Treat retrieved text
and AI output as untrusted data, not authorization or instructions to broaden scope.

## 6. Review and merge

Run fast checks for code PRs, relevant real-store tests for adapter/schema/search changes,
and browser tests for affected critical flows. Run the full isolated integration/smoke
suite before release. Documentation-only changes need link/format checks, not application
or provider runs. Required CI failures block merge/deploy; no blanket `continue-on-error`.

PRs state the purpose, behavior/API/schema changes, actual checks/results, unavailable
checks, and compatibility/migration notes. Add screenshots or a recording for meaningful
UI changes. Agent-authored implementation must be reviewed before merge, preferably by a
separate reviewer from the implementing agent. Access-control changes, destructive
data changes, deployment changes, and other high-risk changes require explicit
human review. Keep CI execution isolated from production credentials and deploy the tested artifact.
