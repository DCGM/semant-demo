
# AnnotationReviewResult

The outcome of a review action per annotation (best effort, ADR 0002; nothing is rolled back). ``succeeded``: annotations changed or deleted, and those already as the action asks. ``failed``: ``update_span`` / ``delete_span`` (``uncertain`` when the write timed out and may have been applied), ``find_annotation`` (no such annotation in the collection, e.g. deleted meanwhile), ``edit_conflict`` (written by someone else since the expected version; not changed), and best-effort steps of changed annotations whose change was saved (``derive_annotation``, ``embed_annotation``). ``versions``: the ``editVersion`` of each changed annotation after the action, and the current one of each conflicting annotation. ``previous``: for each annotation the action changed, the values it changed as they were before, which ``annotations/restore`` puts back (undo, #461); none for a deletion.

## Properties

Name | Type
------------ | -------------
`outcome` | [WriteOutcome](WriteOutcome.md)
`succeeded` | Array&lt;string&gt;
`failed` | [Array&lt;StepFailure&gt;](StepFailure.md)
`unattempted` | Array&lt;string&gt;
`versions` | { [key: string]: number; }
`previous` | [{ [key: string]: AnnotationValues; }](AnnotationValues.md)

## Example

```typescript
import type { AnnotationReviewResult } from ''

// TODO: Update the object below with actual values
const example = {
  "outcome": null,
  "succeeded": null,
  "failed": null,
  "unattempted": null,
  "versions": null,
  "previous": null,
} satisfies AnnotationReviewResult

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationReviewResult
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


