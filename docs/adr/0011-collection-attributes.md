# ADR 0011 - Collection attributes and accepted assignments

Status: proposed with #331 (backend in review; workspace UI follows); store rollout pending an
operator step. Date: 2026-10-24. Decided in the collection-workspace plan (#311, #324, #331);
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
  collection removes its definitions first, so a repeated deletion still finds the collection.
- **The accepted assignments of an annotation are one array on the annotation**,
  `Annotation.attributeValues` (`text[]`, whole-element tokenization, filterable, not searchable):
  elements `<attribute id>:<value id>` with both ids in canonical lowercase UUID form
  (`features/attributes/codec.py`). Fixed-length parts make the encoding unambiguous: no element is a
  prefix of another, the prefix `<attribute id>:` selects exactly one attribute, labels and
  punctuation never take part. The array is the only copy of the current state.
- **Filters** use the array only: any of an attribute's values (`contains_any`), all attributes
  (conditions are ANDed), and "no accepted value of attribute A" as the explicit negation of the
  prefix `like` (`NOT (attributeValues like "A:*")`), which also holds for annotations that never
  had the property or hold an empty array. Verified on Weaviate 1.40.1
  (`tests/integration/test_annotation_attributes.py`). Filters are part of the concordance query and
  of id resolution; ids of another collection simply match nothing in the tenant.
- **Only approved (`pos`) annotations receive values.** Unresolved AI suggestions and rejected
  annotations carry no accepted classification, and nothing here writes AI-proposed values: those
  belong to a separate proposal structure (#336/#337) and enter the array only through a person's
  decision (`source: ai_assisted` with the run id). Values stay on an annotation that is later
  rejected or retagged; accepted-only counts must also filter by `type = pos`. Removing values is
  allowed for any type.
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
  assignment: actor, time, previous and new value ids, `manual`/`ai_assisted` source with the run
  id, the annotation's `editVersion` when it has one and the attribute's `revision`. Records are
  appended after the Weaviate write; when that fails the assignment stays and the response says
  `record_attribute_changes` failed. Ids not labels are stored, so renaming keeps the history.
  There is no undo of assignments yet.
- **Rename and retire, never rewrite.** Labels, descriptions and applicable tags change without
  touching annotations. A value or attribute that annotations still hold cannot be deleted (409
  with the number affected) but can be retired. Merging values (reassigning the affected
  annotations) is not implemented here.
- **The properties are added by an operator command**
  (`annotation_attributes add-schema`), never at startup or by a request; the backend reads and
  writes them only when the collection holds them (`bootstrap.detect_attributes`). Without them
  definitions work and assignments answer 503. They are not derived data: attribute and tag changes
  never re-embed (ADR 0009).

## Consequences

Assignments read the annotation once under its lock and write one update (two for the record
afterwards, SQL). Definitions in SQLite are part of the daily backup (#399) and, being product
data, not recoverable from Weaviate alone; a restore of Weaviate without the matching SQL database
leaves assignments whose ids have no definition (shown as unknown values, filters still exact).
Collection deletion crosses two stores (SQL first). Retagging an annotation to a tag an
attribute does not apply to keeps its values. The document view does not show attributes yet.

## Verification

Service rules with a real SQLite repository and in-memory spans (`tests/test_attributes.py`:
definitions, per-collection ids, assignment modes and rules, conflicts and retries, concurrency,
failed/uncertain writes, change records, access, collection deletion order), the filters in the
concordance service (`tests/test_annotation_concordance.py`), and real Weaviate 1.40.1
(`tests/integration/test_annotation_attributes.py`: exact filters with similar ids, several values,
empty arrays and missing properties, use counts, the API end to end, store without the
properties).
