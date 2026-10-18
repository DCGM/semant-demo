# Issue workflow: from draft to implementation

GitHub issues hold the requirements for semANT implementation work. This guide defines
how an idea becomes an implementable task. For coding, testing, branches, PRs and
merging, follow [CONTRIBUTING.md](../CONTRIBUTING.md); agents must also follow
[AGENTS.md](../AGENTS.md).

**An implementation-ready issue defines a verifiable outcome and any decisions
needed to achieve it.** It need not prescribe every coding step. It *may* prescribe
a specific technical approach when that is an agreed requirement or architectural
constraint.

## Lifecycle

1. **[Draft]** — Capture an idea, problem or request, even if incomplete.
2. **Implementation proposal** — The developer and AI agent investigate the
   repository, refine requirements, identify decisions and propose a suitably
   scoped task. **Normally update the original issue**, preserving its discussion
   history; do not create a replacement issue just for refinement.
3. **Consultation (if needed)** — Ask a maintainer to resolve significant product,
   architectural or operational questions; record decisions in the issue.
4. **Ready → work** — Once the [readiness checklist](#readiness-checklist) is met,
   remove the `[Draft]` prefix. The developer takes ownership and implements the
   agreed scope. **Readiness is the developer's responsibility**, not a mandatory
   administrator approval step.
5. **PR → review → merge** — Open a focused PR, request human review, address
   feedback and merge after required checks and approval. Close the issue when
   its acceptance criteria are satisfied; track remaining work separately.

A proposal can return to draft/refinement if implementation reveals a material
missing requirement. Being ready does not imply scheduling or prioritization.

## Draft issues

Use the title prefix `[Draft]`. Only **the problem or goal** and **enough context
to understand it** are required. Add examples, user scenarios, screenshots, initial
ideas, related work and open questions when available.

Drafts may be short and speculative. Distinguish suggestions from decisions.
A draft is not an approved design or an implementation commitment. It may remain
open as a longer-term parent issue.

Prefer searching for an existing related issue before opening a new one; a quick
capture of a new idea should not be blocked by extensive investigation.

## Implementation-ready issue content

Write proportionately: a small bug fix can be brief, while a cross-feature
change may need a detailed contract. The issue should let another developer
implement and verify the requested result without guessing important decisions.

1. **Goal and motivation (required).** State what changes and why. For a bug,
   show actual versus expected behavior and reproduction evidence when available.
2. **Functional requirements (required).** Describe observable behavior,
   workflows, inputs and outputs, plus relevant empty, error, partial-result or
   permission states. Include examples where useful. State an approved technical
   design when it is part of the requirement; otherwise link the relevant
   existing contract and leave routine implementation choices to the developer.
3. **Scope and non-goals (required).** Define what this issue includes and
   deliberately excludes, particularly attractive adjacent work.
4. **Acceptance criteria (required).** Use a concise checkbox list of testable
   outcomes, including important boundaries and regressions. Describe *what
   must be true*, not a checklist of coding activities.
5. **Technical context and constraints (when relevant).** Link affected
   components, established interfaces, ADRs, data formats, dependencies and
   approved design decisions. Specify migration, compatibility, authorization,
   performance or operational constraints if they matter.
6. **Verification (required).** Name the specific evidence needed (for example,
   a bug regression test, isolated-store integration test, browser interaction,
   UI states or a performance baseline). Apply the existing
   [testing contract](../CONTRIBUTING.md#4-testing-contract); do not restate
   generic commands and quality rules.
7. **Relationships (when relevant).** Link the parent, blocking prerequisites,
   related issues and relevant PRs. Separate blockers from background context.
8. **Open decisions (when relevant).** State outstanding questions and who can
   decide them. Material decisions must be resolved before the issue is ready.

### Readiness checklist

- [ ] Goal, expected behavior and acceptance criteria are clear and verifiable.
- [ ] Scope and non-goals are defined.
- [ ] Relevant existing work, code, architecture and repository rules were checked.
- [ ] Important constraints and dependencies are linked or stated.
- [ ] Necessary product/architecture decisions are resolved.
- [ ] Verification is feasible and the work is independently reviewable (or split
      into appropriately scoped subissues).

Minor coding choices may remain open; significant uncertainty about behavior,
scope or architecture may not.

## AI-assisted issue preparation

The developer is expected to use an AI agent for technical investigation before
marking an issue ready. Ask the agent to:

- Search related **open and closed issues, PRs and planned work**; identify
  duplicates, overlaps, dependencies and conflicting requirements.
- Read `AGENTS.md`, `CONTRIBUTING.md`, relevant
  [architecture](ARCHITECTURE.md), [ADRs](adr/README.md) and
  [TODO index](TODO.md). Inspect affected code, callers, interfaces and tests;
  distinguish implemented behavior from proposed behavior.
- Check fit with existing architecture, shared contracts and access rules, plus
  implications for API/schema compatibility, data, security, failure behavior,
  performance, costs, deployment and tests **where applicable**.
- Suggest scope, acceptance criteria, verification and useful subissues. Flag
  decisions needing consultation rather than silently making them.
- Summarize findings **concisely in the issue**, linking evidence and separating
  verified facts, assumptions and proposals. State any areas the agent could
  not verify.

The developer checks that the result matches the intended user need and reviews
significant conclusions. AI-generated prose is not evidence of correctness.
The agent must not treat older plans as current requirements or revise settled
contracts without raising the conflict.

## Parent issues and subissues

Use a parent issue for a larger initiative: overall outcome, boundaries, common
contracts, major design decisions, linked subissues and integration criteria.
Create implementation subissues when there are distinct, reviewable deliverables,
ownership boundaries or dependencies. **Do not split tasks mechanically by
frontend/backend/database layers** if a vertical slice is simpler.

Each implementation subissue has its own scope, acceptance criteria and blockers;
refer to the parent instead of copying the full specification. Prefer short,
focused tasks that can yield a reviewable PR promptly. A parent closes only
when its overall integration/acceptance criteria are met. A `[Draft]` may stay
open as the parent while ready subissues proceed.

## When to consult maintainers

**No approval gate for routine issues.** A developer may proceed when
requirements are clear, the change follows existing decisions and contracts,
and risks are covered by normal review.

Consult a maintainer (normally Michal or Martin) **before implementing a
significant unresolved decision**, for example:

- New or ambiguous product behavior, workflows or feature priorities.
- Architectural changes, cross-feature contracts or conflicting planned work.
- Data models/migrations, destructive operations, access control or security.
- Deployment/shared infrastructure, external integrations or material ongoing cost.
- A substantial expansion of the agreed issue scope.

Bring the specific question, plausible options, trade-offs and a recommendation
when possible. Record the answer in the issue and update requirements. If it
changes an architectural decision, follow the repository's ADR/documentation
review process.

## Implementation and PR handoff

1. Check ownership, blockers and current `main`, then assign yourself or comment
   before starting work. Follow the branch and development rules in
   [CONTRIBUTING.md](../CONTRIBUTING.md).
2. Aim for a **reviewable PR within approximately 24 hours** of starting
   implementation. For larger features, use smaller slices rather than a long
   unreviewed branch. A draft PR can expose blocked or incomplete work, but is
   not a request to merge it.
3. If work exposes a material gap, document it in the issue, consult when
   needed and update the agreed scope. Do not silently extend the task.
4. Link the issue in the PR. Describe changes, actual checks/results, relevant
   UI evidence, important decisions, risks and incomplete work. Use
   `Closes #123` only when the PR completes that issue.
5. **Explicitly request review** from an appropriate maintainer; opening a PR
   alone is not the review request. Apply corrections in the same PR and merge
   only with required human review and passing checks. Update parent progress,
   follow-up issues and active documentation when applicable.

Keep the process lightweight: avoid repeated documentation, speculative
requirements and subissues for trivial steps. The objective is a correct,
reviewable implementation, not a long specification.
