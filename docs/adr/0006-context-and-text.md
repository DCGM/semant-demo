# ADR 0006 - Shared context, source text, and optional image alignment

Status: search-chat scope and line-level roadmap agreed; detailed context/geometry
contracts remain implementation proposals.
Date: 2026-10-07. Q3 and Q5 clarified; replaces the earlier whole-query alternative
and page-only starting recommendation.

## Context

Document text will be reused in search, chat, translation, summary, TTS, annotations,
concordances, export, NER display, and page images. A shared sidebar must not cause these
tools to silently operate on a different source or a wider selection.

The pinned review found browser string-length calculations and Python slicing, NER
string lists, and chunk start-page/page-range fields. Those inspected fields do not
establish complete line geometry. No ALTO dataset or deployed alignment was validated.

## Shared context

The app/workspace shell owns the sidebar and active context; feature panels receive
explicit inputs, not unrelated global state. Add only the context variants needed by
implemented features: corpus, search results, collection, document, collection-document,
or passage/annotation. Do not build a generic context framework ahead of use cases.

For server-side AI work, resolve authorized source text and IDs on the server. Client
text, retrieved content, model IDs, and conversation history cannot widen access or scope.
Preserve stable source references in responses and reject late events with a context/run
token. Loading state and caches must also be scoped to the user and active context.

### Search chat - confirmed

Chat operates on **the retrieved results, or an explicitly selected subset of those
results**. It does not mean the whole matching query/filter scope.

Represent the chosen result set explicitly, using existing hit/chunk identifiers and
ranges where applicable. Resolve and re-authorize those sources on use. Do not rerun
the original query and silently substitute a larger or changed result set; do not add
unselected chunks, full documents, or old-conversation sources as evidence. Adjacent
context outside the chosen scope needs an explicit scope change, not a hidden fallback.

An empty or unavailable selected scope is reported, not expanded to the corpus. A new
search or selection creates a new context; late responses cannot overwrite it. Separate
corpus/collection/document chat modes remain separate user-selected modes. Collection-
document context is limited to the included document content, not the entire document.

## Canonical text and coordinates

Keep source text separate from display transformations, translations, TTS normalization,
and alignment-normalized strings. Preserve existing cross-chunk semantics until deliberately changed.
Use shared Python/TypeScript fixtures for Unicode, chunk boundaries, and gaps.

An explicit half-open coordinate convention is the proposed target. Unicode code points
are a possible backend convention with conversion at browser boundaries. First characterize
current stored/manual/AI values and provider behavior; do not relabel existing offsets.
A coordinate change needs a compatibility or migration plan, not an incidental schema edit.

## Line-level text-image correspondence - confirmed roadmap

Line-level correspondence is planned. **Its computation may remain entirely in the
frontend**, for example by mapping canonical chunk text to page ALTO XML. This does not
require moving the alignment algorithm to the backend or adding stored geometry now.

Keep mapping in a small document-viewer module so it can be tested and later replaced.
Make source-page/ALTO access an explicit viewer input or adapter, respecting source access
rules. No new proxy, alignment service, or universal OCR pipeline is a refactor deliverable.
Matching may normalize strings internally, but must map back to canonical text offsets.
Uncertain, ambiguous, or unavailable matches must be visible rather than presented as exact.

Later, chunks, tag annotations, or NER occurrences may carry **optional lists of polygons**.
Geometry is derived location information, not a replacement for stable IDs and text ranges.
A future contract should identify the page and coordinate system for each polygon, support
multiple pages/regions, and record enough source/alignment revision information to avoid
using stale locations. Text-only records and clients must continue working when geometry
is absent. Do not add mandatory geometry fields or a database migration just for alignment planning.

NER string lists do not uniquely identify repeated occurrences. Frontend matching or later
located NER data may provide that correspondence; keep ambiguity explicit and share the
source-location conventions rather than inventing a separate coordinate model.

## Deferred decisions

Choose frontend-only versus persisted alignment, polygon field details, and the mapping
algorithm with real ALTO examples during viewer work. They are not blockers for cleanup.

Q6, chat-history persistence/sharing, remains deferred; preserve current behavior for the
refactor. Persistent history is separate from durable jobs and never permanently grants
access to sources. Recheck access when loading history or citations after sharing changes.

## Verification

When changing text/context features, preserve stored offset behavior and test navigation races and
collection-subset isolation. When search chat is added, test full retrieved set, selected
subset, empty selection, missing/revoked sources, and no fallback to broader retrieval.

When alignment is implemented, test real or synthetic ALTO fixtures: line breaks,
hyphenation, repeated text, Unicode, cross-page/multi-polygon locations, missing/ambiguous
matches, and polygon transforms after image resize/zoom. Exact fixture-to-overlay assertions
belong in mapping tests plus a small browser test. These future tests are not required
before the feature exists.

Pinned evidence: [frontend coordinates](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_frontend/src/composables/useAnnotations.ts),
[AI selection](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/routes/ai_assistance_routes.py),
[text/NER schema](https://github.com/DCGM/semant-demo/blob/375caa5f7f68defba25a56cccbb7dbc7fdf99a13/semant_demo_backend/semant_demo/schemas.py).
