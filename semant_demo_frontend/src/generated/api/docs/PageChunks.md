
# PageChunks

The chunks whose page range (``from_page``..``to_page``) includes page ``page``, in document order, at most the requested number; ``has_more`` tells whether more do.

## Properties

Name | Type
------------ | -------------
`page` | number
`chunks` | [Array&lt;DocumentChunk&gt;](DocumentChunk.md)
`hasMore` | boolean

## Example

```typescript
import type { PageChunks } from ''

// TODO: Update the object below with actual values
const example = {
  "page": null,
  "chunks": null,
  "hasMore": null,
} satisfies PageChunks

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PageChunks
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


