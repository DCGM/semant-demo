# Refactor status

Last updated: 2026-10-08 (#208)

## Current state

- Integration branch: `197-refactor---base`
- Current issue: #208 — Consolidate backend schemas and generated API contracts
  (in review); next: #209.
- Completed refactor issues: #198 (bootstrap and configuration; manually verified
  against local Weaviate), #199 (fast checks and blocking CI, PR #211), #200 (isolated
  real-store and browser test infrastructure, PR #214), #201 (access checks and partial
  write outcomes, PR #216), #202 (adapter foundation, PR #219),
  #203 (Collections feature migration, PR #221), #204 (annotation/chunk tag consistency,
  PR #223), #205 (Search feature service and adapter, PR #225), #206 (Annotations
  feature, PR #226), #207 (request-scoped AI suggestions, PR #228)
- Current stage: R3/R6 contract cleanup (#208)

## Development environment

- Local realistic database snapshot is available under `local_data/`.
- Local Weaviate runs from `local_data/weaviate_semant_test`.
- Local SQLite state is `local_data/tasks.db`.
- Shared server databases are not used for normal refactor development.
- The SQL database is configurable through `SQL_DB_URL` (#198). The
  `semant_demo_backend/tasks.db` symlink still works with the default URL.
- Automated real-store and browser tests use throwaway test-owned Weaviate instances,
  never `local_data/` (#200, see DEVELOPMENT.md section 11).

## #198 outcome

- `Config(environ=...)` reads settings once from an explicit mapping or the process
  environment. The duplicated Topicer block was removed; the values that were already
  effective (`http://topicer:8089`, `openai`, `600.0`) are unchanged. The unused
  `TOPICER_READ_WRITE_TIMEOUT` / `TOPICER_RW_TIMEOUT` setting was removed.
- `semant_demo.main.create_app(config)` builds an app; `semant_demo.main:app` is still the
  production entry point. `bootstrap.AppResources` owns the SQL engine, lazily connected
  Weaviate client, summarizer, and RAG registry for one lifespan and is closed at shutdown,
  also after a failed startup.
- The RAG registry, JWT secret, CORS/static settings, feedback, and summarizer routes now
  use the app's config instead of import-time globals.
- OpenAPI output is byte-identical to the pre-change export.
- Tests: `tests/test_config.py`, `tests/test_app/test_bootstrap.py`; auth tests build their
  own app with `tests/app_support.make_test_config` instead of patching globals and reloading.

## #199 outcome

- Root `Makefile` with `make setup`, `make check`, `make api-generate` (plus `check-backend`,
  `check-frontend`, `api-check`). CONTRIBUTING documents the underlying commands.
- Backend: test tools moved from `requirements.txt` to `requirements-dev.txt`; the full
  development set is pinned in `requirements-dev.lock` (versions taken from the existing
  `.venv`, no upgrades). Ruff 0.14.0 added. pytest registers `integration`/`live`/`benchmark`
  markers with `--strict-markers`; `tests/conftest.py` refuses network connections
  (including loopback) in unmarked tests. `tests/fakes.py` provides `FakeChatAPI`.
- Auth tests use a function-scoped `client` fixture (fresh app and SQLite per test) and
  create their own users; each test passes alone.
- Frontend: `npm test` runs Vitest (real composable and Quasar component tests in
  `test/unit`), `npm run typecheck` runs vue-tsc, Node pinned to 22 (`.nvmrc`, engines).
  TypeScript raised from 4.9 to 5.5 because zod 4 typings cannot be parsed by 4.9 (a
  deliberate compatibility upgrade; production build verified). `skipLibCheck` enabled.
  The duplicate `User`/`TagData` interfaces in `src/models.ts` (ESLint errors) were merged
  without changing the effective `TagData` type; the unused stale `User` variant was removed.
- Generated client: `scripts/api-client.sh` generates into an empty directory and diffs
  for drift. 92 stale files the generator no longer produces were removed; all other
  generated files were already identical to the current schema.
- CI: backend job is blocking (no `continue-on-error`), installs the lock, runs Ruff and
  fast tests; new frontend job (lint, type check, tests) and drift job (pinned generator
  image). Production and test-main deploys now require all three to succeed (previously
  `always()`, i.e. they deployed even after failed tests). PR preview deploys are unchanged.

## #200 outcome

- `make test-integration`: `scripts/with-test-weaviate.sh` starts a uniquely named Weaviate
  1.34.4 container with no volume on random loopback ports and a random per-run
  `SEMANT_TEST_STORE_TOKEN`, and removes it afterwards; pytest runs `-m integration`
  against it. Tests read only `SEMANT_TEST_*`, never the application's `WEAVIATE_*`.
- Ownership (`tests/weaviate_store.py`) is specific to the run: an empty instance is
  claimed with a marker holding the token, a marker with the same token is accepted, and
  anything else (unmarked data, or a marker from another run) is refused before any write.
  Verified by pointing the variables at the local development Weaviate: refused, its
  collections unchanged. Non-loopback hosts need `SEMANT_TEST_WEAVIATE_ALLOW_NONLOCAL=1`.
  Collection names cannot be prefixed per run (some are also used as reference names in
  filters), so the run's namespace is the whole throwaway instance.
- Fixture corpus `tests/fixtures/corpus.json` (single source for pytest and Playwright,
  validated on load): owner/annotator/outsider/admin, three collections (one shared, one
  of another user), a document in two collections with partial chunk membership,
  manual/automatic/rejected spans and positive/automatic/negative chunk tag references,
  Czech diacritics, a combining mark, a non-BMP character, missing metadata. The test
  schema (`create_app_schema`) mirrors the properties/references the backend uses in the
  deployed schema; unused metadata-enrichment properties are omitted.
- Integration tests (22): store isolation/cleanup, collection listing for owner/shared/
  unrelated/admin, stats, partial membership, document stats, span metadata, Unicode
  round trip, BM25 search scoped by collection and chunk tag, HTTP login for corpus users
  and document-view endpoints. They pin current behavior; no access checks exist yet (#201).
- `make test-e2e`: Playwright 1.63.0 (Chromium headless shell). The web server builds the
  frontend into `dist/e2e` (new `QUASAR_DIST_DIR` override in `quasar.config.js`) and starts
  `tests/e2e_server.py`: seeded store, temporary SQLite with corpus users, built SPA on the
  same origin, fake embedding/Topicer providers (`tests/fake_providers.py`; other provider
  routes answer 501, no API keys). Smoke tests: login persists across reload, shared user
  opens a shared document, approved annotations render at their offsets, switching
  collection shows no stale chunks/annotations. `aria-label="User menu"` was added to the
  account button so it has an accessible name.
- Fast tests added for the ownership rules and for the fakes speaking the real Topicer
  client protocol.
- CI: new blocking `Integration tests` job with a per-job Weaviate service container;
  production and test-main deploys also need it. The browser suite is not in CI yet (#212).

## #201 outcome

- `features/collections/access.py`: direct-lookup checks `require_collection_read`,
  `require_annotation_edit`, `require_tag_definition_edit`, `require_membership_edit`,
  `require_collection_owner`, plus tag/span -> collection resolution and tag/chunk scope
  checks. Mapped to 401 (anonymous), 404 (no read access, unknown or malformed id) and
  403 (shared user lacking the right) in `create_app`. Rights table: ADR 0007
  ("Decided for the implementation"); the maintainer decided that shared users may edit
  tag definitions and see the member list, and that metadata edits/deletion are owner-only.
- Every collection, tag, span, AI-assistance, span-chat, sharing/member and
  document-with-collection route checks access before reading, writing or calling a
  provider (AI checks run before the stream starts). Collection+document requests
  (document chunks/range/neighbour/stats, scoped annotation deletes, AI suggestions)
  also require the document to be linked to the collection
  (`require_document_in_collection`, one lookup independent of document size); before,
  optimized AI mode called the provider for another collection's document. Add/remove
  document are membership operations and do not require it. In the local snapshot every
  collection/document pair implied by chunk membership has this link. Previously most of them had no
  check at all; several did not even require login.
- Contract changes (generated client regenerated, frontend updated):
  - span reads (`GET /api/tag_spans`, `POST /api/tag_spans/batch`) require `collection_id`;
    without it they returned spans of every collection;
  - add/remove document and add chunk return a `WriteResult` (`outcome` complete/partial/
    failed, `succeeded`, `failed` with step and `uncertain` for timeouts, `unattempted`)
    instead of an empty body / `CreateResponse`;
  - bulk span update and the two scoped span deletes keep their fields and add the
    `WriteResult` fields; AI suggestion events add `unsaved` and report save failures and
    out-of-scope proposals in `error` (previously silently dropped);
  - search with `user_collection_id` uses the direct check: no access is now 404, was 403.
- Behavior fixes: the undefined-`e` branch in add chunk is gone (a failed document link is
  now a reported partial outcome, not a logged success); `add_document` no longer
  re-adds existing links (a string/UUID comparison never matched); `remove_document`
  unlinks chunks first and keeps the document linked if any chunk unlink fails; AI
  optimized mode no longer saves proposals on chunks outside the collection returned by
  the provider; bulk span ops and annotation edits are limited to one collection and
  cannot attach chunks to a collection.
- Termination: scoped span deletes and document membership changes list the affected ids
  before writing; the refetch-first-page cascades (tag/collection delete, reference
  removal) stop with an error when a page repeats processed objects. Verified with more
  than a full page of failing deletes.
- Tests: fast access-rule and outcome tests; integration tests for the read matrix
  (owner/shared/unrelated/admin/anonymous), denials with unchanged store state, no
  provider call on denied AI requests, mixed-scope batches, revocation, admin owner
  change, and partial/total failures injected into real Weaviate writes.
- Frontend: membership and bulk span calls raise `IncompleteWriteError` with a readable
  message for partial/failed outcomes; the document view and the AI panel update local
  state only for ids the backend reports as done and notify about the rest.

## #202 outcome

- The #182 -> #184 -> #187 stack was superseded, not rebased: its branches predate sharing,
  the newer chunk routes and the #201 access/outcome work. Kept from the stack: per-
  repository dependency injection, a shared paging helper, a single chunk mapping, removal
  of dead code (`Document.read_all`/`search`, `Tag.read_all`/`read_spans`/`search_spans`,
  `UserCollection.read_all_chunks`/`get_document_chunks_with_context`,
  `WeaviateErrorContext`, unused `WeaviateHelpers` methods, the `.idea` file), routes no
  longer catching errors into fake success, and the `PatchTag` "at least one value"
  validator (#184). Not kept: the `WeaviateBaseRepository` CRUD base class and the methods
  that only raised `NotImplementedError`; the `NotFoundError`/`ConflictError` in the
  Weaviate-named exception module.
- Conventions (`adapters/weaviate/__init__.py`): plain concrete repositories
  `DocumentRepository`, `TagRepository`, `UserCollectionRepository` in
  `adapters/weaviate/{documents,tags,collections}.py`; ids are `UUID`; single reads
  return `None` for a missing object, operations needing one raise
  `core.errors.NotFoundError`; SDK errors propagate unwrapped (500). `paging.fetch_all`
  reads every page before returning (offset paging, Weaviate's `QUERY_MAXIMUM_RESULTS`
  still applies). `writes.py` holds `step_failure`, `guard_progress` (now raising
  `NoProgressError`) and the tag/collection delete cascades. Their "process the first page
  again" loop now re-queries after every non-empty page, also a short one, and ends only on
  an empty result; before, a short last page whose deletes reported success without taking
  effect ended the loop (a tag was then deleted while its spans remained). No Protocols were added: the
  only fakes needed (access tests) are plain objects.
- `core/errors.py`: `NotFoundError` (404) and `InvalidRequestError` (400), mapped in
  `create_app`; `access.ResourceNotFound` is a `NotFoundError`.
- SQL user lookups moved out of the Weaviate repository into `adapters/sql/users.py`; the
  sharing/owner-change/member routes look users up there and pass ids/names to the
  repository. The repository no longer checks ownership itself (the route's access check
  does).
- Bootstrap owns the Weaviate client: `AppResources.connect_weaviate` runs in the
  lifespan after SQL setup and builds the repositories and the transitional facade on one
  client, closed at shutdown. **Startup now fails if Weaviate is unreachable or not
  ready** (`WeaviateUnavailable`), instead of the first request connecting (and
  `exit(-1)` when not ready). The client uses `skip_init_checks=True` plus an explicit
  readiness check, so it no longer requests pypi.org. `create_app(config,
  weaviate_connector=...)` injects a stand-in; fast tests use
  `tests.app_support.offline_weaviate`. `WeaviateAbstraction.create` is kept for
  standalone scripts (`search_filters.fetch_db_filter_stats`, `rag_runner_demo.py`).
- Migrated callers: document, tag and collection routes and `features/collections/access.py`
  use the repositories; access functions take the repository they read (collections,
  tags, spans), and unmigrated routes pass `searcher.userCollection` etc.
- Behavior changes (no schema change; generated client only has updated descriptions):
  - removing a chunk that is not in the collection succeeds (was 400 from a Weaviate
    error); removing an unknown chunk is 404; storage failures are 500 (were 400);
  - removing a document that is not in the collection is a no-op `complete` result;
    an unknown document is 404 (was a `failed` result);
  - tag PATCH with no non-null field is 422 (was 404); null fields are kept as before;
  - malformed document ids in `GET /api/document/{id}` and the chunk count are 404;
  - `read_all_documents` and `get_chunks_in_range` read every page (were capped at 25
    and 10 000).
- Tests: `tests/integration/test_repositories.py` (missing ids for every write and read,
  mapping of documents/tags/collections/chunks, a 205-chunk document across pages, 30
  collection documents, 105 tags, tag and collection cascades over more than a page,
  repeated add/remove of chunks, documents and shares) and
  `tests/integration/test_repository_routes.py` (HTTP error mapping, PATCH validation,
  SQL user lookups); fast tests for the startup connection, startup failure without
  Weaviate and the default connector's error.

## #203 outcome

- Collections is a feature package: `features/collections/routes.py` (moved from
  `routes/user_collection_routes.py`), `service.py`, `access.py`, `schemas.py` (moved from
  `schema/collections.py`). The Weaviate adapter stays `adapters/weaviate/collections.py`.
  No ports, models or service classes were added.
- `service.py` holds one function per use case (metadata, owner change, delete, sharing,
  members, stats, document/tag lists, collection-scoped document reads, membership
  changes). Each takes the repositories it needs plus the user (or `None`) and runs the
  access check itself before any other read or write, so non-HTTP callers get the same
  rules. Routes only parse HTTP, inject dependencies and call one service function.
  Other features may call these functions instead of the repository.
- Owner change checks `access.require_admin` in the service as well (the route still
  uses the `current_active_admin` dependency, so HTTP behavior is unchanged).
- SQL user lookups: `adapters/sql/users.UserLookup` wraps one request's session and returns
  `UserSearchResult` instead of ORM users; injected by `routes.dependencies.get_user_lookup`.
  The service does the sharing/owner-change/member lookups; routes no longer touch SQL.
- No API change: the exported OpenAPI schema is byte-identical to the base, the generated
  client is unchanged.
- Tests: `tests/test_collection_service.py` (service called directly: owner/shared/
  unrelated/admin/anonymous for every collection operation, denied calls reach no
  repository method or user lookup, share/owner-change validation, member lookup); the
  existing HTTP integration tests (CRUD, sharing, membership, paging) pass unchanged.
- `GET /api/documents/{document_id}/chunks/count` (public corpus read) is still registered
  by the Collections router; move it to the Documents router in #210, preserving public
  access and API behavior.

## #204 outcome

- Contract (ADR 0004): chunk `automaticTag` / `positiveTag` / `negativeTag` references
  are the projection of the spans. A chunk references tag `T` through the property of
  span type `auto` / `pos` / `neg` exactly when at least one such span with tag `T` is
  anchored on it (`text_chunk`; a cross-chunk span counts on its first chunk only, as it
  is stored). Search is unchanged and still filters on these references.
- Meaning (decided in review of PR #223): the lists reflect the spans' *current* type.
  `automaticTag` holds tags with at least one unresolved AI suggestion (`auto` span) on
  the chunk, not "the AI ever proposed this tag". Approving a suggestion changes its span
  to `pos`, so the tag moves from the chunk's `automaticTag` list to its `positiveTag`
  list unless another `auto` span of that tag remains; rejecting moves it to
  `negativeTag`. Search with `automatic=true` alone therefore finds chunks with pending
  suggestions. Keeping AI provenance after approval would need an origin field on spans
  (not stored today) and is not planned.
- Before: no backend path wrote these references at all (span create/update/delete,
  bulk and scoped deletes, AI proposals). The local snapshot has 0 chunk tag references
  and 602 spans: 250 references the spans require are missing (187 automatic, 37
  positive, 26 negative), so tag-filtered search there finds nothing. No unbacked
  references exist in the snapshot.
- `adapters/weaviate/chunk_tags.py`: `sync_chunk_tags(pairs)` re-derives the references
  of given (chunk, tag) pairs from the spans stored now (reads the pair's spans and the
  chunk's references, adds/removes only the difference). It is idempotent, so a second
  backing span neither duplicates the reference nor is the reference removed while
  another span needs it. A failed read is a failure, never "no spans".
- Every span mutation calls it after the span write for the pairs it touched: create;
  every PATCH, also offset-only (the span's pair; on tag reassignment the old and the new
  pair), so saving a span again retries a failed chunk tag update; bulk update (once per
  pair after all span updates);
  single, scoped (`in_document/delete`) and AI (`auto_spans/delete`) deletes; AI proposal
  persistence. It also runs when the span write raised (a timed-out write may have
  landed), then the error propagates. Tag and collection deletes already removed the
  references (#202).
- Best effort (ADR 0002): a failed reference write keeps the span write and is reported
  as step `update_chunk_tags` with item `chunk_id:tag_id`, and the outcome is never
  `complete` when the attempted sync failed. Saving the span again (any PATCH, including
  offset-only) re-derives the pair; a failed sync after a delete is left for the audit.
  No background repair.
- Contract changes (generated client regenerated, frontend updated):
  - `POST /api/tag_spans` and `PATCH /api/tag_spans/{id}` return `TagSpanWriteResult`
    (the `TagSpan` fields plus `outcome`, `succeeded`, `failed`, `unattempted`);
  - `DELETE /api/tag_spans/{id}` returns 200 with a `WriteResult` (was 204, no body);
  - bulk update and the scoped/AI deletes may list `update_chunk_tags` failures in
    `failed` (outcome `partial`); AI suggestion events report saved spans whose chunk tag
    failed in `error`.
  - Frontend: the span store keeps the saved/deleted span locally and shows a warning for
    a partial result (`searchTagWarning`), instead of treating it as a failed write.
- Audit/cleanup: `python -m semant_demo.maintenance.chunk_tag_audit` (DEVELOPMENT.md
  section 10) reports `unbacked` and `missing` references; `--apply REPORT
  --remove-unbacked/--add-missing --confirm-endpoint HOST:PORT` corrects only the listed
  pairs after re-checking them. Run read-only against the local snapshot (result above);
  `--apply` was not run against any development, shared or production database.
- Tests: `tests/integration/test_chunk_tags.py` (real Weaviate, HTTP API + tag-filtered
  BM25 search): create, suggestion create, approve, reject, delete, second backing span
  then final removal, approving one of two suggestions, tag reassignment, offset-only
  change, bulk approve, scoped and AI deletes, injected reference write failures on
  create (then a type re-save fixes it) and delete, an offset-only re-save that reports
  `partial` while the reference write still fails and repairs it afterwards, a timed-out-
  but-applied update, failed read not taken as absence, audit/cleanup removing only
  unbacked (also duplicated) references and keeping one backed since the audit. With the
  sync disabled, 14 of the first 19 fail; the offset-only test fails with the earlier
  "offset-only patches skip the sync" behavior. The
  fixture corpus is validated to satisfy the contract. Fast tests: cleanup refuses without
  a matching confirmed endpoint, before connecting; frontend unit tests for the warning.

## #205 outcome

- Search is a feature package: `features/search/routes.py` (moved from
  `routes/search_routes.py`), `service.py`, `filters.py` (moved from `search_filters.py`)
  and `schemas.py` (neutral `ChunkQuery`, `FieldCondition`/`Op`, `TagFilter`). The
  Weaviate side is `adapters/weaviate/search.py` (`ChunkSearchRepository`): filter
  translation (document fields through the `document` reference), BM25/near-vector/hybrid
  call, returned references and result mapping. `weaviate_utils/text_chunk.py`
  (`TextChunk.search`) is removed. No Protocols were added; fakes are plain objects.
- `service.retrieve(backends, user, request, filter_definitions)` checks access, turns
  configured filters (or, without them, the legacy `min_year`/`max_year`/`language`
  fields) into conditions, embeds the query for vector/hybrid modes and calls the
  adapter. `service.search` adds the optional summaries. Display text normalization
  (joined hyphenated line breaks) moved from the adapter into the service; stored text is
  unchanged.
- Embeddings: `adapters/embeddings/gemma.GemmaEmbeddings(config.GEMMA_URL)` is built by
  `AppResources.create` and injected (`SearchBackends`, dependency
  `get_search_backends`); `gemma_embedding.py` and its process-wide `config` read are
  removed. Timeouts unchanged (36 s query, 6 s documents).
- Tag authorization (deferred from #201): every `tag_uuids` value must belong to exactly
  one collection the user can read, and to `user_collection_id` when given
  (`access.require_readable_tags`). Unknown, malformed, other users' and other
  collections' tags all get 404 `{"detail": "Tag not found"}`; anonymous requests with tags
  get 401. Checked before embedding or retrieval, also when neither `positive` nor
  `automatic` is set (those tags still do not filter). Previously any tag id was accepted
  (unknown ids returned no hits). Public search without collection and tags is unchanged,
  also anonymously. The search page never sends tag ids, so the UI is not affected.
- Summaries are optional: `SearchResultsSummarizer.__call__` now returns the parts that
  failed (`title`, `query_summary`, `results_summary`) through a new `on_error` callback;
  the parts keep the configured fallback text ("N/A") as before. If any part failed or the
  summarizer raised, the response keeps the hits (and finished summaries) and gets
  `warnings: ["Some titles or summaries could not be generated."]`. Before, provider
  errors silently became "N/A" and an unexpected summarizer exception made the search
  500. `/api/summarize/results` is unchanged.
- RAG: `rag_request(request, retrieve)` receives `service.public_retriever(backends)`
  instead of the facade, i.e. authorized public-corpus retrieval without summaries (RAG
  requests carry no collection or tags; such a request would be refused like an
  anonymous one). `rag_runner_demo.py` builds the same from its own connection.
- `create_default_configurations.py` connects to Weaviate itself and reads the year/
  language statistics through `ChunkSearchRepository.document_filter_stats()`;
  `fetch_db_filter_stats` no longer opens a connection or reads the process-wide config.
  `WeaviateAbstraction.create`/`close` (only used by these scripts) are removed.
- Contract changes (generated client regenerated): `SearchResponse.warnings: list[str]`
  (default empty); the search page shows each warning. The never-populated
  `tags_result` (built by `TextChunk.search` but dropped by the response model, so never
  on the wire) is gone from the backend and from the hand-written `models.ts` type; the
  adapter no longer fetches the `automaticTag`/`positiveTag` references for it.
- Tests: `tests/test_search_service.py` (fakes: embedding choice for each mode and HyDE,
  embedding failure, legacy/configured filter normalization, invalid filters before any
  provider call, tag kinds, collection/tag authorization matrix with no retrieval or
  embedding on denial, public retriever, display text, reported/raised summary failures
  including the templated summarizer's provider-error path);
  `tests/integration/test_search.py` (real Weaviate: every filter alone and combined,
  vector/hybrid with the same restrictions, mapping, filter stats; HTTP: permitted tag
  filters with and without collection scope, another user's tag, permitted mixed with
  inaccessible, unknown/malformed tags with identical answers, recorded adapter calls
  prove denial precedes retrieval, configured and legacy filters, invalid filter,
  injected embeddings, summary failure warning). The old facade-based search test in
  `test_collections_store.py` moved there.

## #206 outcome

- Annotations is a feature package: `features/annotations/routes.py` (tag and span routes,
  moved from `routes/tag_routes.py` and `routes/span_routes.py`; registered as two routers
  so the OpenAPI path order is unchanged), `service.py`, `schemas.py` (moved from
  `schema/tags.py` and `schema/spans.py`) and `offsets.py`. Persistence is
  `adapters/weaviate/spans.py` (`SpanRepository`, replacing `weaviate_utils/span.py`) and
  the existing `tags.py`; `weaviate_utils/helpers.py` and `weaviate_exceptions.py` are
  removed (no other users). No Protocols; fakes are plain objects.
- `service.py` takes an `AnnotationStore` (collections, tags, spans, chunk tags, documents
  repositories; dependency `get_annotation_store`) and the user, and checks access before
  any other read or write: list/read need collection read, span writes annotation edit,
  tag writes tag-definition edit (unchanged rights). It owns the span write followed by
  the chunk tag re-derivation and the partial outcomes that `weaviate_utils/span.py` held
  (#204). The AI suggestion routes save validated proposals through `service.save_span`
  (no access check: the route has checked it before the stream) and delete suggestions
  through `service.delete_suggestions_in_document`; the rest of AI orchestration is #207.
  Span chat reads spans through the facade's `SpanRepository`.
- Coordinates (characterized, not changed; ADR 0006): spans are stored on the chunk where
  they start, `start`/`end` half-open, in UTF-16 code units (what the document view sends:
  JavaScript `String.length`); a span may continue into the following chunks of its
  document while `order` is consecutive, also through chunks outside the collection.
  `offsets.py` and `src/utils/spanOffsets.ts` (now used by `useAnnotations.ts` for the
  offset/projection math, behavior unchanged) are tested against the shared cases in
  `semant_demo_backend/tests/fixtures/text_offsets.json` (diacritics, combining mark,
  non-BMP character, chunk boundaries, three chunks, later anchor, gap, past end).
- **Behavior change — offset validation:** span creation and PATCH/bulk updates that send
  `start`/`end` are rejected with 400 (before any write; a bulk request as a whole) when
  start is negative or not inside the anchor chunk, the span is empty, crosses a gap in
  chunk order or ends after the document's text. Before, any integers were stored.
  Updates without offsets (approve/reject/retag) do not re-check stored offsets. Reads
  only the anchor chunk unless the span continues past it. AI proposals are not checked
  here (they are clamped by the AI route; see known problems).
- **Behavior change — empty span PATCH** (no non-null field) is 400 (was 500).
- Tag creation (recorded after #202): the service inserts the tag and then links it.
  If the link fails, it deletes the new tag again (best effort) and fails with 500 and
  `{"detail", "step": "link_collection", "completed": {}, "uncertain"}`; nothing remains,
  creating again is safe. If the deletion fails too, `step` is `delete_unlinked_tag`,
  `completed` is `{"insert_tag": 1}`, `uncertain` is set if either write timed out, and the
  detail says the link failed and names the tag id that may remain (unreachable: it
  belongs to no collection).
  Before: 500 and an orphaned tag every time.
- Deletion cascades (follow-up from PR #221), decision: **keep the 204-on-success
  contract** (no `WriteResult` for these deletes): a delete either finishes or is
  retried, there are no independent items a client could act on separately, and retrying
  is idempotent. Instead a failure is no longer an unstructured 500: `IncompleteWriteError`
  (core/errors.py) answers 500 with `detail` (failed step, cause, completed steps, "deleting
  again continues"), `step` (`unlink_chunk_tag`, `delete_span`, `delete_tag`; collections
  also `unlink_chunk`, `unlink_document`, `delete_collection`), `completed` (counts) and
  `uncertain` (timeout). The no-progress stop reports the step and "a deletion reported
  success without taking effect". The frontend shows the detail in the tag/collection
  delete and tag create notifications. Collection deletion authorization stays in the
  Collections service. Generated client: descriptions only.
- Chunk tag concurrency (tracked from #204), decision: per-pair serialization within the
  process. `ChunkTagRepository` (one per application, in bootstrap) runs the re-derivation
  of a (chunk, tag) pair one at a time (`asyncio.Lock` per pair, kept only while used).
  Every span write is followed by its own re-derivation, so the last one of a pair reads
  all earlier span writes and the pair ends consistent. The deployed backend runs one
  process (`run.py`); with several workers the race would remain and the audit stays the
  manual recovery. The maintenance cleanup does not take the lock.
- Tests: `tests/test_annotation_service.py` (fakes: access matrix for every tag/span use
  case with no write on denial, shared-user writes, tag link failure with cleanup, timed-out
  link, failed cleanup, write-then-sync order, sync after a raising write, partial sync,
  cross-chunk reads only when needed, every invalid-offset kind before any write, UTF-16
  units, chunk outside the collection, empty patch, approval of a span with old invalid
  offsets, retag syncs both pairs, bulk partial failure and whole-batch offset validation,
  scoped delete partial failure); `tests/test_span_offsets.py` and
  `test/unit/spanOffsets.spec.ts` (shared fixture); `tests/integration/test_annotations.py`
  (real Weaviate: cross-chunk create and reload, continuation through a chunk outside the
  collection, UTF-16 end with a non-BMP character, gap, invalid offsets, invalid offset
  PATCH, approval/rejection reload, tag link failure with and without cleanup and the safe
  retry, tag and collection cascades failing part way and finishing on retry, concurrent
  delete/create on one pair — fails without the lock, verified by disabling it);
  `test_partial_writes.py` now also checks the no-progress body. Frontend unit test for the
  delete/create message.

## #207 outcome

- AI suggestions are an Annotations workflow: `features/annotations/suggestions.py`
  (orchestration) and `features/annotations/suggestion_routes.py` (moved from
  `routes/ai_assistance_routes.py`; HTTP, NDJSON encoding, disconnect handling). Topicer is
  `adapters/topicer/client.py` (`TopicerClient`, moved from `ai_assistance/topicer_client.py`),
  built by bootstrap from the app's config (`AppResources.topicer`, dependency
  `get_topicer`): it no longer reads the process-wide `config`. Suggestion models moved from
  `schema/ai_assistance.py` to `features/annotations/schemas.py` (span chat models stay);
  the unused `SuggestSpansSelectionResponse` is removed. AI routes no longer use the
  facade. `anyio` (already installed via Starlette) is now a declared dependency.
- `prepare_document_run` / `prepare_selection_run` check access and scope (moved from the
  routes, same order and status codes) and load tags and chunks before the stream starts;
  `SuggestionRun.events()` calls Topicer, validates, saves through `service.save_span` and
  yields typed events. Routes only encode them. Unchanged: request-scoped execution,
  per-proposal persistence before its event, at most 10 Topicer calls per run (thorough
  now starts further chunks as calls finish instead of creating every task up front), no
  rollback, `unsaved`/`error` per event.
- **Contract change — terminal event:** every stream now ends with
  `{"event": "end", "outcome": "complete"|"partial"|"failed", "saved", "rejected",
  "save_failures", "search_tag_failures", "provider_failures", "error"}`; result lines get
  `"event": "result"`. No end line means interrupted. An unexpected error during a run (e.g.
  a failed read) ends it with this event instead of a broken stream. The NDJSON models are
  not in OpenAPI; the generated client changed in descriptions only. Details and the
  outcome rules: ADR 0003 "Implemented in #207".
- **Behavior change — provider validation:** a proposal is rejected (counted in `unsaved`
  and `rejected`, reason in `error`) when its tag is not a requested tag, its chunk is not
  a chunk of the document in the collection, or its offsets are not integers with
  `0 <= start < end <= len(text sent)`. Before, out-of-range offsets were clamped and
  saved, and proposals without a tag or offsets were dropped silently.
- **Behavior change — offset units (resolves the #206 known problem):** Topicer offsets
  are read as Python string offsets (code points) into the text it was sent (assumed, see
  known problems) and stored in UTF-16 units (`offsets.utf16_offset`); selection offsets
  from the browser are UTF-16 and converted for slicing (`offsets.code_point_offset`). Both
  differ from before only after characters outside the BMP.
- **Fix — selection across chunks outside the collection:** the browser sends only the
  collection's chunks of a selection. A proposal continuing from one selected chunk into a
  later one now gets an end that counts the document's chunks in between (as user spans
  are stored, ADR 0006); before, the end was measured over the selected chunks only and
  pointed into the skipped chunk. A proposal across a gap in chunk order is rejected.
  Selection requests are refused with 400 when the chunks are not distinct and in document
  order, or the selection contains no text of them (was an empty stream).
- Cancellation: `_RunResponse` closes the run however the response ends (Starlette
  cancels a disconnected stream but does not close its iterator, so before, a run suspended
  at a send kept its tasks until garbage collection). Closing cancels running Topicer
  calls and waits for them (shielded from anyio's repeated cancellation); a span write in
  progress finishes with its chunk tag first. Saved spans remain.
- Duplicates (documented, not changed): ADR 0003 "Duplicate proposals".
- Frontend: `src/utils/ndjson.ts` reads NDJSON (lines split across chunks and UTF-8
  characters); `useAiAssistance` gives each run a token. `reset()` (document change,
  collection change, and leaving the document view) aborts document-wide and selection
  runs; their late events, errors and finally blocks no longer touch the store or loading
  state; `runOnSelection` returns `null` for a
  cancelled or superseded run. The end event sets `lastStatus` and a message for partial,
  failed and interrupted runs; the panel says when a run was cancelled.
- Tests: `tests/test_suggestions.py` (fakes: span stored before its event, provider
  failure after partial success, all calls failing, no proposals, storage failure with an
  uncertain timeout, chunk tag failure, every invalid proposal kind with no write, UTF-16
  conversion, cancellation by closing and by task cancel, anyio-style cancellation waiting
  for slow-to-cancel calls, cancellation during a write, concurrency limit, unexpected
  error, route closing the run on disconnect, duplicate characterization, access/request
  denials before any provider call, optimized-mode chunk validation, selection anchoring,
  selection across a hidden chunk, gap, invalid selections); disabling the route close, the
  write shield or the cleanup shield each fails a test. `tests/integration/test_suggestions.py`
  (real Weaviate: saved suggestions reload and are found by tag-filtered search, partial
  run keeps saved spans, UTF-16 storage with an emoji, cross-chunk selection accepted by
  the user-span validation, client disconnect on a real uvicorn server cancels the
  remaining provider call and keeps the saved span). Existing AI integration tests now
  inject the fake through `use_topicer`/`fake_topicer` (dependency override) and check the
  end event. `test/unit/aiAssistance.spec.ts` (NDJSON splitting, progressive store update,
  interrupted/partial/cancelled runs, late events after a document change; removing the
  token checks fails two tests).
- Not covered: no browser test runs AI suggestions (progressive display and navigation
  during a run); add with the context-scoped state work in #209.

## #208 outcome

- Audit result: two document models (`schemas.Document` for search hits and the document
  view, `schema/documents.Document` for document/browse/collection reads) described the
  same stored object with different fields and a conflicting `author` (`str` vs
  `list[str]`). Their name clash also made OpenAPI emit module-path names
  (`semant_demo__schemas__Document`, `semant_demo__schema__documents__Document`) and
  needless `-Input`/`-Output` copies of `Document`, `TextChunkWithDocument` and
  `SearchResponse`. Every other model has one definition; the chunk models are three
  intentional projections (search/document-view `TextChunk`, collection `Chunk` with
  `in_collection`, internal `ChunkText`), now documented in `schema/chunks.py`.
- One `Document` (`schema/documents.py`) for every read: the fields of both, `author:
  list[str]` (stored `text[]`), `library` optional (still filled in with `"mzk"` for search
  hits and the document view, absent elsewhere as before), `partNumber: int | str`,
  `keywords: list[str]` (was `str | list[str]` on search hits, which the generator renders
  as an unusable empty type; no store we can see holds a string). OpenAPI now has single
  `Document`, `TextChunkWithDocument` and `SearchResponse` components; paths are unchanged
  apart from those references (checked by diffing the export with references and
  descriptions normalized).
- **Fix #215:** `GET /api/documents/{document_id}/{collection_id}/chunks` answered 500 for
  every document with authors; it returns them as a list. The `KNOWN_BROKEN_READS`
  exception in `test_access.py` is removed.
- **Contract change — search hit documents:** the search adapter requested `authors` and
  `subTitle`, which the local snapshot does not store (it stores `author`, `subtitle`), so
  hits never carried authors; requesting `author` would have failed like #215. It now
  requests every field of `Document`, so hits include `author` (list), `subtitle` and the
  other stored metadata. The search page shows the authors joined (it showed
  "Unknown Author"). `DocumentMetadataCard` joins list values (before, its document view
  data failed to load for such documents).
- Moves (no wire change): search HTTP models (`SearchRequest`, `SearchResponse`,
  `TextChunkWithDocument`, filters, summaries) to `features/search/schemas.py`; `SpanType`,
  `TagSpan` to `features/annotations/schemas.py`; `TextChunk` to `schema/chunks.py`;
  `DocumentDetail*` to `schema/documents.py`. Removed unused `TagData` and `APIType`;
  `ExtractedMeradata` (a type annotation only) declared `min_date` twice and `language: int`,
  now `max_date` and `str`. `schemas.py` keeps the RAG/feedback models, `CreateResponse`,
  `CollectionNames` and the SQL base/feedback table (moving the SQL base is #210).
- Canonical vs display text: search hits carry display text (`service.display_text`), the
  document view canonical stored text that span offsets refer to; stated on
  `TextChunkWithDocument` and `DocumentDetailTextChunkWithUserCollectionInfo` (OpenAPI
  descriptions). No field was added.
- Frontend: client regenerated (pinned generator); `SemantDemoSchemaDocumentsDocument`/
  `SemantDemoSchemasDocument` users now use `Document`. `src/models.ts` keeps only the raw
  snake_case types still used by the axios callers (search page, user store; they move to
  the generated client with the transport work in #209), aligned with the backend
  (`author` list, optional `library`/`title`, `public` boolean, `language` string, no
  `page`, no never-sent `automaticTags`/`positiveTags`); 20 unused legacy types (task-era
  responses, `TagData`, ...) are removed. Unused zod duplicates `src/schemas/{collection,
  documents,tags}.ts` (stale shapes) are removed. Type-check baseline unchanged (60).
- DATABASE.md: the documented `Documents` properties differ from the local snapshot;
  recorded there. Deployed databases were not inspected.
- Tests: `tests/test_api_contracts.py` (offline: no module-path or `-Input`/`-Output`
  components, every document read references `Document`, document and browse responses
  serialize stored list/uuid/datetime properties through the real routes, a search
  response validates back as summary input); integration: document view chunk detail with
  zero, one and two authors (repository and HTTP), search hit authors (fixture `letters`
  now has two authors). With `author: str` restored, the new integration tests and the
  owner/annotator access-matrix cases fail.

## Temporary exceptions

- **Process-wide `config` still read directly** by `ai_assistance/span_chat.py`. An app
  built with `create_app(other_config)` still uses the process-wide settings for span chat.
  `semant_demo.main:app` passes the same object, so production has one source. Topicer
  takes the app's config since #207. Remove with the span-chat audit in #210. (The standalone scripts `rag/rag_runner_demo.py` and
  `create_default_configurations.py` read it as their entry-point configuration.)
- **Transitional `WeaviateAbstraction` facade** (`weaviate_utils/weaviate_abstraction.py`)
  is still used by span chat only. It is built on the application's one client. Search,
  summarizer, RAG (#205), tags/spans (#206) and AI suggestions (#207) no longer use it.
  Remove the facade when span chat has moved (#210).
- **Vue type-check baseline** (`semant_demo_frontend/typecheck-baseline.json`, 60 errors).
  Several are real defects: `useTagging.ts` calls `DefaultApi` methods that no longer exist,
  `chunk_collection-store.ts` passes `userId` as fetch options, services import missing
  model exports. Shrink the baseline as frontend code is migrated (#209), then reconcile
  any remaining entries with explicit owners during #210.
- **Ruff rule set limited** to `E9, F63, F7, F82`. The default rule set reports ~140 legacy
  findings (unused/star imports, comparisons). Python formatting and a Python type checker
  are not enforced yet.
- **Access checks are called from route handlers** outside Collections, Search and
  Annotations (span chat, document routes), because those features have no service layer
  yet. Each handler calls the check before any other work. Audit the remaining Document and
  span-chat boundaries under #210 while preserving intentionally public corpus reads.
  Collections (#203), Search (#205), Annotations (#206) and AI suggestions (#207, in the
  `prepare_*` functions) enforce access in their services; `service.save_span` is the
  documented exception (its callers `create_span` and the suggestion workflow check first).
- **Vitest 0.23.4** is pinned because it is the last release supporting Vite 2
  (`@quasar/app-vite` 1). Upgrade together with Quasar app-vite 2 / Vite 5.

## Known problems affecting later steps

- Existing data needs the reviewed #204 cleanup before tag-filtered search reflects
  annotations created before #204 (in the local snapshot: 250 missing references). Not
  run; deployed databases were not audited.
- Chunk tag sync is not atomic with the span write (ADR 0002, reported as
  `update_chunk_tags`). Concurrent writes on one pair are serialized only within a
  process (#206); running several backend workers would reopen that race (audit is the
  recovery). Maintainer direction (2026-10-08): when scaling out, prefer eventual
  consistency (e.g. re-deriving pairs later or a periodic audit) over distributed locking,
  to keep the system simple and fast.
- Topicer offset units are assumed to be Python string offsets (code points) of the text
  it was sent (#207 converts them to UTF-16); this matches the fake provider and the
  previous clamping but was not verified against the real Topicer (no live calls in this
  refactor). If Topicer reports UTF-16 or byte offsets, adjust `_validated`/`_save` in
  `suggestions.py`. AI spans stored before #207 next to non-BMP characters may be off by
  one unit per such character; not migrated (ADR 0006). In optimized mode offsets are
  checked against the stored chunk text, not the text Topicer echoes back.
- AI suggestion concurrency is bounded per run (10 Topicer calls), not across concurrent
  runs: [#227](https://github.com/DCGM/semant-demo/issues/227).
- TODO after the refactor (post-refactor work, not a blocker for #205 or any refactor gate;
  [#224](https://github.com/DCGM/semant-demo/issues/224) — Define tag-filtered search
  behavior for cross-chunk spans): a cross-chunk span sets the
  chunk tag only on its anchor (first) chunk, so tag-filtered search does not find the
  following chunks it covers. Decide whether covered chunks should carry the tag too
  (needs the covered-chunk computation from canonical offsets).
- Removing a chunk or document from a collection leaves its spans and therefore its chunk
  tag references (consistent with each other, unchanged by #204); search scoped to the
  collection excludes the chunk through membership.

- A partial add chunk (chunk linked, document link failed) leaves the chunk in the
  collection while its document is not, so collection+document requests for that document
  return 404 until the add is retried (the partial outcome is reported to the user).
- Shared users still see owner-only membership, metadata and sharing controls despite
  backend denial; hide or disable these controls without restricting tag editing/member
  listing (#209).
- Partial-write failure notifications from #201 lack focused browser/component regression
  coverage; add it in #209.

- Required checks are a repository setting, not part of the workflow file. As of
  2026-10-07 the ruleset for `197-refactor---base` requires "Backend tests", "Frontend
  checks", "Generated API client drift" and "Integration tests" (strict, branch up to
  date). Before merging the refactor into `main`, verify and configure the same four
  required checks for `main` with a repository administrator (#210).
- PR preview deploys still run with production `OPENAI_API_KEY`/`JWT_SECRET` secrets on
  the self-hosted runner and still deploy after failed checks. Not changed in #200 (a
  deployment decision); tracked in #213.
- Deployment: the backend container now exits at startup when Weaviate is not ready
  (it previously started and failed requests). The app compose files use
  `restart: unless-stopped`, so it retries; there is no `depends_on`/health condition
  between the separately deployed stacks.
- Tag creation deduplicates against at most 2000 tags of a collection: #218.
- `UserCollectionRepository.read_all` pages by 1000; the multi-page path of that listing
  is not exercised by a test (needs more than 1000 collections for one user); cover it
  with a real-store regression test in #210.
- The corpus has no stored cross-chunk annotations; `test_annotations.py` creates them
  through the API. Multi-page documents are created by the repository tests themselves.
