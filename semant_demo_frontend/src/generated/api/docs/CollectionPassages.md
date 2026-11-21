
# CollectionPassages

Counts of the passages included in a user collection (``Chunks.userCollection``, as ``CollectionStats.chunks_count`` counts them), not of the passages of its documents.

## Properties

Name | Type
------------ | -------------
`scope` | string
`userCollectionId` | string
`unit` | string
`totalPassages` | number
`computedAt` | Date
`dataSource` | string
`languages` | [CategoryDistribution](CategoryDistribution.md)
`classification` | [PassageClassification](PassageClassification.md)

## Example

```typescript
import type { CollectionPassages } from ''

// TODO: Update the object below with actual values
const example = {
  "scope": null,
  "userCollectionId": null,
  "unit": null,
  "totalPassages": null,
  "computedAt": null,
  "dataSource": null,
  "languages": null,
  "classification": null,
} satisfies CollectionPassages

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CollectionPassages
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


