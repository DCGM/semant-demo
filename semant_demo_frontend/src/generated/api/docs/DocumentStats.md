
# DocumentStats


## Properties

Name | Type
------------ | -------------
`documentId` | string
`collectionId` | string
`chunksInCollection` | number
`totalChunks` | number
`annotationsCount` | number
`distinctTagsCount` | number

## Example

```typescript
import type { DocumentStats } from ''

// TODO: Update the object below with actual values
const example = {
  "documentId": null,
  "collectionId": null,
  "chunksInCollection": null,
  "totalChunks": null,
  "annotationsCount": null,
  "distinctTagsCount": null,
} satisfies DocumentStats

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentStats
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


