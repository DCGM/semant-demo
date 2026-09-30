
# SuggestSpansSelectionRequest

Request body for ``POST /api/ai/suggest_spans/selection``.  The user has highlighted a passage and asked the AI to propose tags for *only that passage*. The selection may span multiple consecutive chunks; the frontend sends the chunk IDs in document order. Offsets are measured against the concatenation of those chunks\' text:  - ``selection_start`` — char offset measured from the start of the   first chunk (so it is also the local offset inside that chunk). - ``selection_end`` — char offset across the concatenation (may   exceed the first chunk\'s length when the selection extends into   later chunks).  Resulting auto spans are anchored on the first chunk in ``chunk_ids`` with ``start`` / ``end`` in the same coordinate system, mirroring how cross-chunk user spans are stored.

## Properties

Name | Type
------------ | -------------
`collectionId` | string
`documentId` | string
`chunkIds` | Array&lt;string&gt;
`selectionStart` | number
`selectionEnd` | number
`tagIds` | Array&lt;string&gt;

## Example

```typescript
import type { SuggestSpansSelectionRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "collectionId": null,
  "documentId": null,
  "chunkIds": null,
  "selectionStart": null,
  "selectionEnd": null,
  "tagIds": null,
} satisfies SuggestSpansSelectionRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SuggestSpansSelectionRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


