# ADR 0010 - Annotation provenance and edit versions

Status: proposed with #460 (implementation in review); store rollout pending an operator step.
Date: 2026-10-22. Decided in the collection-workspace plan (#330, decisions of 2026-10-21 and
2026-10-22 in #330 and #460); refines ADR 0008 (annotation storage) and ADR 0007
(collaboration without live synchronization).

## Context

Several users of a shared collection review the same annotations: one in the document view,
another in the workspace with a selection of up to 5,000 annotations (#459). Before #460 an
annotation recorded no actor, time or origin, and every write overwrote whatever a
collaborator had saved meanwhile; approving an AI proposal (`auto` → `pos`) also erased that it
came from AI. `revision` (ADR 0009) counts offset changes only, because derived data depends on
nothing else.

## Decision

- **Current-state provenance on the `Annotation` object**, not an event log: `origin`
  (`manual` / `ai` / `unknown`), `createdBy`/`createdAt`, `reviewedBy`/`reviewedAt` (last approve
  or reject), `lastEditedBy`/`lastEditedAt` (last span write) and `aiRunId` (a UUID generated per
  suggestion run; no run table). `origin` is independent of `type` and, like `aiRunId`, `reason`
  and `confidence`, is never rewritten. User ids are stored; clients resolve names from the
  collection's owner and members. Annotations saved before keep `origin` `unknown` and no actor
  or time; nothing is backfilled or invented.
- **`editVersion`** counts every span write (type, tag, offsets; 0 at creation). Clients send
  the version they know (`expected_version`); a write or delete of an annotation written since
  is refused with 409 and the current annotation, or per item (`edit_conflict`) in batches, and
  changes nothing. A write that finds the annotation already as it asks counts as done without
  writing, so retrying a write whose answer was lost is no conflict. Document-wide cleanups
  (delete all approved annotations or suggestions of a tag in a document) are not checked.
- **Batches check every item.** The workspace selection keeps each member's version from when
  it was added (*Select all* gets them with the resolved ids); only this user's saved writes move
  it on. A conflicting item is reported apart and never retried: the user selects the changed
  items at their current versions and reviews them again.
- The check reads the annotation, and the write reads it back, under its per-span lock (a write
  returns the version it saved, never a later writer's): reliable within one backend process,
  detectable but not atomic across processes (as ADR 0009 accepts for revisions). `revision`
  keeps its boundary-only meaning.
- The backend reads and writes the properties only when the collection holds them (decided at
  startup); adding them is an explicit operator command (`annotation_provenance add-schema`),
  never startup or a request. Without them nothing is recorded and no version is checked.

## Consequences

Every checked write reads the annotation once more before writing (a lookup by id), also for
type and tag changes that needed no read before; batches of 200 do these reads concurrently.
Reads and the ids lookup return one more integer per annotation. Users see conflicts where
they used to overwrite silently, including on large *Select all* batches. History (who changed
what before the last change) and undo are not recorded here; undo (#461) restores previous
values only where `editVersion` shows nothing changed since. Provenance is shown in the
workspace sidebar; the document view reports conflicts but does not show provenance (#467).

## Verification

Service behavior with fakes (`tests/test_annotation_service.py`: provenance per write, refused
outdated writes and deletes, already-applied writes, the saved version returned when another write
follows at once, per-item batch conflicts, unchecked cleanups,
no recording before the schema; `tests/test_suggestions.py`: run id and origin), real Weaviate
1.40.1 (`tests/integration/test_annotation_provenance.py`: API provenance and 409, review
conflicts, schema addition to a pre-#460 collection without auto-schema), frontend store and
component tests (`concordance.spec.ts`, `editConflicts.spec.ts`, `provenanceSummary.spec.ts`,
`selectionBar.spec.ts`) and browser tests (`annotationWorkspace.spec.ts`, also a
conflict whose change took the annotation out of the filters; `documentViewer.spec.ts`).
