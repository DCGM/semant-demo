# Active follow-ups and technical debt

This document indexes **current** known limitations and future work, not a second issue tracker or priority commitment. Keep actionable requirements, decisions and acceptance criteria on GitHub issues. Earlier technical-debt notes and implementation history are preserved in the [archive](archive/refactor-2026/README.md).

## Known correctness and behavior limitations

- [#232 — UTF-16 offsets in span chat](https://github.com/DCGM/semant-demo/issues/232): stored offsets are UTF-16 units, but Python text slicing currently uses code-point indices; context may shift around non-BMP characters.
- [#224 — cross-chunk tag search](https://github.com/DCGM/semant-demo/issues/224): search indexes only the anchor chunk of a cross-chunk annotation; decide whether all covered chunks should be indexed.
- [#218 — tag creation deduplication cap](https://github.com/DCGM/semant-demo/issues/218): address deduplication past the current capped scan with bounded behavior and regression coverage.
- [#227 — Topicer concurrency across requests](https://github.com/DCGM/semant-demo/issues/227): per-run concurrency is bounded, but independent runs have no shared provider limit.
- **Chunk tag consistency:** span writes and their derived chunk-tag references are best effort, not atomic; concurrent synchronization is serialized only within one backend process. Audit with `python -m semant_demo.maintenance.chunk_tag_audit` (see [DEVELOPMENT](DEVELOPMENT.md#chunk-tag-audit-and-cleanup)). Any repair requires a reviewed dry run and explicit apply, never an automatic deployment migration. Consider eventual repair when scaling out; see [ADR 0002](adr/0002-best-effort-writes.md) and #206.
- **Topicer offsets:** proposed start/end positions are treated as character (Unicode code-point) offsets and converted to stored UTF-16. Earlier AI spans near non-BMP characters may need review; no automatic data migration is planned ([ADR 0006](adr/0006-context-and-text.md)). 

## Deployment, security and tests

- [#234 — anonymous paid-provider access](https://github.com/DCGM/semant-demo/issues/234): decide login/rate/cost limits for the public RAG, summary and question endpoints. It is not a private-data access leak, but may incur provider costs.
- [#212 — browser smoke suite in CI](https://github.com/DCGM/semant-demo/issues/212): browser tests are available via `make test-e2e`; evaluate making them an additional blocking CI check.
- **PR preview credentials ([#213](https://github.com/DCGM/semant-demo/issues/213)):** previews use dedicated `OPENAI_API_KEY_PREVIEW` / `JWT_SECRET_PREVIEW` secrets (an administrator must provision them, with a provider spending limit, before previews deploy again) and still deploy after failed checks by design. They share the server and Docker daemon with CI and the other deployments; host separation is deliberately out of scope ([deploy/README](../deploy/README.md#pr-preview-credentials)).
- [#257 — Kramerius metadata sync](https://github.com/DCGM/semant-demo/issues/257): `maintenance.metadata_sync` implements the source-library-only report/apply; the library comes from corrections, a map, chunk start-page ancestry, the stored value or the mirror (with `--library-priority` for documents several libraries hold), and `public` follows the source row. #259 sets the library priority `nkp,mzk` (it decides 215 of the 500 local documents). Open: `mzk` issue rows without their own title or part number give only the periodical title, so `--overwrite` can drop a stored issue number; the single-pass `--sync` mode ran on the deployed test database (2026-10-11, rerun 2026-10-12 with `--prefer-library-with-metadata`, which picks the library whose row has MODS); production ran on 2026-10-12 with 54 documents unresolved (libraries outside `nkp,mzk`; [#259](https://github.com/DCGM/semant-demo/issues/259)); mirror rows with `mods_path = not_found` (83% of `nkp`, 36% of `mzk` monographs) have no `metadata_json`, so their documents get no author or publisher until the `librarymetadata` mirror re-downloads them; the search/document-view `"mzk"` default for a missing library remains (#255).
- [#281 — documents without chunks](https://github.com/DCGM/semant-demo/issues/281): `maintenance.document_cleanup` audits (read-only) and, with a confirmed endpoint, a verified backup and an unchanged chunk count, deletes them, collection members included. The test database audit found 468 of 500 removable (40 in user collections); its deletion and the read-only production audit wait for authorization; production deletion needs separate approval.
- When deploying against an existing Weaviate store, compare property types (especially document metadata) and **review** the #204 chunk-tag audit; do not silently rewrite or reset shared data.

## Product and engineering improvements (when scoped)

- [#230 — document sidebar integration](https://github.com/DCGM/semant-demo/issues/230): move document tools into the app-level sidebar when the UX is decided.
- [#43 — optional durable bulk tagging jobs](https://github.com/DCGM/semant-demo/issues/43): evaluate the requirement and worker/deployment budget first; the current `Tagging Jobs` tab is a placeholder, not an active queue.
- From the earlier backlog: consider repeatable image builds beyond the backend Python lock (#139: base-image digests, the unpinned embedding service requirements); SQL backend scalability beyond the current SQLite use; unified RAG model/prompt creation; search pagination; startup/provider readiness checks; package metadata and broader formatting/type-checking. Create a focused issue and tests before implementation—prioritize them only when an issue is scoped and approved.

## Documentation policy

Update [ARCHITECTURE.md](ARCHITECTURE.md) when implementation changes, [CONTRIBUTING.md](../CONTRIBUTING.md) for workflow/test-policy changes, [DEPLOYMENT.md](DEPLOYMENT.md) for deployment changes, and the [ADRs](adr/README.md) when an agreed decision changes. Link new actionable follow-ups to GitHub rather than modifying archived history.
