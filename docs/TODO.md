# Open risks and follow-ups

A short index of **open** limitations that affect development or operation. Requirements,
decisions and status live on the linked GitHub issues; update this list when an issue is
opened or closed, not with progress notes. Completed work is recorded on its issue/PR and,
for the 2026 refactor, in the [archive](archive/README.md).

## Correctness and behavior

- [#224](https://github.com/DCGM/semant-demo/issues/224) — tag-filtered search indexes only the anchor chunk of a cross-chunk span.
- [#218](https://github.com/DCGM/semant-demo/issues/218) — tag creation deduplication reads at most 2000 tags of a collection.
- [#227](https://github.com/DCGM/semant-demo/issues/227) — Topicer calls are bounded per run, not across concurrent runs.
- [#402](https://github.com/DCGM/semant-demo/issues/402) — the adaptive RAG's Explain answers 500 when `sources`, the selection or the answer is empty.
- **Chunk tag consistency** — span writes and their chunk tag references are best effort, serialized only within one backend process, so run one process ([ADR 0002](adr/0002-best-effort-writes.md)). Audit and reviewed repair: [DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#chunk-tag-audit-chunk_tag_audit).
- **Topicer offsets** — proposals are read as code points and stored as UTF-16; older AI spans near non-BMP characters may need review; no automatic migration is planned ([ADR 0006](adr/0006-context-and-text.md)).

## Data

- [#327](https://github.com/DCGM/semant-demo/issues/327) — annotations moved to one tenant per collection; production and the shared test store are migrated (2026-10-18). Another store needs the [cutover](DATA_MAINTENANCE.md#cutover-production-test-store) before a release with #327 runs on it. Idle tenant deactivation stays disabled (no memory benefit measured yet). The legacy `Span` collection is kept for rollback.
- [#328](https://github.com/DCGM/semant-demo/issues/328) — annotation text, positions and vectors are stored only after `annotation_enrichment add-schema` on a store, and existing spans only after its backfill ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#annotation-derived-data-annotation_enrichment-328)); schema and backfill are on production and the shared test store (`status` on 2026-10-25: 15,273 / 1,178 spans with current text, one failed vector on each store, likely an over-long span: [#439](https://github.com/DCGM/semant-demo/issues/439)). With several backend processes a late vector may land on a newer revision; it is detected as stale, not prevented, so the backfill runs with the application stopped. Concordance rows have their route (#329); similarity reads have none until #332 (annotation search, Stage 2). Stored contexts join chunk texts without a separator, as the canonical text does, so words of neighbouring chunks can run together in KWIC rows ("ošklivé.Pozdravuj"); a display separator needs the chunk boundaries in the stored context.
- [#460](https://github.com/DCGM/semant-demo/issues/460) — annotation provenance and `editVersion` conflicts are recorded only after `annotation_provenance add-schema` on a store and a backend restart ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#annotation-provenance-annotation_provenance-460)); schema added to production and the shared test store (2026-10-23), recorded since the restarts with `v0.1.29` and `test-main`. Existing annotations stay `origin: unknown`. The version check is atomic only within one backend process ([ADR 0010](adr/0010-annotation-provenance-and-edit-versions.md)). Provenance in the document view: [#467](https://github.com/DCGM/semant-demo/issues/467).
- [#331](https://github.com/DCGM/semant-demo/issues/331) — collection attributes are stored and assigned only after `annotation_attributes add-schema` on a store and a backend restart ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#collection-attributes-annotation_attributes-331)); run on production and the shared test store (2026-10-25, before `v0.1.30` and the `test-main` deploy of `04bf55f`). Backend and API only so far: the workspace UI, value merging and undo of assignments follow; the API is not exercised on a deployed instance until the UI lands. One `attributeVersion` serves all attributes of an annotation ([ADR 0011](adr/0011-collection-attributes.md)). Definitions and change records are SQL data: restore them together with Weaviate. Follow-ups ([#498](https://github.com/DCGM/semant-demo/issues/498), [#499](https://github.com/DCGM/semant-demo/issues/499)): merging used values, `single` → `multi` cardinality, and a maintenance check for orphaned attribute ids and SQL rows left by a failed collection deletion. Values on an annotation retagged to a tag the attribute does not apply to stay visible ([#500](https://github.com/DCGM/semant-demo/issues/500)). Change records keep names, labels and kinds of their time but not descriptions or examples; interpreting past decisions by the definitions of their time needs versioned definitions ([#502](https://github.com/DCGM/semant-demo/issues/502)).
- [#422](https://github.com/DCGM/semant-demo/issues/422) — production chunk tag references disagree with the annotations in 6,689 audit entries (6,603 annotations missing from tag-filtered search, 86 unbacked references); cause and reviewed repair pending.
- [#376](https://github.com/DCGM/semant-demo/issues/376) — chunk context reads (and sorts) every chunk of the document; 0.14–0.2 s p50, up to 2.4 s ([audit](WEAVIATE_AUDIT_2026-10-17.md#376-chunk-context-and-document-reads)).
- [#259](https://github.com/DCGM/semant-demo/issues/259) — Kramerius metadata import: unresolved libraries and mirror rows without MODS (no author/publisher).
- [#281](https://github.com/DCGM/semant-demo/issues/281) — documents without text chunks: audit and gated removal ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#documents-without-chunks-document_cleanup-281)).
- [#279](https://github.com/DCGM/semant-demo/issues/279) — corpus document public-access policy.
- [#313](https://github.com/DCGM/semant-demo/issues/313) — chunk ingestion does not fill `Chunks.yearIssued`, which the year filter uses; until it does, run `chunk_year --write` after ingesting chunks or changing document years ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#document-year-on-chunks-chunk_year-153)). Ingestion also does not add the `Qwen3_Embedding_0_6B` vector: run the embedder (`data_tools/embedder`) afterwards, or new chunks are missing from vector and hybrid search.
- When deploying against an existing Weaviate store, compare property types (especially document metadata) and review the chunk tag audit; never silently rewrite or reset shared data.

## Deployment, security and tests

- [#319](https://github.com/DCGM/semant-demo/issues/319) — access tokens live 7 days without renewal, and the stateless JWT logout revokes nothing server-side: signing out only forgets the token in this browser (all its tabs).
- [#444](https://github.com/DCGM/semant-demo/issues/444) — several `weaviate_utils/` scripts delete data or change the schema on `localhost` as soon as they run, without arguments or confirmation ([agent-readiness audit](AGENT_READINESS_AUDIT_2026-10.md)).
- [#261](https://github.com/DCGM/semant-demo/issues/261) — reproducibility of the production frontend build. The backend Python packages are locked; the base images and the embedding service requirements are not ([DEPLOYMENT.md](DEPLOYMENT.md#docker--production-deployment)).
- [#501](https://github.com/DCGM/semant-demo/issues/501) — the frontend unit test `routes.spec.ts` (deep link `/search`) times out in the full `make check` run and passes alone.
- The seeded local development environment ([DEVELOPMENT.md](DEVELOPMENT.md#2-lifecycle-reset-and-safety), #438) runs one instance per machine (fixed container, volume and ports); parallel checkouts or agents must take turns. Its corpus is the small test fixture; `make dev-add-documents` adds deterministic metadata-only documents for the corpus overview (#361), while a richer dataset with chunks and annotations is separate follow-up work.
- PR previews share the server and Docker daemon with CI and the other deployments; separate preview credentials limit, but do not isolate, them ([deploy/README](../deploy/README.md#pr-preview-credentials)). Host separation is out of scope.

## Product work (when scoped)

- [#43](https://github.com/DCGM/semant-demo/issues/43) — optional durable bulk tagging jobs; the placeholder `Tagging Jobs` tab was removed (#479).
- Page-specific sidebar tools and chat: [#243](https://github.com/DCGM/semant-demo/issues/243) and its linked issues.

Create a focused issue before starting other improvements (SQL scalability beyond SQLite,
search pagination, provider readiness checks).

## Documentation policy

Update [ARCHITECTURE.md](ARCHITECTURE.md) when implementation changes,
[CONTRIBUTING.md](../CONTRIBUTING.md) for workflow/test-policy changes,
[DEPLOYMENT.md](DEPLOYMENT.md) or [deploy/README](../deploy/README.md) for deployment changes,
[DATA_MAINTENANCE.md](DATA_MAINTENANCE.md) for maintenance procedures, and the
[ADRs](adr/README.md) when an agreed decision changes. Do not modify archived history.
