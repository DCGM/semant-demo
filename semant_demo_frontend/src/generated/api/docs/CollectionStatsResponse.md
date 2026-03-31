
# CollectionStatsResponse


## Properties

Name | Type
------------ | -------------
`collectionId` | string
`documentsCount` | number
`chunksCount` | number
`annotationsCount` | number
`tagsCount` | number

## Example

```typescript
import type { CollectionStatsResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "collectionId": null,
  "documentsCount": null,
  "chunksCount": null,
  "annotationsCount": null,
  "tagsCount": null,
} satisfies CollectionStatsResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CollectionStatsResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


