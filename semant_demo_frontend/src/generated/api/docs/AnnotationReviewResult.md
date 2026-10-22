
# AnnotationReviewResult

The outcome of a review action per annotation (best effort, ADR 0002; nothing is rolled back). ``succeeded``: annotations changed or deleted, and those already as the action asks. ``failed``: ``update_span`` / ``delete_span`` (``uncertain`` when the write timed out and may have been applied), ``find_annotation`` (no such annotation in the collection, e.g. deleted meanwhile), ``edit_conflict`` (written by someone else since the expected version; not changed) and ``update_chunk_tags`` (item ``chunk_id:tag_id``: the change was saved, tag-filtered search does not reflect it; ``annotations/chunk-tags/sync`` with that pair repairs it, also after a deletion). ``versions``: the ``editVersion`` of each changed annotation after the action, and the current one of each conflicting annotation.

## Properties

Name | Type
------------ | -------------
`outcome` | [WriteOutcome](WriteOutcome.md)
`succeeded` | Array&lt;string&gt;
`failed` | [Array&lt;StepFailure&gt;](StepFailure.md)
`unattempted` | Array&lt;string&gt;
`versions` | { [key: string]: number; }

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


