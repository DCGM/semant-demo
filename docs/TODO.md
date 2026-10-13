# Open risks and follow-ups

A short index of **open** limitations that affect development or operation. Requirements,
decisions and status live on the linked GitHub issues; update this list when an issue is
opened or closed, not with progress notes. Completed work is recorded on its issue/PR and,
for the 2026 refactor, in the [archive](archive/README.md).

## Correctness and behavior

- [#232](https://github.com/DCGM/semant-demo/issues/232) — span chat slices UTF-16 span offsets as Python code points; context may shift around non-BMP characters.
- [#224](https://github.com/DCGM/semant-demo/issues/224) — tag-filtered search indexes only the anchor chunk of a cross-chunk span.
- [#218](https://github.com/DCGM/semant-demo/issues/218) — tag creation deduplication reads at most 2000 tags of a collection.
- [#227](https://github.com/DCGM/semant-demo/issues/227) — Topicer calls are bounded per run, not across concurrent runs.
- **Chunk tag consistency** — span writes and their chunk tag references are best effort, serialized only within one backend process, so run one process ([ADR 0002](adr/0002-best-effort-writes.md)). Audit and reviewed repair: [DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#chunk-tag-audit-chunk_tag_audit).
- **Topicer offsets** — proposals are read as code points and stored as UTF-16; older AI spans near non-BMP characters may need review; no automatic migration is planned ([ADR 0006](adr/0006-context-and-text.md)).

## Data

- [#259](https://github.com/DCGM/semant-demo/issues/259) — Kramerius metadata import: unresolved libraries and mirror rows without MODS (no author/publisher).
- [#281](https://github.com/DCGM/semant-demo/issues/281) — documents without text chunks: audit and gated removal ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#documents-without-chunks-document_cleanup-281)).
- [#279](https://github.com/DCGM/semant-demo/issues/279) — corpus document public-access policy.
- When deploying against an existing Weaviate store, compare property types (especially document metadata) and review the chunk tag audit; never silently rewrite or reset shared data.

## Deployment, security and tests

- [#234](https://github.com/DCGM/semant-demo/issues/234) — anonymous RAG, summary and question endpoints call paid providers; decide login/rate/cost limits.
- [#212](https://github.com/DCGM/semant-demo/issues/212) — run the browser smoke suite (`make test-e2e`) in CI.
- [#299](https://github.com/DCGM/semant-demo/issues/299) — Topicer compose files lack their Dockerfile; Topicer is deployed manually, not by CI/CD.
- [#300](https://github.com/DCGM/semant-demo/issues/300) — an empty `FEEDBACK_LOG_PATH` (as in the `.env` templates) makes app feedback fail.
- [#261](https://github.com/DCGM/semant-demo/issues/261) — reproducibility of the production frontend build. The backend Python packages are locked; the base images and the embedding service requirements are not ([DEPLOYMENT.md](DEPLOYMENT.md#docker--production-deployment)).
- PR previews share the server and Docker daemon with CI and the other deployments; separate preview credentials limit, but do not isolate, them ([deploy/README](../deploy/README.md#pr-preview-credentials)). Host separation is out of scope.

## Product work (when scoped)

- [#255](https://github.com/DCGM/semant-demo/issues/255) — link search results, chat citations and document views to their original digitized sources.
- [#43](https://github.com/DCGM/semant-demo/issues/43) — optional durable bulk tagging jobs; the `Tagging Jobs` tab is a placeholder.
- Page-specific sidebar tools and chat: [#243](https://github.com/DCGM/semant-demo/issues/243) and its linked issues.

Create a focused issue before starting other improvements (SQL scalability beyond SQLite,
search pagination, provider readiness checks).

## Documentation policy

Update [ARCHITECTURE.md](ARCHITECTURE.md) when implementation changes,
[CONTRIBUTING.md](../CONTRIBUTING.md) for workflow/test-policy changes,
[DEPLOYMENT.md](DEPLOYMENT.md) or [deploy/README](../deploy/README.md) for deployment changes,
[DATA_MAINTENANCE.md](DATA_MAINTENANCE.md) for maintenance procedures, and the
[ADRs](adr/README.md) when an agreed decision changes. Do not modify archived history.
