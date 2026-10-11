
# AdjacentChunks

Chunks directly before or after a chunk of a corpus document, in document order, without the chunk itself (public). Extends a :class:`DocumentChunkWindow` without reading the document metadata or chunk count again. ``has_more`` tells whether the document continues beyond them in that direction.

## Properties

Name | Type
------------ | -------------
`chunks` | [Array&lt;TextChunk&gt;](TextChunk.md)
`hasMore` | boolean

## Example

```typescript
import type { AdjacentChunks } from ''

// TODO: Update the object below with actual values
const example = {
  "chunks": null,
  "hasMore": null,
} satisfies AdjacentChunks

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AdjacentChunks
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


