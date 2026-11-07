
# PassageSearchResponse

The ranking of one passage search, its first page and what the ranking covers.  The search ranks at most ``retrieval_limit`` passages once (best first, ``ranked_ids``); later pages read slices of those ids (``POST /api/search/passages/read``) instead of ranking again, and visualizations of the same search can describe the same population. ``bounded`` is ``False`` when the ranking holds every matching passage (then ``total_count`` is their number) and ``True`` when the limit cut it (more passages match but are not retrievable). Vector and hybrid search rank every passage that passes the filters, so they are bounded unless the filters leave fewer than the limit.

## Properties

Name | Type
------------ | -------------
`rankedIds` | Array&lt;string&gt;
`items` | [Array&lt;SearchResultChunk&gt;](SearchResultChunk.md)
`readCount` | number
`retrievalLimit` | number
`bounded` | boolean
`totalCount` | number
`criteria` | [SearchCriteria](SearchCriteria.md)
`vector` | string
`timeSpent` | number

## Example

```typescript
import type { PassageSearchResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "rankedIds": null,
  "items": null,
  "readCount": null,
  "retrievalLimit": null,
  "bounded": null,
  "totalCount": null,
  "criteria": null,
  "vector": null,
  "timeSpent": null,
} satisfies PassageSearchResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PassageSearchResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


