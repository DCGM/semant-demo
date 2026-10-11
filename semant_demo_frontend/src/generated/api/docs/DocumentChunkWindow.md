
# DocumentChunkWindow

A bounded passage of a corpus document around one of its chunks (public): up to the requested number of chunks before and after the anchor chunk, in document order, with the anchor included. ``text`` is the canonical stored text. ``has_before``/``has_after`` tell whether the document continues beyond the returned chunks.

## Properties

Name | Type
------------ | -------------
`document` | [Document](Document.md)
`chunks` | [Array&lt;TextChunk&gt;](TextChunk.md)
`anchorChunkId` | string
`hasBefore` | boolean
`hasAfter` | boolean
`totalChunks` | number

## Example

```typescript
import type { DocumentChunkWindow } from ''

// TODO: Update the object below with actual values
const example = {
  "document": null,
  "chunks": null,
  "anchorChunkId": null,
  "hasBefore": null,
  "hasAfter": null,
  "totalChunks": null,
} satisfies DocumentChunkWindow

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentChunkWindow
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


