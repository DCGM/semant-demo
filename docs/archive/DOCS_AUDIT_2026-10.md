# Contributor documentation audit, 2026-10-20 (#412)

A dated record of the documentation and onboarding audit of `main` at `bf85cbb`. It is
evidence, not current instructions. Its "Fixed in #443" items were fixed by
[#443](https://github.com/DCGM/semant-demo/pull/443), and the remaining work is tracked in the
linked issues. Discussion is on [#412](https://github.com/DCGM/semant-demo/issues/412).

**Method.** I made a fresh `git clone` at `bf85cbb` on Ubuntu 22.04.4 (Python 3.12.15, Node 22.22.2, npm 10.9.7, OpenJDK 11.0.32, Docker 27.1.1, GNU Make 4.3, gh 2.102). I followed only README → START_HERE → CONTRIBUTING → DEVELOPMENT, and I read AGENTS, ISSUE_WORKFLOW, USER_FEEDBACK_ISSUES, TODO, TARGET_ARCHITECTURE, the ADR index, ADR 0007/0008, DEPLOYMENT, deploy/README, the issue template, `ci-cd.yml` and the `main` ruleset. I also ran a relative-link and anchor checker over the 53 active Markdown files, excluding archive and generated files. The audit used no production or shared stores, no paid calls and no development stores.

## Fresh-checkout walkthrough (measured)

| Step | Result |
|---|---|
| `make setup` | pass, 1 m 05 s |
| `make check` | pass, 1 m 58 s: Ruff clean, 1232 backend tests, ESLint 0 errors / 5 warnings, vue-tsc, 390 Vitest, API drift. **First run downloaded `openapi-generator-cli` 7.20.0.jar (31 MB)** and needs Java |
| targeted tests | `pytest tests/test_search_service.py -k access` 9 passed in 0.05 s; `npx vitest run test/unit/routes.spec.ts` 17 passed |
| `make test-integration` | pass, 337 tests, 3 m 41 s (throwaway Weaviate) |
| `make test-e2e` | pass, 98 tests, 4 m 12 s (fakes, throwaway store) |
| `make dev-*` | not run (one instance per machine; not needed to verify the docs) |

All of these work offline with fakes, except `make setup` and the first `make check`, which need network. Only real embedding or LLM evaluation, snapshot work and deployment need service access. They are documented as optional and authorization-gated. **Linux works as documented.** The docs say nothing about macOS/WSL/Windows, and I have no evidence either way (the scripts are bash plus Docker). I recommend stating "Linux tested; others untested" only if someone tries them.

## Findings

| # | Sev | Finding and evidence | Impact | Smallest fix | Tracking |
|---|---|---|---|---|---|
| F1 | **P1** | **Students cannot complete a PR from a fork, and no document says so.** Every CI job has `if: … head.repo.full_name == github.repository`, and the `main-protection` ruleset requires *Backend tests, Frontend checks, Generated API client drift, Integration tests, Python dependency locks*. A fork PR therefore never gets its required checks. CONTRIBUTING and START_HERE never mention write access or forks | First-contribution blocker for anyone without push rights | One paragraph in CONTRIBUTING §6: ask for write access, link #393 | **Fixed in #443**; CI side in #393 |
| F2 | P2 | **Stale embedding model.** README tech stack and tree, ARCHITECTURE §1, DATABASE `Chunks`, VISION and DEPLOYMENT §3 presented `BAAI/bge-multilingual-gemma2` as current. DEVELOPMENT §6 tunnelled to the retired Gemma port 8001. Actual state: deployed Qwen3-Embedding-0.6B on vLLM via `search_vectors_qwen.yaml`, with `default` and `Gemma` dropped ([audit 2026-10-17](../WEAVIATE_AUDIT_2026-10-17.md)). The repository **default** `configs/search_vectors.yaml` still targets the Gemma service | Wrong mental model, and a non-working real-search recipe | Wording | **Fixed in #443.** Whether to change the default config or retire `embedding_service/` and `adapters/embeddings/gemma.py` is a code decision → #413 |
| F3 | P2 | **Java and network are required by `make check`, contrary to the docs.** START_HERE says "Java 11+ is needed only when regenerating", and START_HERE and README say `make check` "runs offline". `make check` includes `api-check`, which generates (`scripts/api-client.sh` fails without `java`). The first run downloads the jar | A newcomer without Java hits an unexplained failure, and an offline first run fails | Wording now. Optionally prefetch the jar in `make setup` (tooling) | **Docs fixed in #443**; prefetch → #413 |
| F4 | P2 | **No targeted test commands are documented anywhere.** No pytest-file, `-k` or `vitest run <file>` example exists in any active doc. Only the full `make check` and the e2e-dev loop are documented | Agents and students rerun the 2-minute full suite on each edit | Three-line block in CONTRIBUTING §4 | **Fixed in #443** |
| F5 | P2 | **Review request and 24 h target live only in ISSUE_WORKFLOW.** CONTRIBUTING §6 (the PR procedure) said only "obtain the required human review". AGENTS says "request review" without saying how. Ruleset facts not documented: strict up-to-date branch. The ruleset also requires code-owner review, but there is no `CODEOWNERS`, so that rule is inert | PRs opened without anyone being asked to review; surprise "branch out of date" blocks | Add to CONTRIBUTING §6 | **Fixed in #443** (CODEOWNERS: see decisions) |
| F6 | P2 | **AGENTS.md restates rules found elsewhere.** About 1,240 words, loaded into every session. *Architecture* and *Behavior to preserve* restate CONTRIBUTING §3/§5, TARGET_ARCHITECTURE and ADR Q1–Q5 in different words ("document/chunk membership" vs "collection membership" vs "collection membership or owner-only settings"; consistent with ADR 0007 today, but a drift risk). It contains a ~200-word `gh --attach` recipe used only for UI PRs. *Before editing* asks agents to read all of ARCHITECTURE.md (~10,000 words) for every change | Context cost on every agent run; three copies to keep in sync | Keep only agent-specific rules in AGENTS and link the rest | **New #442** |
| F7 | P3 | **No PR template.** PR contents are listed in three places (CONTRIBUTING §6, ISSUE_WORKFLOW handoff, AGENTS handoff), each slightly different | Inconsistent handoffs | `.github/pull_request_template.md` | **#442** |
| F8 | P3 | **Stale ADR status.** ADR 0008 and the ADR index said the migration of deployed stores was pending. #327 records production and the test store migrated on 2026-10-18 | Agents may believe a migration is outstanding | Status line | **Fixed in #443** |
| F9 | P3 | **Run-the-app block appears in five places** (README, START_HERE, CONTRIBUTING twice, DEVELOPMENT, AGENTS). All copies are consistent today | Drift risk only | Keep DEVELOPMENT §1 as the full copy, pointers elsewhere | #442 |
| F10 | P3 | **CONTRIBUTING §2 puts a ~250-word lock-maintenance paragraph in the newcomer's setup path** | Slows the essential path; content is correct | Move under a "Dependency locks" subheading | optional, #442 |
| F11 | P3 | README documentation map omitted ISSUE_WORKFLOW.md | Process doc reachable only via START_HERE and CONTRIBUTING | Add a row | **Fixed in #443** |
| F12 | P3 | Passing Vitest runs print an `ApiError … HTTP 429` stack trace (`spanDiscussion.spec.ts`) | Noisy output that looks like a failure to a newcomer or agent | Silence the expected console error in the test | #413 (tooling) |

**Checked, no issue found:**
- **Links and anchors:** zero broken in active docs.
- **Commands:** every documented `make` target exists, and `make dev` is correctly documented as absent.
- **Supported runtimes:** consistent (Python 3.12, Node 22 `.nvmrc`, Weaviate 1.40.1).
- **CI vs docs:** required checks match. E2E is not in CI, as stated (#212).
- **Generated-client rules:** consistent across README, START_HERE, CONTRIBUTING and AGENTS.
- **Data and environment safety:** clear, prominent and consistent (DEVELOPMENT §2/§7, CONTRIBUTING §5, AGENTS).
- **Issue readiness:** ISSUE_WORKFLOW distinguishes `[User draft]` / `[Draft]` / ready clearly, with required sections, a readiness checklist and consultation triggers. USER_FEEDBACK_ISSUES is non-technical, as intended.
- **Screenshot expectations:** clear and proportionate (UI checklist and template).
- **Historical material:** marked as such and kept under `docs/archive/`.
- **Agent rules:** discoverable. AGENTS.md was auto-loaded by this agent session, and no instruction lives only in a private prompt.

## Representative navigation tasks

| Task | Docs needed | Detours / duplication |
|---|---|---|
| Get a green baseline | START_HERE → `make setup`, `make check` | Java not listed (F3) |
| Run one test while iterating | none answered it | F4 |
| Change an API schema | CONTRIBUTING §1 + §3 | Fine (two places, one doc) |
| Decide which tests a change needs | CONTRIBUTING §4 table → ADR 0005 | Good progressive disclosure |
| Is this issue ready? | ISSUE_WORKFLOW | Good |
| Open a PR and get it reviewed | CONTRIBUTING §6 **and** ISSUE_WORKFLOW handoff **and** AGENTS handoff | F1, F5, F7 |
| Agent: may a shared user remove a document? | AGENTS, CONTRIBUTING §3, TARGET_ARCH, ADR README Q1, ADR 0007 | Five statements of one rule (F6) |
| Real vector search on a snapshot | DEVELOPMENT §6 | Was wrong (F2) |

## Canonical entrypoints (recommended; mostly already the case)

- **Human:** README → START_HERE → CONTRIBUTING.
- **Process:** ISSUE_WORKFLOW for issues; CONTRIBUTING §6 for PRs.
- **Environment:** DEVELOPMENT.
- **Current implementation:** ARCHITECTURE. Decisions: ADRs.
- **Open risks:** TODO, which indexes issues and is not a tracker.
- **Agents:** AGENTS.md as agent-specific deltas plus links (#442).

Owners: whoever changes a behavior updates the doc that TODO.md's documentation policy assigns to it. That policy already exists and is adequate.

## Before onboarding students vs optional

- **Needed before onboarding:** F1 (route for write access), F3 (Java), F4 (targeted tests), F5 (review request). All are in #443, pending confirmation of the write-access decision below.
- **Recommended soon:** #442 (F6, F7, F9) for agent context efficiency.
- **Optional:** F10, F12, prefetching the generator jar, and a WSL/macOS note once someone has tried them.

## Decisions for maintainers

1. Are students given write access, as #443 now states, until #393 lands?
2. Should the ruleset's code-owner requirement get a `CODEOWNERS` file, or be dropped? It is inert today. Also, two bypass actors merge without review: 8 of the last 15 merged PRs had zero reviews. That is fine for maintainers, but CONTRIBUTING describes review as always required.
3. Should the default `search_vectors.yaml` keep targeting the retired Gemma service (#413)?
