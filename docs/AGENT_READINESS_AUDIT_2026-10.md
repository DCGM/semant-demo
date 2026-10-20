# Codebase and tooling readiness for agent-assisted development, 2026-10-20 (#413)

This audit asks whether a student or a coding agent can take a bounded issue, find the code,
change it, run the right checks and hand over a reviewable PR quickly and safely. It covers
the code, tests, CI and local tooling. The companion documentation and onboarding audit is
[#412](https://github.com/DCGM/semant-demo/issues/412); documentation findings here are only
those found while running the workflows, and they are handed over to it.

## Conclusions

1. **Ready for routine, supervised student and agent contributions. There are no P1
   blockers.** A clean checkout installs and passes `make check` in under 3 minutes. Every
   feature has one place for its routes, service, schemas and adapters, with no import
   cycles. Each test layer has a measured loop of seconds to tens of seconds. AI providers
   are fakes, fast tests are offline by construction and real-store tests own their store.
   Two bounded trials, one backend and one frontend, each went from issue to a
   passing regression test in a single short iteration (see [Trials](#change-trials)).
2. **The largest remaining risk is outside the application:** the old `weaviate_utils/`
   scripts delete data or drop collections as soon as they are run. They have no
   arguments or confirmation and use hard-coded `localhost` ports (finding G1, [#444](https://github.com/DCGM/semant-demo/issues/444)).
   Everything else that writes to a store has a guard.
3. **The largest remaining friction is browser-test confidence, which is already tracked:**
   CI does not run the E2E suite ([#212](https://github.com/DCGM/semant-demo/issues/212)),
   so the full local run falls on each contributor, and three E2E specs are known to be
   flaky ([#348](https://github.com/DCGM/semant-demo/issues/348),
   [#410](https://github.com/DCGM/semant-demo/issues/410),
   [#429](https://github.com/DCGM/semant-demo/issues/429)).
4. **The code does not need a refactor program.** The deviations found are local: the RAG
   pipelines' style and provider coupling, two accepted frontend data-access patterns, and
   a few large single-file components. None cascades into unrelated layers. They are listed
   as P3 and should be fixed only when a change touches them.
5. **The main avoidable agent cost is reading:** the files an agent must read before
   editing total about 115 KB (≈29k tokens). `ARCHITECTURE.md` alone is 78 KB. This is
   handed over to #412 (finding D1).

This PR also makes two small tooling and documentation fixes found during the audit (see
[Changes in this PR](#changes-in-this-pr)).

## Baseline

| Item | Value |
|---|---|
| Audited commit | `main` at `bf85cbb` (2026-10-20) |
| Host | Linux 6.8 x86_64, 12 CPUs; Docker 27.1.1 |
| Toolchain | Python 3.12.15 (`.venv`), Node 22.22.2, npm 10.9.7, OpenJDK 11.0.32, gh 2.102.0 |
| Clean environment | a fresh `git worktree` of `origin/main` with its own `.venv` and `node_modules`, created by `make setup`; removed afterwards |
| Data | synthetic fixtures and test-owned throwaway Weaviate containers only; no development, shared or production store was opened, no provider was called |

Timings are wall-clock times of single runs on this host, with pip and npm caches warm. CI
times come from the PR run [39432207884](https://github.com/DCGM/semant-demo/actions/runs/39432207884)
(self-hosted `semant-ci`).

## Measured feedback loops

| Loop | Command | Time |
|---|---|---|
| Clean setup | `make setup` in a fresh worktree (warm caches) | 60 s (`npm ci` alone: 6 s) |
| Full fast checks, clean checkout | `make check` | 1 min 48 s, all passing |
| Backend fast suite | `make check-backend` (Ruff + 1,232 tests) | 63 s (Ruff 0.05 s, collection 4 s) |
| One backend test file | `pytest tests/test_search_service.py` | 3 s (2.3 s of it is importing the app) |
| Backend red → green | edit plus `pytest -k` on one test | 5.4 s per run |
| Frontend lint / types / unit | `npm run lint` / `typecheck` / `npm test` (390 tests) | 10 s / 21 s / 14 s |
| One Vitest file | `npx vitest run test/unit/searchResultCard.spec.ts` | 3.6 s |
| Generated client drift | `npm run api-check` | 6.5 s |
| Integration, full | `make test-integration` (337 tests) | 3 min 49 s |
| Integration, one file | `test_chunk_tags.py` against a throwaway Weaviate | 29 s (container ready in ~1 s) |
| Integration, one test | `make test-integration ARGS="… -k bulk"` (this PR) | 8.5 s |
| E2E loop start | `make e2e-dev-start` | 28 s |
| One E2E spec | `make e2e-dev-test ARGS="test/e2e/searchResultCards.spec.ts"` | 16 s (6 tests) |
| Frontend edit → E2E | `make e2e-dev-rebuild` | 21 s |
| UI captures, three widths | `make e2e-dev-capture` | 68 s (33 states) |
| Full E2E on a warm profile | `make e2e-dev-test ARGS=--all` | 3 min 38 s (98 tests, all passing) |
| Full E2E, cold | `make test-e2e` (build, fresh Weaviate and profile) | 3 min 59 s (98 tests, all passing) |
| CI per PR | the five required jobs plus the preview | ~5 min wall; Integration 312 s, Backend 147 s, Locks 44 s, Frontend 31 s, Drift 13 s, preview 68 s |

All targeted loops take seconds to tens of seconds. Only the full integration and E2E
suites are minute-scale. The fast E2E loop from #272 saves the ~30 s build and startup on
each iteration; for the whole suite, a cold run costs only about 20 s more. Its guards worked as documented: `e2e-dev-test` without a spec refuses and
says to pass `--all`, and `status` reports whether the build is stale.

## What works well

Keep these; they are why the trials were short.

- **Predictable backend layout** ([ADR 0001](adr/0001-simple-feature-monolith.md)). The 12
  route modules contain no control flow (0 `if`/`for`/`try` statements outside one quota
  route): each parses HTTP and calls a service. A module-level import graph of the 131
  application modules has **no cycles**. The cross-feature dependencies are the documented
  ones (access, search retrieval, quota, schemas). The Weaviate SDK appears only in
  `adapters/`, `maintenance/` and `bootstrap.py`.
- **Offline by construction.** `tests/conftest.py` refuses any socket connection, including
  loopback, in unmarked tests. AI providers are fakes (`tests/fakes.py`,
  `tests/fake_providers.py`), and the dev and E2E profiles point every provider URL at
  fakes. Nothing in `make check` needs a key, GPU or download.
- **Store ownership.** `scripts/with-test-weaviate.sh` uses a uniquely named container on
  random loopback ports. The tests claim it with a per-run token and refuse any other
  instance, including non-loopback hosts. The seeded development environment refuses
  stores without its marker and resets only with `CONFIRM=yes`.
- **Actionable diagnostics.** In a checkout without `.venv`, `api-check` names the missing
  interpreter and the fix (`make setup` or `PYTHON=`). The offline guard names the address
  and the fix ("use a fake or mark the test as integration/live"). The typecheck baseline is
  empty and the lock checks explain themselves.
- **Generated-contract discipline.** The client is generated into an empty directory, and
  drift is a required CI check.
- **Lint scope is deliberate, not missing.** Widening Ruff to `F,B` adds 198 findings in
  application code. The inspected categories are false positives or style: B008 is FastAPI
  `Depends`, B023 flags closures that are awaited immediately, and F811 flags imported
  pytest fixtures (there are no duplicate test names). Widening the lint would add noise,
  not catch bugs.
- **Clean code hygiene.** Application code contains no `print` calls, no TODO or FIXME
  comments and no logged user text (and tests check that RAG never logs questions or
  passages).
- **Parallel checkouts work.** A worktree can reuse the main checkout's `.venv` through
  `PYTHON=`: tests, `export_openapi.py` and the E2E server run from the checkout's
  `semant_demo_backend`, so they import that checkout's code (verified). This was
  undocumented; this PR documents it.

## Findings

Severity: **P1** blocks routine contributions; **P2** is repeated friction or a real safety
gap; **P3** is minor. "New" findings were not tracked before this audit.

| # | Sev. | Finding and evidence | Impact | Smallest fix | Tracking |
|---|---|---|---|---|---|
| G1 | P2 | **Destructive `weaviate_utils/` scripts run on import.** `delete_all.py` (`collections.delete_all()` on `localhost:8082`), `delete_collection.py`, `delete_all_objects.py` and `delete_object.py` run at module level, with hard-coded ports, no arguments and no confirmation. `build_db/create_schema.py` drops all application collections first, and `add_*_prop.py` / `create_span_collection.py` change the schema the same way. Only a README warning protects them, and a local SSH tunnel to a server store also appears as `localhost`. | A single mistaken `python weaviate_utils/…` by an agent or student can wipe a store; the in-repo `maintenance/` tools are guarded, these are not. | Move the one-off delete/schema scripts to an archive (or remove them), and give the remaining writers explicit `--host/--port` without defaults, a printed endpoint and object count, and `--yes`. | **New:** [#444](https://github.com/DCGM/semant-demo/issues/444) |
| T1 | P2 | **E2E is not run in CI.** The 98-test suite runs only when a contributor runs it, and it takes 3–4 min warm. | Browser regressions depend on every contributor's discipline; reviewers cannot see an E2E result. | As specified in #212. | [#212](https://github.com/DCGM/semant-demo/issues/212) |
| T2 | P2 | **Three known E2E flakes.** In the trial, #410 did not reproduce in 20 repetitions, and its suggested one-line `expect.poll` fix passed (see [trial](#frontend-trial-410)). | A failing full run cannot be told apart from a regression without rerunning, which the testing contract forbids as a fix. | Fix each as specified on its issue; #410 is a one-line change. | [#348](https://github.com/DCGM/semant-demo/issues/348), [#410](https://github.com/DCGM/semant-demo/issues/410), [#429](https://github.com/DCGM/semant-demo/issues/429) |
| T3 | P2 | **No documented targeted integration run.** `make test-integration` always ran all 337 tests (3 min 49 s). Running one file (29 s) or one test (8.5 s) meant writing the `scripts/with-test-weaviate.sh sh -c '…'` command yourself. | Adapter changes were validated with the full suite or not at all while iterating. | `ARGS` for `make test-integration`, plus one paragraph of documentation. | **Fixed in this PR** |
| D1 | P2 | **Pre-edit reading is about 115 KB.** AGENTS.md lists ARCHITECTURE (78 KB, with 7 single paragraphs over 1,500 characters, e.g. the 7 KB frontend networking/session paragraph), CONTRIBUTING (19 KB), TODO, TARGET_ARCHITECTURE and the ADRs before any edit. | About 29k tokens of context before the first line of code, mostly about features the change does not touch. | Route readers by task: the module map plus the section of the affected feature. Split the longest paragraphs. Documentation only. | → [#412](https://github.com/DCGM/semant-demo/issues/412) |
| T4 | P3 | **`make test-e2e` output is mostly backend request logs.** The web server's stderr is piped, so every request logs `INFO … HTTP request completed` (7,124 of the 7,476 output lines of one cold run). | Failures are buried, and an agent reading the output spends context on noise. | Run `tests.e2e_server` at `LOG_LEVEL=WARNING` unless a variable asks for more. | New, not filed; fold into #212 or the next E2E tooling change |
| T5 | P3 | **A passing Vitest run prints 252 lines,** including stack traces of jsdom's `window.scrollTo` "Not implemented" and Vue warnings about a missing route injection in `documentViewAiCleanup.spec.ts`, plus `console.error` output from tests that expect errors. | A real failure is harder to spot. | Stub `scrollTo` in the Vitest setup, provide the router in those tests, and silence errors the tests expect. | New, not filed (small) |
| T6 | P3 | **CI test jobs have no `timeout-minutes`** (the deploy jobs have 10–30). | A hung job holds the self-hosted runner for GitHub's 6 h default. No hang has been observed. | Add timeouts of about 3× the observed duration. | New, not filed; fold into #393, which reworks these jobs |
| C1 | P3 | **The RAG pipelines are the stylistic outlier.** `features/rag/pipelines/` has 747- and 434-line classes, star-imported prompts (24 Ruff F405 findings) and `openai`/`langchain_google_genai` exception types caught in feature code. `registry.py` uses 3-space indentation. The bug in #402 lives here. | More reading for RAG changes; this does not affect other features. | Fix locally when touching RAG (#370, #402); no refactor program. | [#370](https://github.com/DCGM/semant-demo/issues/370), [#402](https://github.com/DCGM/semant-demo/issues/402) |
| C2 | P3 | **Two frontend data-access patterns.** 13 consumers use a feature's `use…Repository()` wrapper, and 11 call `useApi()` directly; ARCHITECTURE allows both. The wrappers mostly rename generated operation IDs such as `getCollectionTagsApiUserCollectionsCollectionIdTagsGet`. | Small: a contributor follows the pattern of the file at hand. | None now. Changing the operation IDs would churn the whole client and break the "preserve operation IDs" rule. | — |
| C3 | P3 | **A few large single-file components:** `DocumentReaderPage.vue` (975 lines), `AiAssistPanel.vue` (866) and `SearchPage.vue` (823). The logic is already in composables. | Reading cost for changes in those views only. | Split only along a concrete change, as #277 decided for `SearchPage.vue`. | #277 (decision) |
| C4 | P3 | **Small dead code:** 5 ESLint warnings (unused `emit` and notifications), `console.log` calls and a `TODO implement toggle favorite --- IGNORE ---` in `CollectionCard.vue`, `TagsTable.vue`. Two RAG configuration directories with names like `09_NEW_incremental_ollama.yaml` and `01_ollama_default_config .yaml` (with a space). | Misleading for a newcomer looking for "the" configuration. | Remove when touching those files. | — |
| P1′ | P3 | **Issues can hide an open decision.** #402 says the expected behavior is "decided by the RAG owners". A schema-level fix (`min_length` on `sources`) would also break an existing test that sends `sources=[]` on purpose (`test_llm/test_features.py:368`). | An agent following AGENTS.md must stop and ask, which is correct but costs a round trip. | Record the decision on the issue before labelling it for contributors (the [issue workflow](ISSUE_WORKFLOW.md) already asks for this). | [#402](https://github.com/DCGM/semant-demo/issues/402): decision still open |

Not findings, but checked:

- **Secrets:** no tracked keys (pattern search for OpenAI, Google, GitHub tokens and private
  keys). `.env` is ignored and only `*.example` files are tracked.
- **Fork PR CI:** fork PRs skip the self-hosted jobs, which makes skipped checks look
  green. This is tracked in #393 and not redesigned here.
- **Docs-only PRs** run the full CI and a preview (~5 min). This costs runner time but
  not much waiting; path filters on required checks would need the care described in
  #393, so no change is proposed.

## Change trials

Both trials ran in a throwaway worktree of `origin/main`, reusing `.venv` through `PYTHON=`.
Neither change is merged by this PR. The patches are in the PR description, so they can be
reused when the issues are taken up.

### Backend trial (#402)

*Task:* the adaptive RAG's Explain must not answer 500 when `sources`, the selection or the
answer is empty.

- **Locating the code** took the issue text, `features/rag/routes.py` → `service.explain`
  → `pipelines/incremental_rag.py:explain_selection`, and the existing fixtures in
  `tests/test_llm/test_features.py` (`load_rag`, a fake LLM, `metrics`). That is 4 files
  and the predictable route → service → pipeline path.
- **Regression test first:** one parametrized test (3 cases) failed with the reported
  `UnboundLocalError`. A guard that returns a fixed explanation before any model call made
  it pass. The diff is +15/−1 lines in 2 files, the loop took 5.4 s, and Ruff took 0.05 s.
- **Friction:** the issue leaves the expected response (400 or a message) to the RAG
  owners (P1′). The pipeline file is 747 lines in the RAG style (C1). Nothing else got in
  the way.

### Frontend trial (#410)

*Task:* stop `searchResultCards.spec.ts` from reading the selected background during its
CSS transition.

- `make e2e-dev-start` took 28 s. 20 repetitions of the two desktop tests (`--repeat-each
  10`) did not reproduce the flake (45 s).
- The one-line fix suggested on the issue (`await expect.poll(background).not.toBe(unselected)`)
  passed the spec in 16 s, and ESLint on the file took 1.7 s.
- A source edit to `SearchResultCard.vue` followed by `e2e-dev-rebuild` took 21 s, and the
  three-width capture took 68 s. The full warm suite (98 tests) passed.
- **Friction:** a flake that cannot be reproduced on demand cannot be proven fixed. The
  change is still a strict improvement, and the issue can be closed after it has passed
  in CI once #212 runs E2E there.

## Recommendations

In order of value for the cost. None of these is a prerequisite for routine contributions.

1. **Guard or archive the destructive `weaviate_utils/` scripts (G1, new issue).** This is
   the one safety gap a well-behaved agent could still fall into ([#444](https://github.com/DCGM/semant-demo/issues/444)).
2. **Fix the three E2E flakes, then run E2E in CI (T2, T1; #410/#348/#429, then #212).** A
   flaky suite would make the CI job unusable as a required check, so fix the flakes first.
3. **Shorten the pre-edit reading (D1 → #412).** This is the largest cost per task, at no
   risk to the code.
4. **Quiet the test output (T4, T5)** in the next PR that touches the E2E server or the
   Vitest setup.

Measured savings from changes already made in this PR: iterating on one integration test
file takes 29 s instead of 3 min 49 s (T3).

## Changes in this PR

- `Makefile`: `make test-integration ARGS="…"` passes test selection to pytest. Without
  `ARGS` it behaves exactly as before.
- `docs/DEVELOPMENT.md` and `CONTRIBUTING.md`: the targeted integration loop, and how to
  work in parallel checkouts (sharing `.venv` through `PYTHON=`, `npm ci` per checkout, and
  E2E port spacing).
- This report.

## Not executed

- `make lock-check` (re-resolves both locks over the network for minutes), because no lock
  input changed.
- `make dev-up` and the seeded development environment, which a development instance on
  this machine may own; its behavior was reviewed from #438 and its documentation.
- A truly cold setup with empty pip and npm caches. The 60 s setup time is with warm
  caches.
- Concurrent E2E runs on moved ports. The port derivation (`port`, `+1`, `+2`) was read
  from `tests/e2e_server.py`, not exercised.
- A fork-based contribution (#393), and any live provider, GPU or shared store, as the
  audit's scope requires.
