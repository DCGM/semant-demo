
# SearchCriteria

The submitted query and filters shared by Search, document browsing and Analytics (docs/EXPLORATION.md). Retrieval settings belong to each endpoint\'s request.

## Properties

Name | Type
------------ | -------------
`textQuery` | string
`documentFilters` | [DocumentFilters](DocumentFilters.md)
`chunkFilters` | [ChunkFilters](ChunkFilters.md)

## Example

```typescript
import type { SearchCriteria } from ''

// TODO: Update the object below with actual values
const example = {
  "textQuery": null,
  "documentFilters": null,
  "chunkFilters": null,
} satisfies SearchCriteria

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchCriteria
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


