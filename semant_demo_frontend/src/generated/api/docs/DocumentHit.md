
# DocumentHit

A document result: the document, and for a text query why it matched and its best chunk.

## Properties

Name | Type
------------ | -------------
`document` | [Document](Document.md)
`match` | string
`chunk` | [SearchResultChunk](SearchResultChunk.md)

## Example

```typescript
import type { DocumentHit } from ''

// TODO: Update the object below with actual values
const example = {
  "document": null,
  "match": null,
  "chunk": null,
} satisfies DocumentHit

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentHit
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


