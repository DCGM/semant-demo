
# PassageSearchResponse

A page of ranked passages and what the whole retrieved population covers.  One search retrieves at most ``retrieval_limit`` passages (best first); every page is a slice of that one ranking, and later visualizations of the same search describe the same population. ``bounded`` is ``False`` when it holds every matching passage (then ``total_count`` is their number) and ``True`` when the limit cut the ranking (more passages match but are not retrievable). Vector and hybrid search rank every passage that passes the filters, so they are bounded unless the filters leave fewer than the limit.

## Properties

Name | Type
------------ | -------------
`items` | [Array&lt;SearchResultChunk&gt;](SearchResultChunk.md)
`offset` | number
`nextOffset` | number
`hasMore` | boolean
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
  "items": null,
  "offset": null,
  "nextOffset": null,
  "hasMore": null,
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


