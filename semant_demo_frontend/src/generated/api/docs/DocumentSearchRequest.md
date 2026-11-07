
# DocumentSearchRequest

Documents matching search criteria without a text query (#606, docs/EXPLORATION.md), one page of them in a stable order.  Document filters hold on the document. Chunk filters apply per dimension: for each, some chunk of the document has one of its values (different filters may be met by different chunks), answered from the documents\' chunk-value summaries as last recomputed (#529). Ranking documents by a text query is not available (#527): ``criteria.text_query`` must be absent. Without ``user_collection_id`` the public corpus is browsed, also anonymously.

## Properties

Name | Type
------------ | -------------
`criteria` | [SearchCriteria](SearchCriteria.md)
`limit` | number
`offset` | number
`userCollectionId` | string

## Example

```typescript
import type { DocumentSearchRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "criteria": null,
  "limit": null,
  "offset": null,
  "userCollectionId": null,
} satisfies DocumentSearchRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentSearchRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


