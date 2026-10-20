# Contributing to SemANT

The **`main` branch is the canonical base and pull-request target** for routine
development. These guidelines apply to human- and agent-authored changes. [ARCHITECTURE.md](docs/ARCHITECTURE.md) describes the implementation;
[TARGET_ARCHITECTURE.md](docs/TARGET_ARCHITECTURE.md) records continuing design constraints.
New contributors can begin with [START_HERE.md](docs/START_HERE.md).
For drafting, refining and taking ownership of issues, see the
[issue workflow](docs/ISSUE_WORKFLOW.md); this document governs implementation
and PR requirements.

## 1. Working on a change

Read the affected code, callers, and tests, plus
[current architecture](docs/ARCHITECTURE.md), the
[continuing design principles](docs/TARGET_ARCHITECTURE.md), relevant
[ADRs](docs/adr/README.md), and [active follow-ups](docs/TODO.md).
Do not reopen settled product behavior or treat a proposal as implemented code.
Historical decisions and delivery records are available in the
[archive](docs/archive/refactor-2026/README.md), not as active acceptance criteria.

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
| `make lock` / `make lock-check` | Regenerate the backend Python locks / fail if either is stale for its requirements (pip-tools, needs network). |
| `make api-generate` | Export the OpenAPI schema without connecting to services and regenerate `src/generated/api` from it. `make api-check` fails if the committed client differs from a fresh generation. |
| `make test-integration` | Start a throwaway Weaviate container, run the `integration` tests against it, remove it. Needs Docker. |
| `make test-e2e` | Build the frontend and run the Playwright smoke suite against the deterministic backend profile (throwaway Weaviate, fixture corpus, fake AI providers). Needs Docker; installs Playwright's Chromium on first use. |
| `make dev-up` / `dev-backend` / `dev-frontend` | The interactive application: a persistent, seeded development Weaviate and SQLite (initialized on first use only), the backend with `--reload` and fake AI providers, the Quasar dev server with hot reload. `make dev-down` stops Weaviate and keeps the data; `make dev-reset` (confirmation required) reseeds. Needs Docker. See [DEVELOPMENT.md](docs/DEVELOPMENT.md#1-quick-start-the-seeded-local-application). |
| `make e2e-dev-start` / `e2e-dev-test ARGS=...` / `e2e-dev-stop` | Optional fast loop for browser-test work: keep one seeded profile running and rerun selected specs against it (`scripts/e2e-dev.sh`, see [DEVELOPMENT.md](docs/DEVELOPMENT.md#fast-browser-test-loop)). Not a substitute for `make test-e2e` before a PR. |

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
(cd semant_demo_frontend && npm run api-check)

# make api-generate
(cd semant_demo_frontend && npm run api-generate)

# make test-integration
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_backend && ../.venv/bin/python -m pytest -m integration'

# make test-e2e
(cd semant_demo_frontend && npx playwright install --only-shell chromium)
scripts/with-test-weaviate.sh sh -c 'cd semant_demo_frontend && env -u DISPLAY PYTHON=../.venv/bin/python npm run test:e2e'

# make dev-up / dev-backend / dev-frontend / dev-down / dev-reset
scripts/local-dev.sh up | backend | frontend | down | reset
```

Backend dependencies (`semant_demo_backend/`, target CPython 3.12 on Linux x86_64):

- `requirements.txt` declares the direct runtime dependencies; `requirements-dev.txt` adds
  test/lint tools. Do not install either directly; they are inputs to the locks.
- `requirements-dev.lock` pins and hashes the full development set; `make setup` and CI
  install it.
- `requirements-runtime.lock` pins and hashes only the runtime closure; `deploy/Dockerfile`
  installs it with `--require-hashes`. It is compiled with the dev lock as a constraint, so
  production gets exactly the versions CI tests.

After changing either requirements file, run `make lock` (`scripts/python-locks.sh update`,
with `pip install pip-tools==7.6.2` in `.venv`) and review both lock diffs. Existing pins are
kept; upgrade deliberately, e.g. for a security fix, with
`LOCK_COMPILE_ARGS="--upgrade-package NAME" make lock` (or `--upgrade` for everything), and
review the changed versions. The fast tests (`tests/test_dependency_locks.py`) fail when a
lock no longer covers the declared requirements or the two locks pin different runtime
versions; the CI `python-locks` job installs the runtime lock on its own (`pip check`,
OpenAPI export) and re-resolves both locks. Re-resolution takes minutes, so on a PR it runs
only when a path in `LOCK_INPUTS` of `scripts/python-locks.sh` changed (requirements, locks,
the script, its test, or any workflow); pushes to `main`, tags and manual runs always
re-resolve, and `python-locks-drift.yml` re-resolves `main` weekly. Run `make lock-check` or
the drift workflow manually to re-resolve on demand. Deployments wait for the job. Locks must keep their
hashes: CI installs them with `--require-hashes` from a cache shared between runs (see
`deploy/README.md`). Frontend versions are
pinned by `package-lock.json`; Vitest 0.23 is the last line supporting the Vite 2 used by
`@quasar/app-vite` 1.

Known legacy findings are recorded, not hidden:

- `npm run typecheck` runs vue-tsc against `typecheck-baseline.json`, which is empty since
  the previous implementation. New errors fail; never add entries to make the check pass.
- Ruff enforces syntax errors, undefined names and unused imports (`pyproject.toml`).
  Widen the rule set as code is cleaned up rather than adding blanket ignores.
- ESLint warnings are reported but do not fail the check; errors do.

Run the application with the seeded local environment: `make dev-up` once per session,
then `make dev-backend` and `make dev-frontend` in two terminals, and open
<http://localhost:9000> (e.g. `owner` / `owner-password-1`). It needs no snapshot, server
access or AI credentials; AI providers are deterministic fakes. Its data lives in a Docker
volume and `.dev-data/` (ignored by git) and survives restarts; `make dev-reset` restores the
fixture corpus after showing what it destroys. Humans and coding agents use the same
targets; there is no separate agent environment. Tests build apps with
`create_app(Config(environ=...))` and never use the development stores.

A realistic database snapshot under `local_data/` is an optional, explicitly authorized
workflow ([DEVELOPMENT.md](docs/DEVELOPMENT.md#5-advanced-an-authorized-realistic-snapshot)).
Fast tests must not depend on any development data. Real-store automated tests
must use test-owned data as described in the testing contract.

Do not use shared server or production databases unless the task explicitly
requires it.

`make dev` does not exist; use the `dev-*` targets above. Report actual commands, not assumed passes.

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

`npm run api-check` / `api-generate` and `make api-check` / `api-generate` are the same
check: without `PYTHON`, `scripts/api-client.sh` uses the repository's `.venv/bin/python`
from any directory and stops with instructions when it is missing or lacks the backend
packages, rather than running another `python` from `PATH`. A relative `PYTHON` path is
resolved from the directory the script starts in (`semant_demo_frontend` under `npm run`).
The pinned generator (`openapitools.json`, run through `npx --no-install
openapi-generator-cli`) needs Java 11+ on `PATH`; CI sets `OPENAPI_GENERATOR` to the same
version's jar instead.

ESLint's core `no-undef` checks JavaScript only, because it misreads TypeScript type names;
`npm run typecheck` reports undefined names in TypeScript and Vue files, so components must
use `<script lang="ts">` (enforced by lint). `test/unit/devTooling.spec.ts` covers both
defaults.

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
and use a throwaway Weaviate with synthetic data from
`tests/fixtures/corpus.json`. Tests clear and reseed application data; the schema is
recreated only when necessary. The Playwright smoke suite in
`semant_demo_frontend/test/e2e` reads the same corpus. See
[DEVELOPMENT.md](docs/DEVELOPMENT.md#4-testing-versus-development-data) for the store
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
historical name) holds user accounts and RAG feedback: never delete or recreate it as cleanup. Data cleanup is separately reviewed, with a dry run and backup where destructive ([DATA_MAINTENANCE.md](docs/DATA_MAINTENANCE.md)).

Do not commit secrets or log tokens/private text/prompts by default. Log exception
classes, not provider or storage exception messages, and return fixed client errors for
provider failures ([OBSERVABILITY.md](docs/OBSERVABILITY.md#add-a-log-field)). Treat retrieved text
and AI output as untrusted data, not authorization or instructions to broaden scope.

## 6. Branching, review and merge

Start each change from the **latest `origin/main`**, not an old feature branch.
Open pull requests **into `main`**.

1. Create or link a scoped GitHub issue when appropriate and give the PR one clear purpose.
2. Fetch the latest default branch and create a short-lived issue/topic branch:

   ```sh
   git fetch origin
   git switch -c <issue>-short-description origin/main
   ```

3. Implement with relevant tests, docs and generated-client changes. Before review, fetch
   again and integrate any new `main` commits into **your feature branch** (for example,
   `git merge origin/main`); resolve conflicts and rerun impacted checks. Do not force-push
   shared/protected branches.
4. Push the topic branch and open a PR whose base is `main`. State outcomes, compatibility,
   checks actually run, and any deployment/data risk.
5. Obtain the required human review and passing GitHub required checks; merge through GitHub.
   Do not push directly to protected `main` or bypass its rules. Delete the merged topic
   branch when no longer needed.

Run fast checks for code PRs, relevant real-store tests for adapter/schema/search changes,
and browser tests for affected critical flows. Run the full isolated integration/smoke
suite before release. Documentation-only changes need link/format checks, not application
or provider runs. Required CI failures block merging; PR previews intentionally deploy even
when checks fail for manual diagnosis ([deploy/README.md](deploy/README.md#pr-preview-credentials)).

PRs state the purpose, behavior/API/schema changes, actual checks/results, unavailable
checks, and compatibility/migration notes. Meaningful UI changes follow the
[UI change checklist](#ui-change-checklist). Agent-authored implementation must be reviewed before merge, preferably by a
separate reviewer from the implementing agent. Access-control changes, destructive
data changes, deployment changes, and other high-risk changes require explicit
human review. Keep CI execution isolated from production credentials and deploy the tested artifact.

### UI change checklist

Applies to a **meaningful UI change**: new or changed layout, components, responsive
behavior, interaction or visible states. Match verification effort to what the change
could reasonably affect; not every UI change needs all three widths. Backend-only and
non-visual PRs, documentation, and trivial cosmetic edits (a label, a colour token) need
no checklist. A small, localized styling change generally needs only a spot-check of
the affected component; note omitted evidence if a reviewer might expect it.

1. **Inspect relevant contexts before the first review/push.** For new views, shared
   layouts or responsive changes, check wide desktop, constrained desktop (both sidebars
   open where present) and phone. For local interaction changes, check the affected
   states and viewports; for isolated styling, check the relevant component and context.
   Do not inspect unaffected widths merely to complete the checklist.
   `make e2e-dev-capture` can render the three widths against the deterministic profile
   (1920×1000, 1280×900, 390×844); pass your spec to capture the changed state
   ([DEVELOPMENT.md](docs/DEVELOPMENT.md#fast-browser-test-loop)).
2. **Attach proportionate evidence to the PR:** before/after or final screenshots, or
   a short recording, showing the changed state (e.g. selected, expanded, empty, signed
   out) at relevant widths, not just the default view. Unaffected widths need no
   screenshots. If a relevant context or state could not be captured, say which and
   why; do not imply it was.
3. **Review what applies:** card/title/metadata alignment, text overflow and wrapping
   (long titles, narrow toolbars), selected/hover/focus states, controls gated by
   authorization or ownership, keyboard and touch interaction, and direct links/reloads
   into the view. Write a browser test only where the [testing contract](#4-testing-contract)
   calls for one; the checklist is a review aid, not a test requirement.
4. **Report checks honestly:** the commands run and their results, and any full
   `make test-e2e` run still outstanding. Targeted specs are for iteration; full
   validation is still due under the normal merge rules above.

For a new UI issue, the [UI change template](.github/ISSUE_TEMPLATE/ui-change.md) asks for
the requested behavior, expected appearance and target widths, a reference image if one
exists, and non-goals. Describe appearance in words or with a rough sketch; pixel-perfect
mockups are not required, and non-visual bugs need none of this.
