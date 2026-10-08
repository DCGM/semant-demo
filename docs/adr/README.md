# Architecture decisions

These records capture agreed behavior and constraints for the current application.
The core decisions are implemented; future proposals are clearly identified.
Current code is described in [ARCHITECTURE.md](../ARCHITECTURE.md), ongoing
work in [TODO.md](../TODO.md), and historical design evidence in the
[archive](../archive/refactor-2026/README.md).

| Record | Status |
| --- | --- |
| [0001 - Simple feature monolith](0001-simple-feature-monolith.md) | Implemented architecture; classes/interfaces optional. |
| [0002 - Best-effort writes](0002-best-effort-writes.md) | Implemented partial-outcome principle; further envelope details are optional refinements. |
| [0003 - Request-scoped AI](0003-request-scoped-ai.md) | Agreed lifecycle; detailed events/retry policy proposed. |
| [0004 - Storage and annotation search](0004-storage-and-annotation-search.md) | Implemented chunk-tag search; inconsistent entries need reviewed cleanup. |
| [0005 - Testing contract](0005-testing-contract.md) | Implemented baseline; detailed test guidance supporting CONTRIBUTING. |
| [0006 - Context and text](0006-context-and-text.md) | Search context/line-level roadmap agreed; mapping implementation left open. |
| [0007 - Access and collaboration](0007-access-and-collaboration.md) | Implemented shared annotation editing, owner-only membership and local progressive UI. |
| [Review notes](REVIEW_NOTES.md) | **Historical** pre-refactor findings and pinned code evidence (not a current defects list). |

## Confirmed decisions

| ID | Decision | Continuing contract |
| --- | --- | --- |
| Q1 | Shared users may edit annotations, not collection membership. | Separate annotation and membership checks and denial tests. |
| Q2 | Search uses chunk tag attributes. Unsupported entries without backing annotations are inconsistencies to remove. Document view/export/concordances select manual, automatic, or both. | Preserve search representation; fix consistency defects and review cleanup separately. Do not impose approved-only search defaults or a legacy compatibility layer. |
| Q3 | Search chat uses retrieved results or an explicitly selected subset. | Explicit source set; no silent query rerun or scope expansion. |
| Q4 | Real-time means local Document-view annotation, including immediate streamed AI suggestions. | Scope-safe UI updates; no cross-user synchronization requirement. |
| Q5 | Line-level text-image correspondence is planned, possibly by frontend chunk-to-ALTO mapping; polygons may be added later. | Preserve text/source anchors; geometry stays optional and mapping is future feature work. |

These answers supersede the initial Q1–Q5 proposals. Changes to agreed behavior
require an explicit issue, review and ADR update; do not silently broaden scope.

## Deferred implementation decisions

Q6 (persistent/shared chat history) remains future work; preserve current request-scoped
behavior until deliberately changed. Alignment placement, matching algorithm, optional polygon schema, export
formats, and annotation-selector field mappings belong to their feature changes, not
unrelated feature changes. Do not invent extra stored fields merely to anticipate them.

Before adding generation retries, define duplicate handling and preserve human-reviewed
work. Validate external provider data permissions when enabling new integrations. These
are implementation safeguards, not requests to reopen agreed lifecycle or storage choices.

Testing/tool choices (pytest, Vitest/Vue Test Utils, Playwright, blocking deterministic CI)
are now implemented in the development toolchain. See [CONTRIBUTING](../../CONTRIBUTING.md)
and [#212](https://github.com/DCGM/semant-demo/issues/212) for the remaining browser CI decision.

## Updating decisions

Record date, status, context, decision, consequences, and verification. Mark changes to
proposals explicitly; retain a short note of what they supersede. Add an owner on adoption.
Do not list placeholder people as approved reviewers or mark future work implemented.
