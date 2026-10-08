
# SearchResponse


## Properties

Name | Type
------------ | -------------
`results` | [Array&lt;TextChunkWithDocument&gt;](TextChunkWithDocument.md)
`resultsSummary` | string
`searchRequest` | [SearchRequest](SearchRequest.md)
`timeSpent` | number
`searchLog` | Array&lt;string&gt;
`warnings` | Array&lt;string&gt;

## Example

```typescript
import type { SearchResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "results": null,
  "resultsSummary": null,
  "searchRequest": null,
  "timeSpent": null,
  "searchLog": null,
  "warnings": null,
} satisfies SearchResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


