
# PassageSearchRequest

A passage search (#605, #611, docs/EXPLORATION.md): its ranking and first page.  The criteria need a text query: filter-only browsing of passages is deferred. Every chunk filter holds on the returned chunk itself (same-chunk) and every document filter on its document. The remaining fields are retrieval options, not criteria. Without ``user_collection_id`` the public corpus is searched, also anonymously.

## Properties

Name | Type
------------ | -------------
`criteria` | [SearchCriteria](SearchCriteria.md)
`limit` | number
`type` | [SearchType](SearchType.md)
`hybridSearchAlpha` | number
`vector` | string
`userCollectionId` | string

## Example

```typescript
import type { PassageSearchRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "criteria": null,
  "limit": null,
  "type": null,
  "hybridSearchAlpha": null,
  "vector": null,
  "userCollectionId": null,
} satisfies PassageSearchRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PassageSearchRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


