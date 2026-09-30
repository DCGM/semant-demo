
# AutoAnnotationSuggestionRequest


## Properties

Name | Type
------------ | -------------
`chunks` | [Array&lt;TextChunk&gt;](TextChunk.md)
`tags` | [Array&lt;TagData&gt;](TagData.md)

## Example

```typescript
import type { AutoAnnotationSuggestionRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "chunks": null,
  "tags": null,
} satisfies AutoAnnotationSuggestionRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AutoAnnotationSuggestionRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


