
# DocumentRetrieval

How a text query ranked the documents, and whether each part covers everything it matches.

## Properties

Name | Type
------------ | -------------
`metadataLimit` | number
`metadataBounded` | boolean
`chunkLimit` | number
`chunkBounded` | boolean
`rankedChunks` | number
`type` | [SearchType](SearchType.md)
`vector` | string

## Example

```typescript
import type { DocumentRetrieval } from ''

// TODO: Update the object below with actual values
const example = {
  "metadataLimit": null,
  "metadataBounded": null,
  "chunkLimit": null,
  "chunkBounded": null,
  "rankedChunks": null,
  "type": null,
  "vector": null,
} satisfies DocumentRetrieval

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentRetrieval
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


