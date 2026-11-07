
# DocumentSearchResponse

One page of the documents matching the criteria and the whole population they belong to.  ``total_count`` is the exact number of matching documents (a count, not an estimate or a sample). Weaviate reads no result past ``offset + limit = QUERY_MAXIMUM_RESULTS``, so only the first ``retrieval_limit`` documents in ``order`` can be paged through; ``bounded`` is ``True`` when more match than that (narrow the filters to reach the others). A chart of the population counts ``total_count`` documents (#528), not the page.

## Properties

Name | Type
------------ | -------------
`items` | [Array&lt;Document&gt;](Document.md)
`offset` | number
`nextOffset` | number
`totalCount` | number
`retrievalLimit` | number
`bounded` | boolean
`order` | string
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
  "retrievalLimit": null,
  "bounded": null,
  "order": null,
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


