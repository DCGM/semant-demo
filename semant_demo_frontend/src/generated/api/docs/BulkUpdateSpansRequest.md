
# BulkUpdateSpansRequest

Request body for bulk-applying the same :class:`PatchSpan` patch to many spans in a single round-trip. Used by the AI-assist \"Approve / Reject all selected\" action so the frontend doesn\'t have to fan out N PATCH calls. All spans must belong to ``collection_id``.

## Properties

Name | Type
------------ | -------------
`collectionId` | string
`spanIds` | Array&lt;string&gt;
`update` | [PatchSpan](PatchSpan.md)
`expectedVersions` | { [key: string]: number; }

## Example

```typescript
import type { BulkUpdateSpansRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "collectionId": null,
  "spanIds": null,
  "update": null,
  "expectedVersions": null,
} satisfies BulkUpdateSpansRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as BulkUpdateSpansRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


