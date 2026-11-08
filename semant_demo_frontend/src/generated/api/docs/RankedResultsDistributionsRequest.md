
# RankedResultsDistributionsRequest

The ranked ids of one text-query search, as Documents or Passages Results hold them, with that search\'s criteria and collection. Every id once; at most the mode\'s retrieval limit (``SEARCH_DOCUMENTS_METADATA_LIMIT + SEARCH_DOCUMENTS_CHUNK_LIMIT`` documents, ``SEARCH_PASSAGES_LIMIT`` passages). A search without a text query is not a ranked result: its documents are charted by ``POST /api/analytics/corpus/distributions``, and filter-only passages are not supported.

## Properties

Name | Type
------------ | -------------
`mode` | string
`ids` | Array&lt;string&gt;
`criteria` | [SearchCriteria](SearchCriteria.md)
`userCollectionId` | string
`ranking` | [RankingDescription](RankingDescription.md)
`members` | boolean

## Example

```typescript
import type { RankedResultsDistributionsRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "mode": null,
  "ids": null,
  "criteria": null,
  "userCollectionId": null,
  "ranking": null,
  "members": null,
} satisfies RankedResultsDistributionsRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RankedResultsDistributionsRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


