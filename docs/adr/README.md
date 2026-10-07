# Architecture decisions and review notes

Updated 2026-10-07. This package is a draft for repository adoption, not merged policy.
'Agreed' records the development discussion; implementation proposals are not claims
that code, migrations, or test infrastructure already exist.

| Record | Status |
| --- | --- |
| [0001 - Simple feature monolith](0001-simple-feature-monolith.md) | Agreed direction; classes/interfaces optional. |
| [0002 - Best-effort writes](0002-best-effort-writes.md) | Agreed principle; detailed result envelope proposed. |
| [0003 - Request-scoped AI](0003-request-scoped-ai.md) | Agreed lifecycle; detailed events/retry policy proposed. |
| [0004 - Storage and annotation search](0004-storage-and-annotation-search.md) | Chunk-based search retained; inconsistent entries are cleanup, not legacy features. |
| [0005 - Testing contract](0005-testing-contract.md) | Proposed standard; detailed test guidance supporting CONTRIBUTING. |
| [0006 - Context and text](0006-context-and-text.md) | Search context/line-level roadmap agreed; mapping implementation left open. |
| [0007 - Access and collaboration](0007-access-and-collaboration.md) | Shared annotation editing, no membership editing; local progressive UI. |
| [Review notes](REVIEW_NOTES.md) | Pinned code evidence with corrected product interpretation. |

## Confirmed decisions

| ID | Decision | Refactor consequence |
| --- | --- | --- |
| Q1 | Shared users may edit annotations, not collection membership. | Separate annotation and membership checks and denial tests. |
| Q2 | Search uses chunk tag attributes. Unsupported entries without backing annotations are inconsistencies to remove. Document view/export/concordances select manual, automatic, or both. | Preserve search representation; fix consistency defects and review cleanup separately. Do not impose approved-only search defaults or a legacy compatibility layer. |
| Q3 | Search chat uses retrieved results or an explicitly selected subset. | Explicit source set; no silent query rerun or scope expansion. |
| Q4 | Real-time means local Document-view annotation, including immediate streamed AI suggestions. | Scope-safe UI updates; no cross-user synchronization requirement. |
| Q5 | Line-level text-image correspondence is planned, possibly by frontend chunk-to-ALTO mapping; polygons may be added later. | Preserve text/source anchors; geometry stays optional and mapping is future feature work. |

These answers replace the initial Q1-Q5 proposals. Do not block unrelated refactoring
on additional product choices about search representations, roles, or page-only scope.

## Deferred implementation decisions

Q6 (persistent/shared chat history) remains future work; preserve current behavior during
refactoring. Alignment placement, matching algorithm, optional polygon schema, export
formats, and annotation-selector field mappings belong to their feature changes, not
the structural refactor. Do not invent extra stored fields merely to anticipate them.

Before adding generation retries, define duplicate handling and preserve human-reviewed
work. Validate external provider data permissions when enabling new integrations. These
are implementation safeguards, not requests to reopen agreed lifecycle or storage choices.

Testing/tool choices (pytest, Vitest/Vue Test Utils, Playwright, blocking deterministic CI)
remain proposals for adoption with R0 and must be pinned compatibly.

## Updating decisions

Record date, status, context, decision, consequences, and verification. Mark changes to
proposals explicitly; retain a short note of what they supersede. Add an owner on adoption.
Do not list placeholder people as approved reviewers or mark future work implemented.
