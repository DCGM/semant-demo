# ADR 0005 - Behavior-based, offline-first testing

Status: adopted and implemented in #199–#200 and CONTRIBUTING; adding browser smoke to CI is tracked in #212.
Updated: 2026-10-07. Detailed guidance moved here from CONTRIBUTING to keep the everyday
guide short. Confirmed product rules are reflected in the cases below.

## Purpose and tools

The pinned review found order-dependent auth tests, placeholder frontend tests, and
non-blocking CI. See [review evidence](REVIEW_NOTES.md). Manual checks complement, but
do not replace, repeatable regression tests.

[CONTRIBUTING.md](../../CONTRIBUTING.md#4-testing-contract) is the concise policy and
per-change test matrix. This ADR contains implementation guidance and the detailed
regression inventory; AGENTS links to it rather than creating a separate test policy.

Keep pytest/pytest-asyncio/HTTPX and existing unittest cases. Use deterministic injected
providers for fast service/API tests and real isolated Weaviate for storage semantics.
Add Vitest + Vue Test Utils for frontend logic/components and a small Playwright suite.
Use the toolchain and pinned dependency versions documented in CONTRIBUTING. No mass
conversion of existing unittest tests and no GPU/paid-provider requirement for ordinary PRs.

## Isolation and test data

Every test must pass alone and in any order. Create required users, collections, and
annotations in fixtures, not earlier tests. Prefer function-scoped mutable state; shared
read-only fixtures are fine. Construct fresh application instances and dependency
overrides instead of mutating globals and reloading modules.

Each automated integration run owns its mutable test data namespace; add worker suffixes when parallel. Fixture cleanup must positively verify test ownership before deleting anything. Never use production or shared preview databases for automated tests.

Developers may use the local realistic database snapshot under local_data/, as described in DEVELOPMENT.md, for manual development, exploratory testing, and compatibility checks. This snapshot is not the canonical automated integration-test fixture: automated tests must create or reset the data they depend on and must not assume that particular collections, users, or annotations already exist in the snapshot.

Use fixed vectors rather than a live embedding service where embedding behavior itself is not under test. Browser context isolation does not isolate shared backend data.

Fakes implement only the capabilities needed by the use case, not the entire SDK. Where
fake and real adapters share an interface, reuse applicable behavioral contract tests.
A Protocol can help but is not a prerequisite for injecting a fake. Mocking SDK calls
alone does not prove Weaviate filters, pagination, references, or search consistency.

Maintain a small synthetic fixture corpus: an owner, shared annotator, unrelated user,
and admin; two collections sharing a document; partial chunk membership; multiple tags;
manual/automatic annotations and existing approval/rejection states; overlapping and
cross-chunk spans; missing/null metadata; Czech diacritics, combining marks, and non-BMP
characters; and a document exceeding a pagination page. Keep stable fixture IDs where
useful. Share text/offset examples between Python and TypeScript.

No production/user text belongs in fixtures without explicit authorization. Do not
convert acknowledged defects into golden expectations; label characterization tests
with the defect and the intended replacement behavior.

## Suite selection and offline execution

Backend pytest markers are configured in `semant_demo_backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "--strict-markers"
markers = [
  "integration: requires isolated local infrastructure",
  "live: explicitly authorized external provider test",
  "benchmark: controlled performance measurement",
]
```

This configuration is in use. Fast checks exclude all three
categories and deny outbound network. A marker alone is not network isolation. Avoid
provider/resource initialization during import and test collection; unmarked tests must
be offline, with no real API keys or model downloads.

Live tests additionally require explicit opt-in and a cost limit. They and benchmarks
are not ordinary PR gates. Required integration jobs fail on missing infrastructure or
an unexpectedly empty/skipped selection; they do not silently turn into a pass.
Documentation-only changes need link/format checks, not these application suites.

## Async and streaming tests

Use lifespan management when startup/shutdown is relevant: HTTPX ASGI transport does
not start application lifespan itself. Create resources in the correct event loop and
clean up overrides, sessions, clients, and tasks after every test.

Use events/barriers and bounded waits rather than arbitrary sleeps. In-process transports
may buffer responses, so unit/API tests are not proof of progressive browser updates or
actual disconnect cancellation. Include a real-server/browser scenario for those claims.
Test cancellation while work is active, not only before the first result.

Saved-result events follow acknowledged writes. Disconnect retains completed writes;
an interrupted response may leave a write outcome uncertain. Tests must not assume an
upstream call or in-flight write is magically undone by cancellation.

## Regression inventory (historical baseline)

These cases informed #197 and remain useful regression guidance when related behavior
changes. Do not require all layers for every PR or demand features that do not exist yet.

| Area | Cases to prove |
| --- | --- |
| Access | Owner/shared/unrelated/anonymous; shared annotation edits allowed but document/chunk membership changes denied; explicit admin actions; guessed IDs; mixed-scope batches; revocation; no unauthorized read/write/provider call. |
| Search | Text/vector/hybrid; collection + chunk-tag + metadata filters compose; excluded chunks never become eligible; optional summarization failure retains hits. |
| Annotation/search consistency | Create, status/tag change, and delete maintain the existing chunk-tag representation; removing one of several backing annotations retains the tag; final removal clears it; collection/category/cross-chunk rules remain compatible. |
| Pagination | Empty, exact page, page + 1, multi-page; stable ordering; configured limits; shrinking mutation sets; persistent failure/no-progress terminates. |
| Partial writes | One/all failures, already-completed retry, unattempted steps, uncertain timeout; returned item/step outcomes and counts match acknowledged work. |
| AI streams | Save before saved-result event; provider/persistence failure; explicit terminal event; unexpected EOF is incomplete; cancel retains saved work; saved proposals reload. |
| Document-view state | Progressive automatic annotations display without a reload; switch collection/document during a request; late events cannot alter the new context/loading state; logout clears scope; failed writes are visible. |
| Text | Existing manual/AI offset semantics; Unicode conversion; half-open target convention only with compatibility; cross-chunk spans/gaps; canonical versus display text. |
| Lifecycle | Separate app instances/resources; partial-startup cleanup; connection-free OpenAPI export. |
| API compatibility | Stable operation IDs/wire mappings during moves; generated client matches backend; NDJSON schemas and parsing work across fragmented lines/UTF-8 boundaries. |
| Old job removal | Login/users survive; SQL metadata, callers, and generated clients do not accidentally depend on removed jobs. |

Annotation-query details are compatibility/correctness checks, not a mandate to redesign
search. The one-off inconsistent-data cleanup has separate tests: dry-run report, remove
only unsupported chunk tag entries, retain valid multi-annotation references, and treat
failed reads as errors rather than absence. A real production cleanup is not a test fixture.

A minimal release browser suite exercises login, collection membership, annotation editing,
shared annotation access with membership denial, search, and streamed AI/cancellation.
Keep it small; use the lower-level suites for combinatorial coverage.

## Tests added with later roadmap features

These require focused tests when the corresponding feature is implemented:

| Feature | Targeted coverage |
| --- | --- |
| Search chat | Full retrieved set and explicitly selected subset only; empty/missing/revoked sources; no query-scope expansion or unselected history sources. |
| Document view/export/concordances selectors | Manual, automatic, and both using the application's category mapping; filtering is not replaced with an approved-only rule. |
| ALTO text-image alignment | Line breaks/hyphenation, repeated text, ambiguous/missing matches, Unicode, canonical-offset mapping, cross-page polygons, resize/zoom transforms. |
| Located NER | Distinguish repeated surface strings and missing positions; text-only fallback; use shared location conventions. |
| Collection visualizations/export | Explicit scope, units/counting semantics, annotation-category selection, and cross-chunk behavior. |

Use shared mapping fixtures for browser and backend only where both handle the contract.
Frontend-only ALTO matching does not require a duplicate backend algorithm. No WebSocket
or multi-user live-synchronization tests are required by local real-time annotation UX.

## Assertions, coverage, and flakiness

Assert public results and essential side effects, not incidental internal calls. SDK-call
assertions are useful when query construction itself is under test. Avoid large snapshot-
only tests. Fixed-vector retrieval tests check scope and unambiguous ranking invariants,
not exact scores from a live model; record server/client versions.

Measure baseline coverage, excluding generated/vendor code. Do not impose an arbitrary
repository-wide percentage or let a numeric target excuse untested authorization/mutation
paths. New failures cannot be hidden by blanket ignores. Quarantined/expected failures
need an owner, issue, and removal condition. A passing rerun does not establish a fix.
Report selected, passed, failed, and skipped tests and unavailable checks explicitly.

## Quality evaluation and benchmarks

Use a small versioned query/question set with expected sources/scope, not exact model
wording. Intentional prompt/model/retrieval-quality changes record corpus, model/provider
configuration, relevance/citation observations, and tradeoffs for human review. Structural
moves preserving behavior do not require a new paid quality evaluation.

Measure performance with fixed dataset sizes, versions, configuration, and hardware notes.
Keep noisy timing thresholds out of ordinary unit tests. Historical benchmark results are
not a performance guarantee for the current architecture. Request permission for live
provider runs, production data, or substantial resource use.

## References

- [FastAPI async tests and lifespan](https://fastapi.tiangolo.com/advanced/async-tests/)
- [pytest marker registration](https://docs.pytest.org/en/stable/how-to/mark.html)
- [Vue testing guidance](https://vuejs.org/guide/scaling-up/testing.html)
- [Vue Test Utils](https://test-utils.vuejs.org/guide/essentials/a-crash-course.html)
- [Playwright browser isolation](https://playwright.dev/docs/browser-contexts)
