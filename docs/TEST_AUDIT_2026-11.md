# Test audit, November 2026

Ledger of the test audit [#847](https://github.com/DCGM/semant-demo/issues/847): which stage
reviews each test file, what each stage decided, and the measured cost before and after its
changes. Stage 1 ([#848](https://github.com/DCGM/semant-demo/issues/848)) made the inventory on
the 21 November 2026 `main` tree; a stage that finishes replaces `pending` in its rows with
**keep**, **consolidate**, **move** (to a cheaper layer), **simplify fixture** or **remove**, and
adds its completion note under [Stage outcomes](#stage-outcomes). A test file added later belongs
to the stage of its feature; [#858](https://github.com/DCGM/semant-demo/issues/858) reconciles
the ledger at the end. The rules for writing tests are in
[CONTRIBUTING.md §4](../CONTRIBUTING.md#4-testing-contract); this is not CI scheduling or
sharding ([#454](https://github.com/DCGM/semant-demo/issues/454)).

## Inventory

| Suite | Entry point | Files | Cases |
| --- | --- | ---: | ---: |
| Backend fast | `make check-backend` (`pytest -m "not integration and not live and not benchmark"`) | 96 | 2,833 |
| Backend real Weaviate | `make test-integration` (`-m integration`) | 50 | 643 |
| Backend benchmarks | `-m benchmark`, opt-in ([#858](https://github.com/DCGM/semant-demo/issues/858)) | 6 | 6 |
| Backend live | marker `live` is declared; no test uses it | 0 | 0 |
| Frontend unit | `npm test` (Vitest, jsdom) | 89 | 1,091 |
| Browser | `make test-e2e` (Playwright, one worker) | 35 | 298 |
| View capture | `make e2e-dev-capture`, `test/capture` × 3 viewports | 1 | 33 (99 runs) |

Counts are collected cases (pytest `--collect-only`, Vitest's report, `playwright test --list`),
parameterizations included. They are logical cases: the capture runner executes each of its
33 cases at three viewports, so a full run of every suite executes 4,970 tests for the
4,904 cases counted here and in the owner map. Compare timings by executions, ownership by
cases. The inventory is the 21 November `main` tree plus `test_harness_defaults.py`, which
#848 added. 151 backend test files hold 3,482 cases; only
`integration/test_annotation_facets_benchmark.py` mixes markers (real-store tests that run in
every integration suite and one opt-in benchmark).

Harness, fixtures and configuration without tests of their own, all owned by stage 1:

- Backend (`semant_demo_backend/tests/`): `conftest.py`, `integration/conftest.py`,
  `app_support.py`, `auth_support.py`, `seed.py`, `corpus.py`, `fakes.py`, `fake_providers.py`,
  `chunk_fakes.py`, `page_fixtures.py`, `real_pages.py`, `synthetic_documents.py`,
  `fixture_profile.py`, `e2e_server.py`, `local_dev.py`, `mcp_support.py`, `weaviate_store.py`
  (not in the original #848 list), `fixtures/**` (corpus, CORPUS.md, text offsets, RAG configs,
  real pages 1.1 MB), `integration/shard_durations.json`, `pyproject.toml` pytest options.
- Frontend (`semant_demo_frontend/`): `vitest.config.ts`, `playwright.config.ts`,
  `test/unit/{setup.ts,console.ts,environment/**,fixtures/**}`,
  `test/e2e/{support.ts,viewports.ts,longDocument.ts,shard_durations.json}`, `test/fixtures/**`.

Cross-language fixtures are deliberate single sources: `fixtures/corpus.json` (integration,
browser server, Playwright, Vitest), `fixtures/text_offsets.json` (backend and Vitest offset
agreement) and `fixtures/real_pages/` (backend converter drift test, Vitest and Playwright).

## Owner map

Each test file has one primary stage. *Disputed* marks a file that two stage issues name;
the parent tracker decides, and the other stage cross-references it.

| Stage | Files | Cases |
| --- | ---: | ---: |
| #848 | 3 | 25 |
| #849 | 15 | 400 |
| #850 | 49 | 898 |
| #851 | 28 | 721 |
| #852 | 42 | 790 |
| #853 | 38 | 621 |
| #854 | 20 | 452 |
| #855 | 15 | 160 |
| #856 | 36 | 331 |
| #857 | 24 | 499 |
| #858 | 6 | 7 |
| **Total** | **276** | **4,904** |

### #848

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/test_app/test_bootstrap.py` | pytest fast | 17 | keep |
| `backend/tests/test_harness_defaults.py` | pytest fast | 3 | keep (added by #848) |
| `backend/tests/test_page_fixtures.py` | pytest fast | 5 | keep |

### #849

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_access.py` | pytest Weaviate | 36 | keep |
| `backend/tests/integration/test_document_rights.py` | pytest Weaviate | 22 | keep |
| `backend/tests/test_auth/test_auth_routes.py` | pytest fast | 12 | keep |
| `backend/tests/test_auth/test_user_search.py` | pytest fast | 7 | keep |
| `backend/tests/test_quota/test_ai_routes.py` | pytest fast | 53 | keep |
| `backend/tests/test_quota/test_ledger.py` | pytest fast | 25 | keep |
| `backend/tests/test_quota/test_operations.py` | pytest fast | 19 | keep |
| `backend/tests/test_quota/test_quota_routes.py` | pytest fast | 22 | keep |
| `backend/tests/test_quota/test_suggestions_quota.py` | pytest fast | 10 | keep |
| `backend/tests/test_user_collection_access.py` | pytest fast | 42 | keep |
| `backend/tests/test_user_collection_service.py` | pytest fast | 106 | keep |
| `frontend/test/unit/authDialogFocus.spec.ts` | Vitest | 6 | keep |
| `frontend/test/unit/collectionPermissions.spec.ts` | Vitest | 9 | keep |
| `frontend/test/unit/documentRights.spec.ts` | Vitest | 11 | keep |
| `frontend/test/unit/quota.spec.ts` | Vitest | 20 | keep |

### #850

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_annotation_attributes.py` | pytest Weaviate | 9 | keep |
| `backend/tests/integration/test_annotation_concordance.py` | pytest Weaviate | 26 | keep |
| `backend/tests/integration/test_annotation_enrichment.py` | pytest Weaviate | 7 | keep |
| `backend/tests/integration/test_annotation_export.py` | pytest Weaviate | 2 | keep |
| `backend/tests/integration/test_annotation_provenance.py` | pytest Weaviate | 5 | keep |
| `backend/tests/integration/test_annotation_proximity.py` | pytest Weaviate | 5 | keep |
| `backend/tests/integration/test_annotation_ranking.py` | pytest Weaviate | 9 | keep |
| `backend/tests/integration/test_annotation_sorting.py` | pytest Weaviate | 6 | keep |
| `backend/tests/integration/test_annotations.py` | pytest Weaviate | 17 | keep |
| `backend/tests/integration/test_classification_provenance_schema.py` | pytest Weaviate | 3 | keep |
| `backend/tests/test_annotation_collation.py` | pytest fast | 13 | keep |
| `backend/tests/test_annotation_concordance.py` | pytest fast | 70 | keep |
| `backend/tests/test_annotation_derivation.py` | pytest fast | 27 | keep |
| `backend/tests/test_annotation_enrichment.py` | pytest fast | 38 | keep |
| `backend/tests/test_annotation_export.py` | pytest fast | 41 | keep |
| `backend/tests/test_annotation_facets.py` | pytest fast | 21 | keep |
| `backend/tests/test_annotation_proximity.py` | pytest fast | 23 | keep |
| `backend/tests/test_annotation_ranking.py` | pytest fast | 27 | keep |
| `backend/tests/test_annotation_service.py` | pytest fast | 131 | keep |
| `backend/tests/test_annotation_source.py` | pytest fast | 11 | keep |
| `backend/tests/test_attribute_scope_schema.py` | pytest fast | 16 | keep |
| `backend/tests/test_attributes.py` | pytest fast | 50 | keep |
| `backend/tests/test_classification_provenance.py` | pytest fast | 7 | keep |
| `backend/tests/test_span_offsets.py` | pytest fast | 30 | keep |
| `frontend/test/unit/annotationExport.spec.ts` | Vitest | 9 | keep |
| `frontend/test/unit/annotationPopover.spec.ts` | Vitest | 5 | keep |
| `frontend/test/unit/annotationStatistics.spec.ts` | Vitest | 14 | keep |
| `frontend/test/unit/annotationStatisticsView.spec.ts` | Vitest | 3 | keep |
| `frontend/test/unit/annotations.spec.ts` | Vitest | 8 | keep |
| `frontend/test/unit/attributeAssignment.spec.ts` | Vitest | 31 | keep |
| `frontend/test/unit/attributeDialogs.spec.ts` | Vitest | 24 | keep |
| `frontend/test/unit/attributes.spec.ts` | Vitest | 17 | keep |
| `frontend/test/unit/boundaryEdit.spec.ts` | Vitest | 6 | keep |
| `frontend/test/unit/bulkResolve.spec.ts` | Vitest | 5 | keep |
| `frontend/test/unit/cellFilters.spec.ts` | Vitest | 9 | keep |
| `frontend/test/unit/concordance.spec.ts` | Vitest | 36 | keep |
| `frontend/test/unit/concordanceFacets.spec.ts` | Vitest | 9 | keep |
| `frontend/test/unit/concordanceProximity.spec.ts` | Vitest | 11 | keep |
| `frontend/test/unit/concordanceQuery.spec.ts` | Vitest | 17 | keep |
| `frontend/test/unit/concordanceRanking.spec.ts` | Vitest | 15 | keep |
| `frontend/test/unit/concordanceTable.spec.ts` | Vitest | 24 | keep |
| `frontend/test/unit/editConflicts.spec.ts` | Vitest | 6 | keep |
| `frontend/test/unit/provenanceSummary.spec.ts` | Vitest | 3 | keep |
| `frontend/test/unit/spanLanes.spec.ts` | Vitest | 4 | keep |
| `frontend/test/unit/spanOffsets.spec.ts` | Vitest | 18 | keep |
| `frontend/test/unit/tagFocus.spec.ts` | Vitest | 4 | keep |
| `frontend/test/unit/tagSearch.spec.ts` | Vitest | 4 | keep |
| `frontend/test/unit/tagsDialog.spec.ts` | Vitest | 13 | keep |
| `frontend/test/unit/writeOutcome.spec.ts` | Vitest | 9 | keep |

### #851

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_chunk_have_vector.py` | pytest Weaviate | 3 | keep |
| `backend/tests/integration/test_collection_analytics.py` | pytest Weaviate | 9 | keep |
| `backend/tests/integration/test_collection_passages.py` | pytest Weaviate | 9 | keep |
| `backend/tests/integration/test_corpus_analytics.py` | pytest Weaviate | 23 | keep |
| `backend/tests/integration/test_document_search.py` | pytest Weaviate | 10 | keep |
| `backend/tests/integration/test_mcp.py` | pytest Weaviate | 19 | keep (disputed with #853) |
| `backend/tests/integration/test_ranked_result_analytics.py` | pytest Weaviate | 8 | keep |
| `backend/tests/integration/test_search.py` | pytest Weaviate | 81 | keep |
| `backend/tests/integration/test_search_criteria.py` | pytest Weaviate | 36 | keep |
| `backend/tests/test_candidates.py` | pytest fast | 5 | keep |
| `backend/tests/test_corpus_analytics.py` | pytest fast | 94 | keep |
| `backend/tests/test_mcp.py` | pytest fast | 61 | keep (disputed with #853) |
| `backend/tests/test_search_classifications.py` | pytest fast | 5 | keep |
| `backend/tests/test_search_criteria.py` | pytest fast | 32 | keep |
| `backend/tests/test_search_service.py` | pytest fast | 90 | keep |
| `backend/tests/test_search_vectors.py` | pytest fast | 29 | keep |
| `frontend/test/unit/collectionStats.spec.ts` | Vitest | 18 | keep |
| `frontend/test/unit/corpusOverview.spec.ts` | Vitest | 44 | keep |
| `frontend/test/unit/corpusTimeline.spec.ts` | Vitest | 11 | keep |
| `frontend/test/unit/exploreDocuments.spec.ts` | Vitest | 7 | keep |
| `frontend/test/unit/exploreHandoff.spec.ts` | Vitest | 9 | keep |
| `frontend/test/unit/exploreRankedCharts.spec.ts` | Vitest | 9 | keep |
| `frontend/test/unit/exploreResults.spec.ts` | Vitest | 19 | keep |
| `frontend/test/unit/exploreVisualizations.spec.ts` | Vitest | 20 | keep |
| `frontend/test/unit/resultClassifications.spec.ts` | Vitest | 8 | keep |
| `frontend/test/unit/searchHistory.spec.ts` | Vitest | 42 | keep |
| `frontend/test/unit/searchResultCard.spec.ts` | Vitest | 11 | keep |
| `frontend/test/unit/serverQueries.spec.ts` | Vitest | 9 | keep |

### #852

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_chunk_document_public.py` | pytest Weaviate | 7 | keep |
| `backend/tests/integration/test_chunk_ingest.py` | pytest Weaviate | 40 | **simplify fixture** (#860) |
| `backend/tests/integration/test_chunk_positions.py` | pytest Weaviate | 6 | keep |
| `backend/tests/integration/test_chunk_year.py` | pytest Weaviate | 4 | keep |
| `backend/tests/integration/test_collection_export.py` | pytest Weaviate | 3 | keep |
| `backend/tests/integration/test_page_import.py` | pytest Weaviate | 1 | keep |
| `backend/tests/integration/test_page_layout_anchors.py` | pytest Weaviate | 4 | keep |
| `backend/tests/integration/test_page_order.py` | pytest Weaviate | 3 | keep |
| `backend/tests/integration/test_text_upload.py` | pytest Weaviate | 3 | keep |
| `backend/tests/test_chunk_ingest.py` | pytest fast | 66 | keep |
| `backend/tests/test_chunk_positions.py` | pytest fast | 10 | keep |
| `backend/tests/test_chunk_year.py` | pytest fast | 21 | keep |
| `backend/tests/test_collection_export.py` | pytest fast | 7 | keep |
| `backend/tests/test_document_service.py` | pytest fast | 60 | keep |
| `backend/tests/test_page_assets.py` | pytest fast | 45 | keep |
| `backend/tests/test_page_import.py` | pytest fast | 24 | keep |
| `backend/tests/test_page_layout.py` | pytest fast | 72 | keep |
| `backend/tests/test_page_order.py` | pytest fast | 34 | keep |
| `backend/tests/test_real_pages.py` | pytest fast | 10 | keep |
| `backend/tests/test_scan_profile.py` | pytest fast | 24 | keep |
| `backend/tests/test_synthetic_documents.py` | pytest fast | 7 | keep |
| `backend/tests/test_text_upload.py` | pytest fast | 84 | keep |
| `backend/tests/test_text_upload_route.py` | pytest fast | 12 | **simplify fixture** (`openapi_schema`) |
| `frontend/test/unit/chunkContext.spec.ts` | Vitest | 43 | keep |
| `frontend/test/unit/chunkWindow.spec.ts` | Vitest | 6 | keep |
| `frontend/test/unit/documentImagePane.spec.ts` | Vitest | 13 | keep |
| `frontend/test/unit/documentRemoval.spec.ts` | Vitest | 17 | keep |
| `frontend/test/unit/documentText.spec.ts` | Vitest | 3 | keep |
| `frontend/test/unit/documentTextPane.spec.ts` | Vitest | 11 | keep |
| `frontend/test/unit/documentWorkspace.spec.ts` | Vitest | 8 | keep |
| `frontend/test/unit/documentWorkspaceLayout.spec.ts` | Vitest | 10 | keep |
| `frontend/test/unit/layoutMap.spec.ts` | Vitest | 15 | keep (disputed with #855) |
| `frontend/test/unit/longPassage.spec.ts` | Vitest | 3 | keep |
| `frontend/test/unit/originalSource.spec.ts` | Vitest | 27 | keep |
| `frontend/test/unit/readerCitation.spec.ts` | Vitest | 1 | keep |
| `frontend/test/unit/readerOffsets.spec.ts` | Vitest | 17 | keep |
| `frontend/test/unit/readerScanGaps.spec.ts` | Vitest | 4 | keep |
| `frontend/test/unit/realPages.spec.ts` | Vitest | 7 | keep |
| `frontend/test/unit/scanGeometry.spec.ts` | Vitest | 25 | keep |
| `frontend/test/unit/textScanSync.spec.ts` | Vitest | 17 | keep |
| `frontend/test/unit/textSimilarity.spec.ts` | Vitest | 5 | keep |
| `frontend/test/unit/textUpload.spec.ts` | Vitest | 11 | keep |

### #853

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_chunk_summaries.py` | pytest Weaviate | 14 | keep (closes its report file) |
| `backend/tests/integration/test_chunk_titles.py` | pytest Weaviate | 9 | keep |
| `backend/tests/integration/test_classifier_tool.py` | pytest Weaviate | 30 | keep |
| `backend/tests/integration/test_embedder_tool.py` | pytest Weaviate | 16 | **simplify fixture** (#862) |
| `backend/tests/integration/test_span_chat.py` | pytest Weaviate | 5 | keep |
| `backend/tests/integration/test_suggestions.py` | pytest Weaviate | 5 | keep |
| `backend/tests/test_ai_suggestion_dates.py` | pytest fast | 2 | keep |
| `backend/tests/test_chat/test_document_chat.py` | pytest fast | 18 | keep |
| `backend/tests/test_chat/test_search_chat.py` | pytest fast | 13 | keep |
| `backend/tests/test_chunk_summaries.py` | pytest fast | 13 | keep |
| `backend/tests/test_chunk_titles.py` | pytest fast | 61 | keep |
| `backend/tests/test_classifier_cli.py` | pytest fast | 35 | keep |
| `backend/tests/test_embedder_cli.py` | pytest fast | 11 | keep |
| `backend/tests/test_fake_providers.py` | pytest fast | 7 | keep (asserts `retry-after-ms`) |
| `backend/tests/test_llm/test_features.py` | pytest fast | 38 | keep |
| `backend/tests/test_llm/test_gateway.py` | pytest fast | 71 | keep (no retry backoff, via the fake) |
| `backend/tests/test_llm/test_rag_sources.py` | pytest fast | 8 | keep |
| `backend/tests/test_rag_routes.py` | pytest fast | 10 | keep |
| `backend/tests/test_span_chat.py` | pytest fast | 17 | keep |
| `backend/tests/test_suggestions.py` | pytest fast | 47 | keep |
| `backend/tests/test_summarization/test_document_service.py` | pytest fast | 10 | keep |
| `backend/tests/test_summarization/test_lengths.py` | pytest fast | 19 | keep |
| `backend/tests/test_summarization/test_service.py` | pytest fast | 9 | keep |
| `backend/tests/test_summarization/test_templated.py` | pytest fast | 3 | keep |
| `backend/tests/test_topicer_client.py` | pytest fast | 29 | keep |
| `backend/tests/test_utils/test_template.py` | pytest fast | 2 | keep |
| `frontend/test/unit/aiAssistance.spec.ts` | Vitest | 16 | keep |
| `frontend/test/unit/aiRunConfirmation.spec.ts` | Vitest | 10 | keep |
| `frontend/test/unit/aiSuggestionPresentation.spec.ts` | Vitest | 8 | keep |
| `frontend/test/unit/chatSources.spec.ts` | Vitest | 17 | keep |
| `frontend/test/unit/chatStorage.spec.ts` | Vitest | 11 | keep |
| `frontend/test/unit/citationTokens.spec.ts` | Vitest | 3 | keep |
| `frontend/test/unit/documentViewAiCleanup.spec.ts` | Vitest | 3 | keep |
| `frontend/test/unit/ragExplain.spec.ts` | Vitest | 3 | keep (disputed with #851) |
| `frontend/test/unit/scopedChat.spec.ts` | Vitest | 24 | keep |
| `frontend/test/unit/spanDiscussion.spec.ts` | Vitest | 4 | keep |
| `frontend/test/unit/tagSuggestion.spec.ts` | Vitest | 13 | keep |
| `frontend/test/unit/topicerModelStore.spec.ts` | Vitest | 7 | keep |

### #854

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_annotation_migration.py` | pytest Weaviate | 10 | pending |
| `backend/tests/integration/test_annotation_tenants.py` | pytest Weaviate | 16 | pending (disputed with #850) |
| `backend/tests/integration/test_api_store.py` | pytest Weaviate | 7 | pending |
| `backend/tests/integration/test_db_benchmark.py` | pytest Weaviate | 1 | pending (disputed with #858) |
| `backend/tests/integration/test_document_cleanup.py` | pytest Weaviate | 2 | pending |
| `backend/tests/integration/test_local_dev_documents.py` | pytest Weaviate | 3 | pending |
| `backend/tests/integration/test_metadata_sync.py` | pytest Weaviate | 3 | pending (disputed with #852) |
| `backend/tests/integration/test_partial_writes.py` | pytest Weaviate | 12 | pending |
| `backend/tests/integration/test_repositories.py` | pytest Weaviate | 43 | pending |
| `backend/tests/integration/test_repository_routes.py` | pytest Weaviate | 22 | pending |
| `backend/tests/integration/test_store_ownership.py` | pytest Weaviate | 15 | pending (disputed with #849) |
| `backend/tests/integration/test_user_collections_store.py` | pytest Weaviate | 11 | pending |
| `backend/tests/integration/test_weaviate_backup.py` | pytest Weaviate | 2 | pending |
| `backend/tests/test_annotation_migration.py` | pytest fast | 33 | pending |
| `backend/tests/test_db_benchmark.py` | pytest fast | 59 | pending (disputed with #858) |
| `backend/tests/test_document_cleanup.py` | pytest fast | 15 | pending |
| `backend/tests/test_metadata_sync.py` | pytest fast | 146 | pending (disputed with #852) |
| `backend/tests/test_weaviate_backup_script.py` | pytest fast | 29 | pending (disputed with #857) |
| `backend/tests/test_weaviate_store.py` | pytest fast | 11 | pending |
| `backend/tests/test_write_outcomes.py` | pytest fast | 12 | pending |

### #855

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `frontend/test/unit/MiniStateButton.spec.ts` | Vitest | 6 | pending |
| `frontend/test/unit/authNavigation.spec.ts` | Vitest | 18 | pending (disputed with #849) |
| `frontend/test/unit/contextScopedStores.spec.ts` | Vitest | 22 | pending |
| `frontend/test/unit/documentPanels.spec.ts` | Vitest | 2 | pending (disputed with #852) |
| `frontend/test/unit/leftoverTimers.spec.ts` | Vitest | 1 | pending |
| `frontend/test/unit/rightSidebar.spec.ts` | Vitest | 10 | pending |
| `frontend/test/unit/routes.spec.ts` | Vitest | 20 | pending |
| `frontend/test/unit/selectionBar.spec.ts` | Vitest | 9 | pending (disputed with #851) |
| `frontend/test/unit/sessionRestore.spec.ts` | Vitest | 27 | pending |
| `frontend/test/unit/sessionTeardown.spec.ts` | Vitest | 24 | pending |
| `frontend/test/unit/timerTracking.spec.ts` | Vitest | 5 | pending |
| `frontend/test/unit/transport.spec.ts` | Vitest | 7 | pending |
| `frontend/test/unit/usePagination.spec.ts` | Vitest | 4 | pending (disputed with #851) |
| `frontend/test/unit/useTagEditing.spec.ts` | Vitest | 3 | pending |
| `frontend/test/unit/wrappingBadges.spec.ts` | Vitest | 2 | pending |

### #856

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `frontend/test/capture/views.spec.ts` | Playwright capture | 33 | pending |
| `frontend/test/e2e/aiSuggestionNavigation.spec.ts` | Playwright | 1 | pending |
| `frontend/test/e2e/aiSuggestions.spec.ts` | Playwright | 10 | pending |
| `frontend/test/e2e/aiTagNavigationVisibility.spec.ts` | Playwright | 1 | pending |
| `frontend/test/e2e/annotationAttributes.spec.ts` | Playwright | 8 | pending |
| `frontend/test/e2e/annotationWorkspace.spec.ts` | Playwright | 39 | pending |
| `frontend/test/e2e/attributes.spec.ts` | Playwright | 11 | pending |
| `frontend/test/e2e/chatSources.spec.ts` | Playwright | 9 | pending |
| `frontend/test/e2e/collectionCharts.spec.ts` | Playwright | 7 | pending |
| `frontend/test/e2e/collections.spec.ts` | Playwright | 9 | pending |
| `frontend/test/e2e/corpusOverview.spec.ts` | Playwright | 6 | pending |
| `frontend/test/e2e/documentChat.spec.ts` | Playwright | 5 | pending |
| `frontend/test/e2e/documentRights.spec.ts` | Playwright | 6 | pending |
| `frontend/test/e2e/documentSummary.spec.ts` | Playwright | 10 | pending |
| `frontend/test/e2e/documentViewer.spec.ts` | Playwright | 32 | pending |
| `frontend/test/e2e/documentWorkspace.spec.ts` | Playwright | 21 | pending |
| `frontend/test/e2e/navigation.spec.ts` | Playwright | 12 | pending |
| `frontend/test/e2e/originalSource.spec.ts` | Playwright | 4 | pending |
| `frontend/test/e2e/permissions.spec.ts` | Playwright | 4 | pending |
| `frontend/test/e2e/quota.spec.ts` | Playwright | 4 | pending |
| `frontend/test/e2e/realScans.spec.ts` | Playwright | 3 | pending |
| `frontend/test/e2e/scanViewer.spec.ts` | Playwright | 7 | pending |
| `frontend/test/e2e/searchChat.spec.ts` | Playwright | 2 | pending |
| `frontend/test/e2e/searchClassifications.spec.ts` | Playwright | 1 | pending |
| `frontend/test/e2e/searchContext.spec.ts` | Playwright | 5 | pending |
| `frontend/test/e2e/searchExplore.spec.ts` | Playwright | 14 | pending |
| `frontend/test/e2e/searchHistory.spec.ts` | Playwright | 10 | pending |
| `frontend/test/e2e/searchResultCards.spec.ts` | Playwright | 6 | pending |
| `frontend/test/e2e/searchVectors.spec.ts` | Playwright | 3 | pending |
| `frontend/test/e2e/searchVisualizations.spec.ts` | Playwright | 13 | pending |
| `frontend/test/e2e/sessionRestore.spec.ts` | Playwright | 6 | pending |
| `frontend/test/e2e/sessionTeardown.spec.ts` | Playwright | 7 | pending |
| `frontend/test/e2e/sidebar.spec.ts` | Playwright | 4 | pending |
| `frontend/test/e2e/smoke.spec.ts` | Playwright | 7 | pending |
| `frontend/test/e2e/supportHelpers.spec.ts` | Playwright | 5 | pending |
| `frontend/test/e2e/textUpload.spec.ts` | Playwright | 6 | pending |

### #857

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/test_api_contracts.py` | pytest fast | 72 | pending |
| `backend/tests/test_browser_shards.py` | pytest fast | 12 | pending |
| `backend/tests/test_ci_changes.py` | pytest fast | 156 | pending |
| `backend/tests/test_config.py` | pytest fast | 19 | pending |
| `backend/tests/test_dependency_locks.py` | pytest fast | 17 | pending |
| `backend/tests/test_deploy_commit.py` | pytest fast | 6 | pending |
| `backend/tests/test_deploy_feedback_storage.py` | pytest fast | 7 | pending |
| `backend/tests/test_deploy_gating.py` | pytest fast | 3 | pending |
| `backend/tests/test_deploy_image.py` | pytest fast | 1 | pending |
| `backend/tests/test_deploy_mcp_rate_limit.py` | pytest fast | 4 | pending |
| `backend/tests/test_deploy_page_assets.py` | pytest fast | 2 | pending |
| `backend/tests/test_deploy_search_vectors.py` | pytest fast | 6 | pending |
| `backend/tests/test_deploy_sqlite_storage.py` | pytest fast | 5 | pending |
| `backend/tests/test_docker_preflight.py` | pytest fast | 29 | pending |
| `backend/tests/test_e2e_dev_script.py` | pytest fast | 17 | pending |
| `backend/tests/test_integration_shards.py` | pytest fast | 13 | pending |
| `backend/tests/test_local_dev.py` | pytest fast | 60 | pending |
| `backend/tests/test_local_dev_script.py` | pytest fast | 26 | pending |
| `backend/tests/test_makefile_args.py` | pytest fast | 4 | pending |
| `backend/tests/test_offline_guard.py` | pytest fast | 3 | pending |
| `backend/tests/test_python_deps_check.py` | pytest fast | 7 | pending |
| `backend/tests/test_utils/test_observability.py` | pytest fast | 18 | pending |
| `frontend/test/unit/dependencyCheck.spec.ts` | Vitest | 4 | pending (disputed with #855) |
| `frontend/test/unit/devTooling.spec.ts` | Vitest | 8 | pending (disputed with #855) |

### #858

| File | Layer | Cases | Decision |
| --- | --- | ---: | --- |
| `backend/tests/integration/test_annotation_facets_benchmark.py` | pytest benchmark | 2 | pending |
| `backend/tests/integration/test_annotation_sort_benchmark.py` | pytest benchmark | 1 | pending |
| `backend/tests/integration/test_annotation_tenant_rehearsal.py` | pytest benchmark | 1 | pending |
| `backend/tests/integration/test_chunk_position_benchmark.py` | pytest benchmark | 1 | pending |
| `backend/tests/integration/test_chunk_summary_benchmark.py` | pytest benchmark | 1 | pending |
| `backend/tests/integration/test_document_search_benchmark.py` | pytest benchmark | 1 | pending |


## Stage outcomes

### #848 Inventory, shared fixtures, fakes and harness

Measured on one developer machine (Linux, `tmp_path` on a disk, not tmpfs), the same
commands before and after, nothing else running: `pytest -q -m "not integration and not
live and not benchmark" --durations=0` from `semant_demo_backend/`, and
`SEMANT_FIXTURE_PROFILE=… make test-integration ARGS="--durations=0"`.

| Suite | Cases | Before | After |
| --- | ---: | --- | --- |
| Backend fast | 2,830 | 219.8 s (setup 63.9 s, call 147.6 s) | 128.5 s (setup 23.9 s, call 97.1 s) |
| Backend real Weaviate | 643 | 414.7 s (setup 206.1 s, call 188.0 s) | 374.3 s (setup 202.7 s, call 151.7 s) |
| Frontend unit | 1,091 | 30.4 s wall (`npx vitest run`) | unchanged (no frontend change) |

Where the fast suite's time went: no single test dominates (the slowest takes 6 s). The
repeated work was in the shared fixtures, in three places:

1. **Test apps waited for the disk.** Starting a test app (`create_app` and its lifespan,
   which creates the SQLite schema) took ~0.16 s, ~0.03 s on tmpfs: SQLite's `fsync`.
   Every fast test with an app, and every real-store test (`api_app`), paid it. Fixed:
   `tests/conftest.py` sets `PRAGMA synchronous=OFF` on SQLAlchemy's SQLite connections in
   test processes. Transactions, locking and isolation are unchanged, so the quota-ledger
   race tests keep their meaning; only durability after a power loss, which no throwaway
   test database needs, is gone. Tests marked `sqlite_durable` keep SQLite's own setting:
   the rollback-journal recovery tests in `test_deploy_sqlite_storage.py` (#406) assert it.
2. **Passwords were hashed at the production cost.** 189 Argon2id hashes and verifications
   (registration, login, corpus users) took 16.4 s. Fixed: Argon2id with its minimum
   parameters in test processes. The same fastapi-users code hashes and verifies; no
   behavior test asserts the cost. The patch replaces a name inside fastapi-users, so
   `test_harness_defaults.py` checks the parameters of an actual hash and fails if an
   upgrade restores the defaults. `tests.e2e_server` and the development stack run as their own
   processes and keep the defaults.
3. **The OpenAPI schema was generated again by 15 tests** (0.75 s each). Fixed: the
   `openapi_schema` fixture generates the default-settings schema once per run and gives
   each test a deep copy (no shared mutable state). `test_app/test_bootstrap.py` and
   `test_mcp.py` still generate their own, because they compare schemas of differently
   configured apps.

Decisions for the harness (all **keep** unless stated):

| Path | Decision and evidence |
| --- | --- |
| `tests/conftest.py` | **simplify fixture** (above). The network guard stays function-scoped; it costs nothing measurable. |
| `app_support.py`, `auth_support.py`, `mcp_support.py` | Keep. Offline settings with `.invalid` hosts; small helpers with 11–20 importers each. |
| `corpus.py`, `seed.py`, `fixtures/corpus.json`, `CORPUS.md`, `text_offsets.json` | Keep. 7 KB corpus validated on load and cached; the single source for real-store, browser and Vitest tests. No unused helpers. |
| `fakes.py`, `fake_providers.py`, `chunk_fakes.py` | Keep. Fake drift is caught by `test_fake_providers.py` (#853), which drives the real clients against the fakes. |
| `page_fixtures.py`, `real_pages.py`, `fixtures/real_pages/` (1.1 MB) | Keep. Drift tests `test_page_fixtures.py` (this stage) and `test_real_pages.py` (#852); its 2.7 s setup is rendering the synthetic scans once. |
| `synthetic_documents.py`, `local_dev.py` | Keep; development tooling that lives with the tests (tests: #852, #857). |
| `fixture_profile.py` | Keep. Opt-in, a no-op without `SEMANT_FIXTURE_PROFILE`. |
| `weaviate_store.py`, `integration/conftest.py` | Keep. Per-test reset and seed were optimized and profiled in #686 (#695); not reopened. Per-test isolation is required by the testing contract. |
| `e2e_server.py`, `test/e2e/{support,viewports,longDocument}.ts`, `test/fixtures/longPassage.ts` | Keep; browser stage #856 owns the specs. |
| `test/unit/{setup,console}.ts`, `test/unit/environment/` | Keep. The custom jsdom environment ends a file's leftover timers (#551), covered by `leftoverTimers` / `timerTracking` (#855). |
| `pyproject.toml`, `vitest.config.ts`, `playwright.config.ts` | Keep. `--strict-markers` and fail-not-skip store errors stay; Playwright's one worker belongs to #815. |
| `test_app/test_bootstrap.py`, `test_page_fixtures.py` | Keep; app construction without services, settings isolation and fixture drift. |

Not changed, for other stages: the `live` marker is declared but unused (#858);
`test_mcp.py` (17.5 s) and `test_quota/test_ai_routes.py` (13.2 s after this change) are the
most expensive fast files (#851, #849); `test_integration_shards.py` takes 6.3 s in one
test (#857). Real-store setup is still ~0.3 s per test, mostly the per-test Weaviate reset
(56 s in all, 38 s of it 29 schema recreations after tests that change the schema),
client connection (29 s) and seeding (17 s) (#854, after #686). Vitest has no costly
shared setup; its slowest file is `devTooling.spec.ts` (6.7 s, #857).

### #849 Authentication, access, rights and quotas

**Keep everything; no change.** Same machine and commands as #848. Fast backend, 296 cases:
61.1 s before #848's fixture changes, 25.5 s after. Real Weaviate, 58 cases: 32.1 s before,
26.2 s after. Vitest, 64 cases: 2.9 s. Each layer catches a different regression:

- `test_user_collection_access.py` pins the rule table.
- `test_user_collection_service.py` proves every service entry point applies it before any
  repository call or user lookup.
- `integration/test_access.py` and `integration/test_document_rights.py` prove the HTTP
  wiring, the real store filters and the stored state after each denial.
- The quota files cover separate layers: the SQL ledger, gateway operations, Topicer
  settlement, AI route admission and the guest cookie.
- The Vitest specs pin UI rights and labels; the browser specs (#856) pin the rendered
  controls.

The costly remaining test, the ledger race (2.6 s), needs real SQLite lock contention.
The full note is [on #849](https://github.com/DCGM/semant-demo/issues/849).

### #850 Annotations, attributes, concordance and provenance

**Keep everything; no change.** Fast backend, 505 cases: 14.8 s before #848's fixture
changes, 5.7 s after. Real Weaviate, 89 cases: 34.1 s before, 29.4 s after. Vitest, 304
cases: 15.7 s.

- The fast files prove service rules with fakes.
- Their real-store counterparts, which already cross-reference them in their docstrings,
  prove what fakes cannot: sort keys, filter rendering, facet totals, Unicode text as stored
  and tenant reads.
- The per-file fakes differ by scenario and stay local.
- No skips or fixed waits. `attributeDialogs.spec.ts` (4 s) is Quasar dialog mounting
  with fake-timer transitions.

The full note is [on #850](https://github.com/DCGM/semant-demo/issues/850).

### #851 Search, Explore, classifications and analytics

**Keep everything; no change.** Measured after #848's fixture changes, on the same machine
and with the same commands as #848:

| Layer | Files | Cases | Time |
| --- | ---: | ---: | --- |
| Fast backend | 7 | 316 | 30.4 s (setup 6.0 s) |
| Real Weaviate | 9 | 198 | 83.7 s (setup 46.6 s) |
| Vitest | 12 | 207 | 9.3 s (sum of file times) |

`test_mcp.py` (17.2 s) and `test_corpus_analytics.py` (11.6 s) take nearly all of the fast
time. Their tests are not slow; each starts its own application. A fresh test app costs
~0.35 s: ~0.15–0.2 s of lifespan, then ~0.15 s on its first request, when FastAPI 0.142
builds the routes' dependency state (later requests take <1 ms). Sharing one app per
module would save ~15 s in `test_mcp.py`. ADR 0005 asks for fresh application instances
per test, and the corpus-analytics HTTP tests check per-app caches, so this stays (#847).

- **Service vs real store:** **keep both layers.** The fast files cover
  - normalization and validation of the shared criteria,
  - the Weaviate filters they become,
  - the cache rules,
  - the MCP tool projections and bounds.

  The real-store files cover
  - the store's matching,
  - aggregation totals,
  - legacy stores read through aliases,
  - parity of MCP with the Search page.

  Each fast docstring names its real-store counterpart.
- **Route validation in `integration/test_search_criteria.py`:** **keep.** This means
  `test_invalid_search_criteria_are_rejected` and `test_browse_rejects_invalid_document_filters`,
  8 cases taking 2.6 s. Moving them to the fast layer would add a fresh app for each of
  them, so ~2.6 s would move into the suite that runs most often.
- **Parameterized tables:** **keep.** `test_search_service.py` (90 cases, 0.5 s) and
  `test_search_vectors.py` (29) cost milliseconds.
- **Waits:**
  - `test_mcp.py::test_tool_calls_time_out` sleeps in the fake service, under a short
    configured timeout (0.4 s).
  - The Vitest `flush()` helpers are zero-delay.
- **Skips:** none.

`test_mcp.py` (fast and integration) stays here, still disputed with #853. The full note is
[on #851](https://github.com/DCGM/semant-demo/issues/851).

### #852 Documents, chunks, import/export, pages, scans and text

**One fixture simplified ([#860](https://github.com/DCGM/semant-demo/pull/860)); keep the
rest.**

| Layer | Files | Cases | Time |
| --- | ---: | ---: | --- |
| Fast backend | 14 | 476 | 18.3 s |
| Real Weaviate | 9 | 71 | 96.8 s; ~41 s with #860 (only `test_chunk_ingest.py` changes) |
| Vitest | 19 | 243 | 4.2 s (sum of file times) |

- **`integration/test_chunk_ingest.py`:** **simplify fixture** (#860).
  - Before: `ingest_store` dropped and created three collections and two aliases for each
    of the 40 tests, taking 64.8 s.
  - After: it empties and reseeds them, recreating them only when their configuration
    changed, as `reset_app_collections` does (#686). It takes 15.8 s, measured on the same
    `origin/main` base with call time unchanged.
  - The collections are dropped once after the module.
  - The module passes in normal and reversed order.
  - With the reset disabled, 39 of the 40 tests error.
- **`test_text_upload_route.py::test_the_operation_declares_the_multipart_body`:**
  **simplify fixture.** It reads the shared `openapi_schema` instead of `/openapi.json` of
  its own app (0.9 s), the 16th test to do so.
- **Mapping vs persistence:** **keep.** The fast files cover
  - chunk positions and ingest validation,
  - page order, layout anchoring and page import,
  - text chunking,
  - upload limits.

  The real-store files cover what is stored and read back:
  - positions,
  - public flags,
  - export,
  - page order,
  - layout anchors read without the property,
  - failed uploads never shown.
- **`test_page_layout.py::test_bit_parallel_edit_distance_agrees_with_dynamic_programming`:**
  **keep.** It takes 5 × 0.8 s. It is a randomized property check against a plain dynamic
  programming oracle; fewer cases or a faster oracle would weaken it.
- **`integration/test_text_upload.py::test_a_failed_upload_is_reported_and_never_shown`:**
  **keep.** It takes 3.2 s, all of it the production retry backoff (1 s + 2 s). The route
  reads the module-level `text_upload.DEFAULT_LIMITS`, so removing the wait needs either a
  patched global or a limits dependency; that is a follow-up (#847).
- **Vitest:** **keep.**
  - The `textScanSync` and `chunkContext` waits are zero-delay flushes.
  - `scanGeometry` delays one layout by 5 ms on purpose, to resolve out of order.
- **Skips:** none.

The full note is [on #852](https://github.com/DCGM/semant-demo/issues/852).

### #853 LLM, RAG, chat, streaming, summaries and suggestions

**Two waits removed ([#862](https://github.com/DCGM/semant-demo/pull/862)); keep the rest.**
Same machine and commands as #848:

| Layer | Files | Cases | Before | After |
| --- | ---: | ---: | --- | --- |
| Fast backend | 20 | 423 | 9.2 s | 8.3 s |
| Real Weaviate | 6 | 80 | 128.0 s | 67.3 s (63.1 s reversed) |
| Vitest | 12 | 119 | 2.7 s (sum of file times) | unchanged (no frontend change) |

- **`integration/test_embedder_tool.py::test_an_unreachable_grpc_port_stops_a_run_before_it_creates_the_vector`:**
  **simplify fixture.** It took 63.3 s: the Weaviate client retries an unavailable gRPC
  query six times and sleeps 1 + 2 + 4 + 8 + 16 + 32 s in between (`weaviate.retry`, not
  configurable). The test now replaces that sleep and asserts the six backoff steps, so the
  retries still happen. The file takes 12 s again, as `shard_durations.json` assumes; the
  test came with #798 on 21 November, after that file was measured.
- **The fake providers' 501 for unfaked routes:** it now sends `retry-after-ms: 1`. The
  OpenAI client still retries it once, without its random backoff of up to a second
  (`test_gateway.py`, two tests, and `test_quota/test_operations.py`, #849).
  `test_fake_providers.py` asserts the header. The fakes are stage 1's; the browser server
  and the development stack use them too, where a failing unfaked call also ends sooner.
- **`integration/test_chunk_summaries.py`:** keep; one test closes the report file it read
  (a `ResourceWarning`). Its setup (~1.9 s per test) is the per-test schema recreation after
  the summary properties were added; Weaviate cannot drop a property, so this stays (#854
  measures the reset).
- **Gateway, features and RAG (`test_llm/**`, `test_rag_routes.py`):** **keep.**
  - `test_gateway.py` covers tier policy, provider wiring and usage, cost and cancellation
    metering per provider.
  - `test_features.py` runs every RAG pipeline, the question endpoint and search summaries
    through the real gateway against the HTTP fakes.
  - `test_rag_sources.py` covers citation numbering across agent searches.
  - `test_rag_routes.py` covers configuration loading, feedback and content-free logs.
- **Chat and summaries (`test_chat/**`, `test_summarization/**`):** **keep.** The chat fake
  (`FakeLlm` in `test_document_chat.py`, also used by `test_search_chat.py`) streams through
  a feature catalog; `tests/fakes.py`'s `FakeLlm` and `FakeStreamingChat` serve other
  interfaces, so they are not duplicates. `test_templated.py` pins the message and option
  mapping with its own prompts, `test_lengths.py` the bundled length levels.
- **Span chat and suggestions:** **keep both layers.** The fast files cover access before
  any read, history limits, UTF-16 offsets, failures mid-stream and cancellation
  (`test_suggestions.py`: closing the stream, consumer cancellation, a write finished
  before cancelling). The real-store files cover reloading through the span API, offsets
  as stored and a disconnect on a real server.
- **Offline tools (`test_chunk_titles.py`, `test_chunk_summaries.py`, `test_classifier_cli.py`,
  `test_embedder_cli.py` and their integration files):** **keep.** The fast files cover
  CLI refusals, endpoint confirmation, planning and exit codes; the integration files cover
  the runs, resumption and the guarded test collections against the store.
- **`test_topicer_client.py`, `test_ai_suggestion_dates.py`, `test_utils/test_template.py`:**
  **keep.** They cost milliseconds; the Topicer tests pin content-free errors and usage.
- **Waits:** the 0.2 s pacing in `test_fake_providers.py` is what it tests (the browser
  tests rely on it); `test_chunk_titles.py` already removes its backoff; the Vitest
  `flush()` helpers are zero-delay.
- **Skips:** none.

Ownership: `test_mcp.py` stays with #851 and the quota files with #849, as the owner map
says; the tool files above (titles, summaries, classifier, embedder, Topicer), which the
issue text does not name, are this stage's by the owner map.

Remaining risks:

- `integration/test_embedder_tool.py::test_a_filled_vector_keeps_the_chunk_data_and_is_searchable`
  failed once in 33 runs (18 of its file, 15 alone), in the first run after the change, though
  it runs before the changed test. The trace was not kept.
- A reversed run once warned that a garbage-collected aiosqlite connection was not
  returned, after `integration/test_suggestions.py`'s disconnect test.
- A wrong `weaviate_grpc_port` makes the embedder wait the same 63 s before it reports the
  error; that is product behavior, not changed here.

The full note is [on #853](https://github.com/DCGM/semant-demo/issues/853).
