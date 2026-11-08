
# DocumentSearchResponse

The documents matching the criteria: one page and what the whole result covers.  ``eligible_count`` is the exact number of documents the filters admit (a count, not an estimate or a sample). Without a text query those are the results: ``total_count`` equals it and the first ``retrieval_limit`` of them in ``order`` can be paged through by ``offset`` (Weaviate reads no result past ``QUERY_MAXIMUM_RESULTS``); ``bounded`` when more match.  With a text query, ``ranked`` is its bounded ranking of distinct documents and ``items`` its first ``read_count`` entries in full. ``bounded`` is ``True`` when a retrieval limit (``retrieval``) cut it; ``total_count`` is the number of matching documents only when it did not (then every eligible document that matches is ranked), else None: the ranking is a lower bound and ``eligible_count`` an upper one. A chart of the result counts ``total_count`` documents without a text query and the ranked documents with one (#528), never the page.

## Properties

Name | Type
------------ | -------------
`items` | [Array&lt;DocumentHit&gt;](DocumentHit.md)
`offset` | number
`nextOffset` | number
`totalCount` | number
`eligibleCount` | number
`retrievalLimit` | number
`bounded` | boolean
`order` | string
`ranked` | [Array&lt;RankedDocument&gt;](RankedDocument.md)
`readCount` | number
`retrieval` | [DocumentRetrieval](DocumentRetrieval.md)
`criteria` | [SearchCriteria](SearchCriteria.md)
`timeSpent` | number

## Example

```typescript
import type { DocumentSearchResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "items": null,
  "offset": null,
  "nextOffset": null,
  "totalCount": null,
  "eligibleCount": null,
  "retrievalLimit": null,
  "bounded": null,
  "order": null,
  "ranked": null,
  "readCount": null,
  "retrieval": null,
  "criteria": null,
  "timeSpent": null,
} satisfies DocumentSearchResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentSearchResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


