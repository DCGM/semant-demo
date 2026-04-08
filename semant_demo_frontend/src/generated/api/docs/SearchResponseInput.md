
# SearchResponseInput


## Properties

Name | Type
------------ | -------------
`results` | [Array&lt;TextChunkWithDocumentInput&gt;](TextChunkWithDocumentInput.md)
`resultsSummary` | string
`searchRequest` | [SearchRequest](SearchRequest.md)
`timeSpent` | number
`searchLog` | Array&lt;string&gt;
`tagsResult` | [Array&lt;FilteredChunksByTags&gt;](FilteredChunksByTags.md)

## Example

```typescript
import type { SearchResponseInput } from ''

// TODO: Update the object below with actual values
const example = {
  "results": null,
  "resultsSummary": null,
  "searchRequest": null,
  "timeSpent": null,
  "searchLog": null,
  "tagsResult": null,
} satisfies SearchResponseInput

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchResponseInput
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


