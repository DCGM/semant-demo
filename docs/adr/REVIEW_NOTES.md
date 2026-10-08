# Repository re-review against the agreed plan

> **Historical snapshot (2026-10-07).** These observations predate the completed
> #197 refactor and must not be presented as current defects. Use
> [ARCHITECTURE.md](../ARCHITECTURE.md), [TODO.md](../TODO.md) and open GitHub issues
> for current behavior. The full #197 delivery log is
> [archived](../archive/refactor-2026/REFACTOR_STATUS.md).

Date: 2026-10-07.
Baseline: `main` commit `375caa5f7f68defba25a56cccbb7dbc7fdf99a13`.
Documentation updated after Q1-Q5 clarification on 2026-10-07. This corrects product
interpretation; it is not a new repository/deployment audit.

## Scope and confidence

Static inspection through the connected GitHub reader: current commit/PR metadata,
relevant backend routes, repositories, schemas, startup/configuration, CI, tests,
frontend annotation/AI state, dependency manifests, and existing documentation.
The reviewed PR heads match the heads inspected in the earlier review; that earlier
diff review remains applicable to those exact commits. The actual deployment, external
Topicer implementation, source-page datasets, and every application file were not audited.

A local clone attempt failed because the execution container could not resolve GitHub.
No application tests, live Weaviate calls, browser flows, migrations, performance tests,
or API generation were executed. PR test checklists are author reports, not reproduced
results. The documentation package itself was checked separately for structure and links.
Source links below are pinned so findings are not silently changed by later commits.

## What changed or should not be reopened

Current main added iterative collection listing in [the reviewed commit][S0]. The initial
review's specific unpaginated-listing finding is therefore outdated. Offset/query-limit
and direct-authorization concerns remain separate questions, not proof that pagination
is still missing.

Sharing and span discussion already have implementations. Preserve and improve them;
do not treat the whole roadmap as entirely new functionality. [S1], [S8], [S9]

The frontend already has a lockfile, generated clients, API wrappers, and a generator
version pinned to 7.20.0. Preserve those foundations; the gap is deterministic verification
and consistent usage, not the total absence of dependency management. [S10], [S11]

Keep the decisions from discussion: optional interfaces/classes, concrete repositories
only in adapters, service-level access, best-effort writes without repair infrastructure,
Weaviate-resident search metadata, and request-scoped AI with saved proposals.

## Findings

| ID | Finding and evidence | Implication / required action |
| --- | --- | --- |
| F1 | Current collection update/delete still lack principal dependencies; chunk add/remove authenticate then discard `current_user`; member listing does not pass a principal to its repository. [S1] | Authentication is not a resource policy. Complete the service-level access audit and test unrelated users and mixed scopes. |
| F2 | `add_chunk_to_collection` uses `f"Error: {e}"` when its helper returns false, but `e` is not defined there. [S1] | That failure branch can raise a NameError instead of the intended HTTP error. Fix with a regression test and static checking. |
| F3 | Search uses chunk `positiveTag`/`automaticTag` references; span create/update operate on Span records without updating those references in the inspected paths. [S2], [S3] | Likely annotation/search inconsistency. Q2 confirms chunk-based search stays; fix attribute maintenance and audit unsupported entries separately, not a new query design. Prove changed paths on real Weaviate; no deployed reproduction was performed. |
| F4 | AI persistence errors return `None`, indistinguishable from invalid/no proposals to callers; span bulk update skips failures and returns successes only. [S3], [S4] | Does not satisfy the agreed 'user knows about partial failure' rule. Introduce typed item/step outcomes and stream error/completion events. |
| F5 | Span bulk deletion repeatedly reads the first page and catches per-item failures without a no-progress guard. [S3] | A full persistently failing page can be retried indefinitely; smaller failures can be omitted from the returned count. Test termination and failure reporting. |
| F6 | `useAiAssistance.ts` has module-global run/controller state. `tagSpansStore.ts` keys collection-specific results only by chunk ID. [S5], [S6] | Context collisions and late-response contamination are plausible when switching shared documents/collections. Confirm with a navigation test; partition state and guard by context/run token. |
| F7 | Frontend offset math uses string `.length`; AI paths use Python `len` and slicing. [S4], [S7] JavaScript length counts UTF-16 code units, while Python strings are code-point sequences. [E1], [E2] | A cross-language coordinate mismatch is possible for non-BMP characters. It is a static risk, not a claim that every existing span is wrong. Characterize and version/migrate deliberately. |
| F8 | Two Document models differ, including scalar/list author and part-number types. NER data in the inspected schema is lists of strings. [S12], [S13] | Consolidate intentional projections. Q5 allows frontend ALTO matching and optional future polygons; no backend alignment service or mandatory stored geometry is implied. |
| F9 | Span writes attempt schema-property creation during requests, swallow errors, then mark the check complete. [S3] | Move schema changes to an explicit reviewed setup/migration step. A flag is not proof migration succeeded. |
| F10 | Backend CI has `continue-on-error`; frontend checks are commented out; production deployment uses `always()`. `npm test` is a no-op success. [S10], [S14] | Tests are not a reliable release gate. Change CI conditions and add real frontend checks. Repository branch-protection settings were not inspected. |
| F11 | Auth tests use users created by earlier tests, module-scoped mutable state, global config mutation, and import reloads. [S15] | Test ordering/isolation problems; test each case alone with independent fixtures and application resources. |
| F12 | Config hard-codes the relative SQL URL and assigns Topicer values twice. Dependencies live in async-lazily-initialized globals; cleanup does not reset them. [S16], [S17] | Configuration precedence, separate app instances, and offline tests are hard to reason about. Introduce explicit settings and lifespan ownership. |
| F13 | Startup uses `TasksBase.metadata` for users too. The schema reset script unconditionally drops collections. [S18], [S19] | Removing old jobs must not remove user data or run destructive resets as migrations. Tests require positive isolation checks. |
| F14 | Backend dependencies are mostly unpinned; pytest configuration has no custom suite markers. [S20], [S21] | Lock backend/tooling and define offline/integration/live selections. Do not misreport frontend as entirely unlocked. |
| F15 | Existing architecture text describes task workflows and makes strong lifecycle claims not established by its global dependency implementation. Old TagSpans benchmarks compare different layouts/endpoints. [S17], [S22], [S23] | Keep current architecture separate from target; mark historical advice and benchmark context. Do not convert old numbers into release thresholds. |
| F16 | The PR stack still mandates generic CRUD and contains unsupported Document operations. #187's source branch predates current sharing and newer chunk routes. [P1], [P2], [P3] | Revise the abstraction and preserve newer main behavior during stack integration; a clean merge alone is not sufficient validation. |

These findings do not justify adding an event bus, SQL migration, durable jobs, or a
repair subsystem. They justify explicit contracts and focused tests.

## Clarified product decisions and remaining implementation work

[Q1-Q5 are confirmed](README.md#confirmed-decisions), not open refactor blockers:
shared users edit annotations but not membership; search uses chunk tag attributes;
search chat uses retrieved results or a selected subset; local real-time means streamed
AI annotations displayed in Document view; line-level alignment is planned and may use
frontend chunk-to-ALTO matching with optional polygon storage later.

The earlier historical-whole-chunk compatibility suggestion was incorrect. Chunk tags
without backing annotations are database inconsistencies to remove in a reviewed cleanup.
Preserve search representation and verify its normal maintenance, rather than introducing
a second search model. Document view, export, and concordances select manual, automatic,
or both annotations; this is not an approved-only policy.

During later export/visualization work, define the output/counting unit (span, chunk,
document, or entity), format, and cross-chunk behavior. Preserve IDs, text coordinates,
and category information. Counts must not conflate spans and tagged chunks. These details,
selector field mapping, and Q6 chat history do not block structural refactoring.

Validate coordinate compatibility and alignment algorithms with fixtures. Polygons, when
added, must retain page/coordinate/source meaning and remain optional; no exact ALTO data
was verified in this review. No assumption is made that every corpus source is public or
approved for every external AI provider.

## Pinned repository sources

[S0]: https://github.com/DCGM/semant-demo/commit/375caa5f7f68defba25a56cccbb7dbc7fdf99a13
[S1]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/user_collection_routes.py
[S2]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/weaviate_utils/text_chunk.py
[S3]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/weaviate_utils/span.py
[S4]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/ai_assistance_routes.py
[S5]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/src/composables/useAiAssistance.ts
[S6]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/src/stores/tagSpansStore.ts
[S7]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/src/composables/useAnnotations.ts
[S8]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/src/composables/useSpanDiscussion.ts
[S9]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/span_chat_routes.py
[S10]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/package.json
[S11]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/openapitools.json
[S12]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/schemas.py
[S13]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/schema/documents.py
[S14]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/.github/workflows/ci-cd.yml
[S15]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/tests/test_auth/test_auth_routes.py
[S16]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/config.py
[S17]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/dependencies.py
[S18]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/main.py
[S19]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/weaviate_utils/build_db/create_schema.py
[S20]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/requirements.txt
[S21]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/pyproject.toml
[S22]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/docs/ARCHITECTURE.md
[S23]: https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/docs/TagSpans_benchmark.md
[P1]: https://github.com/DCGM/semant-demo/pull/182
[P2]: https://github.com/DCGM/semant-demo/pull/184
[P3]: https://github.com/DCGM/semant-demo/pull/187
[E1]: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/length
[E2]: https://docs.python.org/3/library/stdtypes.html#text-sequence-type-str
