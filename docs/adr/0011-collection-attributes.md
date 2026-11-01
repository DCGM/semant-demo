# ADR 0011 - Collection attributes and accepted assignments

Status: proposed with #331; backend merged (#495) and its schema on the deployed stores
(2026-10-25); definitions are edited in the Attributes part of the Tags & attributes tab, the workspace assignment UI follows.
Date: 2026-10-24. Decided in the collection-workspace plan (#311, #324, #331);
refines ADR 0008 (annotation storage), ADR 0010 (provenance and edit versions) and ADR 0007
(rights); the exact-match design follows the issue's Weaviate representation.

## Context

A researcher classifies occurrences by user-defined categorical attributes (`speaker_type`,
`topic`, `stance`), assigns values to single rows or selections, filters and counts by them, and
renames categories later without rewriting annotations or losing who decided what. Later stages
(statistics #334, AI proposals #336/#337, clusters #340) read the same accepted assignments.

## Decision

- **Definitions are collection data in SQL**, three small tables (`adapters/sql/attributes.py`):
  attributes (stable UUID, name, description, `single`/`multi` cardinality, applicable tags,
  retired flag, `revision`), their values (stable UUID, label, description, examples, kind
  `value`/`unknown`/`not_applicable`, retired flag) and an append-only change record. Names are
  unique per collection and labels per attribute, ignoring case and surrounding spaces; nothing is
  global. A definition has the same rights as a tag definition (owner and shared users,
  `require_attribute_definition_edit`). The cardinality cannot change after creation. Deleting a
  collection deletes the collection first and its definitions and change records afterwards
  (see Consequences).
- **The accepted assignments of an annotation are one array on the annotation**,
  `Annotation.attributeValues` (`text[]`, whole-element tokenization, filterable, not searchable):
  elements `<attribute id>:<value id>` with both ids in canonical lowercase UUID form
  (`features/annotations/attribute_codec.py`). Fixed-length parts make the encoding unambiguous: no element is a
  prefix of another, the prefix `<attribute id>:` selects exactly one attribute, labels and
  punctuation never take part. The array is the only copy of the current state.
- **Filters** use the array only: any of an attribute's values (`contains_any`), all attributes
  (conditions are ANDed), and "no accepted value of attribute A" as the explicit negation of the
  prefix `like` (`NOT (attributeValues like "A:*")`, or a non-approved annotation), which also holds for annotations that never
  had the property or hold an empty array. Verified on Weaviate 1.40.1
  (`tests/integration/test_annotation_attributes.py`). Filters are part of the concordance query and
  of id resolution; ids of another collection simply match nothing in the tenant.
- **Only approved (`pos`) annotations receive values.** Unresolved AI suggestions and rejected
  annotations carry no accepted classification, and nothing here writes AI-proposed values: those
  belong to a separate proposal structure (#337/#338) and enter the array only through a person's
  decision (`source: ai_assisted` with the run id). `ai_assisted` is refused (400) until that
  exists, because a run cannot be checked yet; the record shape is ready for it. Values stay
  stored on an annotation that is later rejected but are not shown: rows of a non-`pos`
  annotation carry no `attributes`, `?attribute=` matches only `pos` annotations and
  `?unassigned=` counts a non-`pos` annotation as unassigned. Approving it again shows the values
  again. Asking for a kept value again on a non-`pos` annotation is refused
  (`check_annotation_type`), not taken as "already as asked". Removing values is allowed for any
  type. Spans (`TagSpan`: `GET /api/tag_spans` and the span write results) carry no values at all,
  only `attributeVersion`; the attribute service reads the stored array itself.
- **A separate `attributeVersion`** (`INT`, 0 at creation) counts assignment writes. An assignment
  names the version it expects per annotation; one written since is refused (`edit_conflict`) and
  changes nothing, one already as asked counts as done without a write (a retry). Attribute
  writes do not move `editVersion` and are not checked against it, so a collaborator's attribute
  decision never makes your pending approve or retag conflict. The counter is shared by all
  attributes of the annotation: two people assigning different attributes of one annotation at
  once conflict. The check runs under the per-span lock (one backend process, as ADR 0010).
- **Batches are best effort** (ADR 0002): up to 200 annotations, one attribute, mode `add` /
  `remove` / `replace`, each annotation on its own with a reported step (`find_annotation`,
  `edit_conflict`, `check_annotation_type`, `check_applicable`, `check_value`, `check_cardinality`,
  `update_attributes` - `uncertain` on a timeout); nothing is rolled back. Single-valued attributes
  take one value (`add` of a different one is refused, `replace` is not); Unknown and Not
  applicable are explicit values, at most one each per attribute, never combined with other
  values; retired values and attributes cannot be assigned again but can be removed.
- **Change records** (`annotation_attribute_change`, SQL) hold, per annotation and attribute and
  assignment: actor, time, the attribute id with its name at that time, the previous and new
  values as ids with their labels and kinds at that time, `manual`/`ai_assisted` source with the
  run id, the annotation's `editVersion` when it has one and the attribute's `revision`. Records are
  appended right after each annotation's Weaviate write (one record per annotation, so one failure
  costs one record); when that fails the assignment stays and the response says
  `record_attribute_changes` failed for that annotation. A record is never rewritten: the ids are
  the identity, the names, labels and kinds only what the history shows, so a later rename,
  retirement or deletion of the definition neither changes nor hides what a past decision said
  (an id without a definition when recorded keeps no label). Descriptions and examples are not
  copied into records; interpreting a past decision by the definition of its time needs versioned
  definitions (#502). There is no undo of assignments yet.
- **All tags is explicit** (#522). An attribute applies to all tags of the collection, also
  tags created later (`all_tags=true`, `tag_ids=[]`), to selected tags (`all_tags=false` with
  their ids) or to no tag (`all_tags=false`, `tag_ids=[]`). `all_tags` defaults to false, and
  All tags is never inferred from an empty list, so removing the last selected tag (also from
  the tag side, #516) leaves the attribute for no tag instead of making it global. All tags has no
  per-tag exceptions; `all_tags=true` with tags is refused (422), and so is sending tags to an
  All tags attribute without `all_tags=false` (400). An attribute for no tag takes no new values
  (`check_applicable`) and is not retired automatically. A tag deleted later stays in `tag_ids`
  (#508); it never turns Selected tags into All tags either.
- **Rename and retire, never rewrite.** Labels, descriptions and applicable tags change without
  touching annotations. A value or attribute that annotations still hold cannot be deleted (409
  with the number affected) but can be retired. The UI offers only retiring and restoring
  (#506); deletion stays an API operation for exceptional cleanup. When the usage cannot be counted (the count fails,
  or startup could not read the schema, so whether annotations hold values is unknown), deleting
  and narrowing are refused with 503 rather than taken as unused. Narrowing an attribute's applicable tags while
  annotations hold values of it is refused the same way (409, counting only annotations whose tag
  would fall outside the new tags; going from All tags to selected tags or to none, and from
  selected tags to none, is narrowing too); widening and an unchanged scope are always allowed. Merging values (reassigning the affected
  annotations) is not implemented here.
- **The properties are added by an operator command**
  (`annotation_attributes add-schema`), never at startup or by a request; the backend reads and
  writes them only when the collection holds them (`bootstrap.detect_attributes`). Without them
  definitions work and assignments answer 503. They are not derived data: attribute and tag changes
  never re-embed (ADR 0009).

## Consequences

Assignments read the annotation once under its lock and write one update (two for the record
afterwards, SQL); one request writes at most 16 annotations at a time. Definitions in SQLite are part of the daily backup (#399) and, being product
data, not recoverable from Weaviate alone; a restore of Weaviate without the matching SQL database
leaves assignments whose ids have no definition (shown as unknown values, filters still exact).
A value or attribute deleted between the usage count and the delete can be left on an annotation
without a definition (a small race; clients must show unknown ids as such, and a maintenance check
for orphaned ids is a follow-up). The conflict check uses the in-process span lock, so it holds
for one backend process only. `run_id` of an AI-assisted assignment is not checked against a run.
Change records keep only the name, labels and kinds of their time, not the descriptions and
examples, so what a value meant when it was assigned is known only as far as its label tells
(versioned definitions: #502).
Collection deletion crosses two stores: the collection (Weaviate) first, then its definitions and
change records (SQL), so a failed collection deletion never costs a surviving collection its
definitions or history; rows a failed second step leaves behind belong to a collection that no
longer exists and are unreachable (cleaning them is a follow-up, `docs/TODO.md`). Retagging an annotation to a tag an
attribute does not apply to keeps its values and, unlike a rejection, still shows them in rows and
filters: the state narrowing refuses to create. How to handle it is open (#500). The document view does not show attributes yet.

## Verification

Service rules with a real SQLite repository and in-memory spans (`tests/test_attributes.py`:
definitions, per-collection ids, assignment modes and rules, conflicts and retries, concurrency,
failed/uncertain writes, change records, access, collection deletion order), the filters in the
concordance service (`tests/test_annotation_concordance.py`), and real Weaviate 1.40.1
(`tests/integration/test_annotation_attributes.py`: exact filters with similar ids, several values,
empty arrays and missing properties, use counts, the API end to end, store without the
properties).
