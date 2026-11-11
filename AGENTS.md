# Agent instructions

[CONTRIBUTING.md](CONTRIBUTING.md) is the shared development contract. Read it for the
task, then follow only the linked procedures and architecture sections relevant to the
change; do not load every guide or repeat their rules here.

## Before implementation

- Understand the issue, affected code, callers and tests. Follow the
  [issue workflow](docs/ISSUE_WORKFLOW.md#ai-assisted-issue-preparation); refine the existing
  issue rather than replace it. For `[User draft]` reports, use the
  [feedback guide](docs/USER_FEEDBACK_ISSUES.md) and preserve the reporter's use case.
- Resolve material ambiguity or conflicts with confirmed product/architecture decisions
  with a maintainer before implementing. Read the architecture module map and affected
  feature sections, not the whole document.
- Branch from the latest `origin/main`, not an unmerged topic branch, unless stacking was
  explicitly requested. Keep the change focused.

## Authorization and safety

You may create and push a topic branch and open its PR. Without explicit authorization
for this task, do not push to `main`, force-update protected branches, merge or deploy;
access shared/production databases or production endpoints; use real user text,
`local_data/` snapshots, paid model calls, GPU/model downloads or live evaluations; or
run data cleanup. Never bypass protected-branch rules.

Before any destructive command, verify the intended local endpoint and data ownership;
"test" in a name is not proof of safety. Do not reset data the user is working with
without asking. Report unavailable access or tooling instead of bypassing safeguards.

## Work and verification

- Use the repository `.venv`; do not create another environment unless required. Reuse the
  [seeded local application](docs/DEVELOPMENT.md#1-quick-start-the-seeded-local-application),
  not a separate agent environment. Check `make dev-status` first: it is machine-wide.
  Run servers in the background and stop those you started when done. Keep its fake AI
  providers; automated tests use separate disposable stores.
- Select checks using [the testing contract](CONTRIBUTING.md#4-testing-contract).
  Use targeted tests while iterating and the fast browser loop for UI work. Never weaken
  assertions, add blanket skips, bypass CI, hand-edit generated clients or claim unrun
  checks passed. A placeholder test command is not verification.
- For meaningful UI changes, follow the
  [UI checklist and upload procedure](docs/UI_GUIDELINES.md#ui-change-checklist)
  before the first push/review; use only synthetic/fixture evidence you actually captured.

## Handoff and self-reflection

Fill in the [PR template](.github/pull_request_template.md), update relevant active docs
and explicitly request review. Report checks actually run, unavailable checks and why,
blockers, remaining risks and decisions.

Before handoff, consider what caused avoidable investigation, retries, tool calls or
context/token use. Complete [Development friction](CONTRIBUTING.md#development-friction),
including resolved hurdles; check existing guidance before proposing new instructions.
Report actionable observations, not a session transcript or private reasoning trace.
