
# DocumentSearchRequest

Documents matching search criteria (#606, #607, docs/EXPLORATION.md).  The filters decide which documents are eligible: document filters hold on the document, and chunk filters apply per dimension: for each, some chunk of the document has one of its values (different filters may be met by different chunks), answered from the documents\' chunk-value summaries as last recomputed (#529). Without ``user_collection_id`` the public corpus is searched, also anonymously.  Without a text query, the eligible documents are paged in a stable order (``offset``). With one, it ranks them once, independently of the filters (``metadata_then_text``): the best chunk of a document need not satisfy the chunk filters. The answer holds the whole bounded ranking and its first ``limit`` documents; later pages are read by id (``POST /api/search/documents/read``), so ``offset`` must be 0. ``type``, ``hybrid_search_alpha`` and ``vector`` select how chunks are ranked, as for passages.

## Properties

Name | Type
------------ | -------------
`criteria` | [SearchCriteria](SearchCriteria.md)
`limit` | number
`offset` | number
`type` | [SearchType](SearchType.md)
`hybridSearchAlpha` | number
`vector` | string
`userCollectionId` | string

## Example

```typescript
import type { DocumentSearchRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "criteria": null,
  "limit": null,
  "offset": null,
  "type": null,
  "hybridSearchAlpha": null,
  "vector": null,
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


