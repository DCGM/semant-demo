
# SearchRequest


## Properties

Name | Type
------------ | -------------
`searchTitleGenerate` | boolean
`searchTitlePrompt` | string
`searchTitleModel` | string
`searchTitleBrevity` | number
`searchSummaryGenerate` | boolean
`searchSummaryPrompt` | string
`searchSummaryModel` | string
`searchSummaryBrevity` | number
`searchResultsSummaryGenerate` | boolean
`searchResultsSummaryPrompt` | string
`searchResultsSummaryModel` | string
`searchResultsSummaryBrevity` | number
`query` | string
`limit` | number
`type` | [SearchType](SearchType.md)
`hybridSearchAlpha` | number
`searchLlmFilter` | boolean
`minYear` | number
`maxYear` | number
`minDate` | Date
`maxDate` | Date
`language` | string
`tagUuids` | Array&lt;string&gt;
`positive` | boolean
`automatic` | boolean
`isHyde` | boolean

## Example

```typescript
import type { SearchRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "searchTitleGenerate": null,
  "searchTitlePrompt": null,
  "searchTitleModel": null,
  "searchTitleBrevity": null,
  "searchSummaryGenerate": null,
  "searchSummaryPrompt": null,
  "searchSummaryModel": null,
  "searchSummaryBrevity": null,
  "searchResultsSummaryGenerate": null,
  "searchResultsSummaryPrompt": null,
  "searchResultsSummaryModel": null,
  "searchResultsSummaryBrevity": null,
  "query": null,
  "limit": null,
  "type": null,
  "hybridSearchAlpha": null,
  "searchLlmFilter": null,
  "minYear": null,
  "maxYear": null,
  "minDate": null,
  "maxDate": null,
  "language": null,
  "tagUuids": null,
  "positive": null,
  "automatic": null,
  "isHyde": null,
} satisfies SearchRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


