# Agent instructions

The project rules for humans and agents are in [CONTRIBUTING.md](CONTRIBUTING.md); this
file adds only what is specific to coding agents and links to the canonical sections.
Do not restate those rules elsewhere; change them where they are defined.

## Before you start

- **Issues:** follow [ISSUE_WORKFLOW.md](docs/ISSUE_WORKFLOW.md#ai-assisted-issue-preparation).
  Normally refine the existing draft or user-feedback issue rather than replacing it.
  For `[User draft]` feedback, follow the [user-feedback guide](docs/USER_FEEDBACK_ISSUES.md),
  preserve the reporter's use case and do the technical refinement yourself instead of
  asking the reporter for a specification. Do not start implementation while material
  decisions remain unresolved; consult a maintainer about them.
- **Reading:** [CONTRIBUTING §1](CONTRIBUTING.md#1-working-on-a-change) lists what to read.
  From [ARCHITECTURE.md](docs/ARCHITECTURE.md), read the module map and the sections for the
  affected feature, not the whole document.
  For UI work, read the [UI guidelines](docs/UI_GUIDELINES.md).
- **Rules you must not break:** code structure and API rules in
  [CONTRIBUTING §3](CONTRIBUTING.md#3-code-and-api-rules); best-effort writes, request-scoped
  AI and data safety in [CONTRIBUTING §5](CONTRIBUTING.md#5-data-failures-and-safety); the
  confirmed product decisions (sharing, search representation, search chat scope, local
  real-time UI, text/image correspondence) in the
  [ADR index](docs/adr/README.md#confirmed-decisions). If a task seems to require changing
  one of them, stop and ask instead of working around it.
- **Python:** use the repository environment `.venv` for backend commands. Do not create
  another one unless the task requires it.

## What needs explicit authorization

Agents may create a topic branch, push it and open its PR for review. Without explicit
authorization for the current task, do not:

- push to `main`, force-update protected branches, merge PRs or deploy;
- connect to or modify shared server Weaviate, shared preview databases, production
  databases or other shared/production data;
- use production endpoints, real user text, paid model calls, GPU/model downloads or live
  evaluations;
- use a `local_data/` snapshot;
- run data cleanup, even when it looks incidental.

Before running a destructive Weaviate/schema/data-cleanup command, verify that the
configured endpoint is the local development instance. An endpoint called "test" is not
safe for that reason alone.

## Branches

Follow [CONTRIBUTING §6](CONTRIBUTING.md#6-branching-review-and-merge). Create each
assigned change's branch from the latest `origin/main`, not from a previous unmerged
topic branch, unless stacking is explicitly requested. Keep the branch to its issue.

## Running the application

Reuse the human-facing seeded environment exactly as described in
[DEVELOPMENT §1](docs/DEVELOPMENT.md#1-quick-start-the-seeded-local-application); do not
build another environment for agents. Run `make dev-backend` and `make dev-frontend` as
background processes and stop them when done. One instance serves the machine: check
`make dev-status` before starting it from another checkout. Its AI providers are fakes;
never point it at live providers to evaluate quality. `make dev-reset CONFIRM=yes`
destroys the development data: run it only when the task needs the seeded state, and
never against data the user is working with without asking. Automated tests use their
own disposable stores, never the development stores.

The Make targets are `make setup`, `check`, `api-generate`, `test-integration`,
`test-e2e`, `e2e-dev-*` and `dev-*` (all but the first three need Docker); `make dev`
does not exist.

## Tests and checks

Select tests by [CONTRIBUTING §4](CONTRIBUTING.md#4-testing-contract) and
[ADR 0005](docs/adr/0005-testing-contract.md); add regression tests for bugs and behavior
changes. Never weaken assertions, bypass CI, add blanket skips or hand-edit generated API
files to get a green result. A placeholder `npm test` is not a test pass.

For browser tests or UI work, do not rerun `make test-e2e` after every change: use the
[fast browser-test loop](docs/DEVELOPMENT.md#fast-browser-test-loop)
(`make e2e-dev-start`, `e2e-dev-test`, `e2e-dev-rebuild`, `e2e-dev-capture`,
`e2e-dev-stop`) and run the full `make test-e2e` once before handoff.

For a meaningful UI change, follow the
[UI change checklist](CONTRIBUTING.md#ui-change-checklist) before the first push,
including its screenshot upload steps. Check `gh --version` and `gh auth status` first;
if `gh` is older than 2.99, ask the user to update it rather than working around it. If
the upload fails, report the blocker and ask the user to upload in the browser; do not
set up external hosting such as gists. Attach only synthetic/fixture screenshots, and do
not present screenshots you did not take or checks you did not run.

## Handoff

Fill in the [pull request template](.github/pull_request_template.md) and request review.
Report the scope, changed behavior and files, checks actually run, checks not run and
why, blockers, and remaining risks or decisions. Link newly discovered actionable gaps to
a GitHub issue and update the relevant active documentation.
