
# ChunkTagSyncRequest

(chunk, tag) pairs of the collection\'s tags whose tag-filtered search references to re-derive: the items of ``update_chunk_tags`` failures (``chunk_id:tag_id``).

## Properties

Name | Type
------------ | -------------
`pairs` | [Array&lt;ChunkTagPair&gt;](ChunkTagPair.md)

## Example

```typescript
import type { ChunkTagSyncRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "pairs": null,
} satisfies ChunkTagSyncRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ChunkTagSyncRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


