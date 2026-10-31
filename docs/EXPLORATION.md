# Explore — interface and query contract

**Status:** Agreed design (2026-10-31); the shared search criteria are implemented (#526, [ARCHITECTURE.md](ARCHITECTURE.md#search-criteria-featuresdocumentscriteriapy-adaptersweaviatecriteriapy)), the Explore workspace is not. Planning parent: [#346](https://github.com/DCGM/semant-demo/issues/346). The current application is described in [ARCHITECTURE.md](ARCHITECTURE.md); this file specifies the intended Explore behavior.

## Scope and terminology

**Explore** is the public-corpus discovery workspace, combining search, document browsing and linked visualizations. It is not a new backend service.

| Concept | UI term | Code/route convention |
| --- | --- | --- |
| Workspace | **Explore** | `/explore`; frontend `features/explore/` |
| Main views | **Results**, **Visualizations** | `ExploreView = 'results' \| 'visualizations'` |
| Results modes | **Documents**, **Passages** | `ResultsMode = 'documents' \| 'passages'` |
| Shared submitted query and filters | **Search criteria** | Backend `SearchCriteria`; frontend `searchCriteria` |
| Optional free-text input | **Text query** | `SearchCriteria.text_query` (TypeScript `textQuery`) |
| Bibliographic restrictions | **Document filters** | Existing `DocumentFilters` contract, shared across consumers |
| Restrictions on stored chunks | **Passage filters** in UI | `ChunkFilters` backend model (chunk language, configured classifications) |
| Existing statistics page | **Corpus overview** | Keep `/corpus` and `CorpusOverviewPage.vue` |
| Source reading | **Document reader** | Application-wide viewer; [#351](https://github.com/DCGM/semant-demo/issues/351) |

**Passage** names a user-facing search result, not a new stored entity. The underlying record remains a `Chunk` / `DocumentChunk`, returned as `SearchResultChunk` for text search, optionally with relevance/highlight/excerpt information. Keep **Chunk** in database, backend schemas and APIs; use **Passage** in UI labels, view names and UX documentation. A text query is not the same as the document-title metadata filter.

## Views and interaction

- **Results** offers a `Documents | Passages` switch. Both modes use the same applied Search criteria, but request independently ranked results. Without a text query, default to **Documents**; filter-only Passages browsing is deferred.
- **Visualizations** is a dedicated view with room for charts. Results may also include **compact visualizations** where space permits; on small screens the dedicated view remains accessible and compact charts can be omitted.
- Switching between Results, Visualizations and results modes preserves applied criteria. Changing modes does not silently change the text query or filters.
- Charts and content are linked: selecting a category may apply a filter; an action to inspect contributing records opens matching results. **Applying** a chart filter changes the criteria and reruns relevant queries. **Inspecting** an existing bounded result set must not silently expand or rerun that set.
- Chart **zoom/pan** changes presentation only, not the filtered population. Give it a separate reset. Applied filters remain visible and removable, with **Clear all**.
- Typing edits **draft criteria**; **Enter** or **Apply** commits them as the criteria for both Results and Visualizations. Some chart interactions may commit immediately when practical; they are optional, not first-release requirements. Pending edits must not relabel old results as new ones.
- Record committed criteria changes in browser history; Back/Forward restores them. Encode applied criteria, active view and results mode in the Explore URL for navigation/sharing, without persisting private data or pretending a subsequent search reproduces a frozen result set.
- Opening a document or a passage uses the **application-wide document reader**, focused on the relevant document/chunk/text when available, and preserves return navigation. Explore must not implement another reader.

## Shared criteria and matching

One typed backend `SearchCriteria` structure (`features/documents/criteria.py`) has an **optional text query**, `DocumentFilters` and `ChunkFilters`. Share filter definitions, normalization, validation and predicate semantics among Search, document browsing and Analytics. Keep retrieval parameters (method, limit, vector configuration) in endpoint-specific requests; no user-visible retrieval-method selector is required initially.

- Combine different filter dimensions with **AND**; multiple accepted values within one dimension use **OR**. Reject invalid/unavailable filters explicitly rather than treating them as zero matches.
- **Document filters** refer to document metadata (publication year, source library, title and **document language**). **Passage language** refers to `Chunks.language`, not `Documents.language`. Do not merge these fields or their statistics.
- **Chunk filters** are exact categorical matches on the chunk language and the configured classifications (no year, no named entities); "missing"/"unknown" values cannot be selected. How they apply depends on the unit (decided on [#526](https://github.com/DCGM/semant-demo/issues/526#issuecomment-6549472480)):
  - **Passages: same-chunk.** A passage qualifies when **the passage itself** satisfies every chunk filter, and its document every document filter.
  - **Documents: per dimension.** A document qualifies when, **for each selected chunk filter, at least one of its chunks** has one of the selected values; different filters may be satisfied by different chunks. The document filters must hold as well. Minimum counts or proportions per dimension are deferred. Document results and document-level Analytics use this same rule.
  - The two rules differ only with two or more chunk filters: for "Czech AND narration", a document with a Czech chunk and a separate narration chunk qualifies as a document, but neither passage does.
- Document-level chunk filtering uses derived per-dimension unions of the chunks' values stored on `Documents` (**document metadata summaries**, [#529](https://github.com/DCGM/semant-demo/issues/529)). They are a snapshot recomputed periodically by an explicit, rerunnable full-database operation (it replaces the old values and records its completion); between runs they may be stale, which is accepted, and they are never synchronized at write time or during a request. Until they exist, document-level endpoints reject chunk filters explicitly (422).
- Apply document and chunk restrictions **during retrieval or eligible-population resolution**, never merely discard nonmatching hits from an already limited top-k search and call the remainder complete.
- The same criteria must mean the same thing in Search and Analytics even though their execution, counts and response schemas differ. Do not require a generic all-purpose database query endpoint.

## Results and ranking

**Documents mode**:
- With a text query, the **filters decide eligibility** and the **text query decides ranking**, independently: a document qualifies by the rules above, and its best text match need not be a chunk that satisfies the chunk filters.
- Retrieve **document metadata matches first** (especially titles; authors/publishers when available), ahead of all documents found only through text. Rank within the metadata group by metadata relevance.
- Rank remaining distinct documents using the existing chunk-search order (best qualifying chunk), initially without score fusion. A document appears once; retain useful matching chunk evidence for navigation.
- Use a separately defined, appropriately bounded document-retrieval strategy. Deduplicating a small passage top-k list is **not** exhaustive document search.
- Without text query, browse matching document records with pagination; any default sort must be stable and clearly indicated.

**Passages mode**:
- With a text query, use current chunk-level keyword/semantic/hybrid retrieval and ranking. A result is presented as a **Passage**, backed by `SearchResultChunk`; highlighting the relevant part is desirable when reliable.
- Additional ranking fusion is future work. Filter-only browsing of passages is **not required initially**.

## Visualization population and counts

- **No text query:** visualize the **full population matching the applied filters**, where technically feasible, with each chart explicitly naming its counting unit (documents or chunks). If an exhaustive calculation is unavailable, report the limitation; never silently substitute a sample or zero.
- **With a text query:** visualize only the **retrieved results for the active Results mode**, bounded by a configurable technical limit. A relevance threshold may be added later only when the chosen retrieval scores support meaningful thresholding.
- State the unit, input size, retrieval method/limit and whether counts cover the full matching population or only retrieved results. A chart of 100 passages from 40 distinct documents is **not** a corpus-wide distribution.
- Switching Results mode changes which retrieved population query-based charts describe. A chart can show a different counting unit (e.g. distinct source documents) **within that same retrieved population**, but must not silently widen it.
- Keep missing/unknown/unavailable values distinguishable; retain exact record-level evidence for the displayed groups when practicable.
- Document distributions over a chunk dimension (from the document metadata summaries) are **multi-valued**: a document with Czech and German chunks counts under both, so the groups overlap and do not add up to the total. Label such charts accordingly ("documents with at least one such chunk").

## Ownership, rollout and exclusions

- **Frontend:** `features/explore/` owns criteria, URL/history, view switching and linked presentation; reuse existing Search, document and Vega components.
- **Backend:** keep `features/search/` for two distinct retrieval endpoints (planned `/api/search/documents` and `/api/search/passages`), `features/analytics/` for aggregates, and existing document services for reading. The shared `SearchCriteria` and filter logic must not create a new backend Explore feature.
- **Compatibility:** retain the current `/search`, `/api/search` and `/corpus` while the replacement is built and verified. Later decide whether `/corpus` remains a statistics page or is deprecated; do not remove it as part of this design.
- **Outside this scope:** user collections, tags, annotations/attributes, their analytics ([#311](https://github.com/DCGM/semant-demo/issues/311)), new RAG workflows, implementing the document reader (#351), filter-only Passages browsing, an initial search-method selector, and speculative graph/map features.

**Implementation order:** (1) shared `SearchCriteria` and filter semantics; (2) Explore Results and separate retrieval; (3) Explore Visualizations and chart/results linking. The existing [#254](https://github.com/DCGM/semant-demo/issues/254) and [#361](https://github.com/DCGM/semant-demo/issues/361) provide document-level analytics foundations. Verify shared filter/count agreement, retrieval limits and performance on representative data before claiming the workflow complete.
