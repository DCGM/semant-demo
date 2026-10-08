# Architecture principles and future directions

This page holds **ongoing design constraints**, not a second implementation plan. The detailed original pre-refactor target is [archived](archive/refactor-2026/TARGET_ARCHITECTURE.md).

The authoritative description of what the application **does today** is [ARCHITECTURE.md](ARCHITECTURE.md). Adopted contracts and decisions are in the [ADRs](adr/README.md), and future product objectives are in [VISION.md](VISION.md). Track new implementation work with a scoped GitHub issue, linked from [TODO.md](TODO.md) when appropriate.

## Current architectural principles

- Keep one feature-oriented FastAPI application with explicit request dependencies and application-lifespan resources; storage and external-provider calls belong in `adapters/`. Add layers or interfaces only when they solve a demonstrated problem.
- Services enforce collection- and resource-level authorization. Shared users can edit tag definitions and annotations but not collection membership or owner-only settings ([ADR 0007](adr/0007-access-and-collaboration.md)).
- Store annotations in Weaviate as spans and maintain searchable chunk tag references on the existing chunk attributes. Treat failed second-step writes as **partial**, not as rollback successes ([ADR 0002](adr/0002-best-effort-writes.md)).
- Keep AI proposal generation request-scoped with progressive results and cancellation, not an implicit durable job system ([ADR 0003](adr/0003-request-scoped-ai.md)). Durable bulk jobs are optional future product work [#43](https://github.com/DCGM/semant-demo/issues/43).
- Preserve canonical corpus text, document IDs and UTF-16 span coordinates; any geometry or ALTO mapping is optional future work ([ADR 0006](adr/0006-context-and-text.md)).
- Partition frontend state by user/collection/document and reject late responses. Search summaries work on actually retrieved or explicitly selected results, without silently broadening retrieval.
- Keep deterministic offline fast tests, real-store integration tests and small browser smoke tests; require passing CI and generated API client drift checks before merging to protected `main` ([CONTRIBUTING](../CONTRIBUTING.md)).

## Open boundaries

See [TODO.md](TODO.md) for relevant issues, including cross-chunk tag-search behavior (#224), multi-request AI concurrency (#227), future document-view panels (#230), provider access (#234), and data/index repair as explicitly reviewed maintenance. These are not reasons to reintroduce the pre-refactor architecture.
