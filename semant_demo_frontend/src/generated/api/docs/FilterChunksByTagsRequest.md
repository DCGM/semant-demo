
# FilterChunksByTagsRequest


## Properties

Name | Type
------------ | -------------
`chunkIds` | Array&lt;string&gt;
`tagIds` | Array&lt;string&gt;
`positive` | boolean
`automatic` | boolean

## Example

```typescript
import type { FilterChunksByTagsRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "chunkIds": null,
  "tagIds": null,
  "positive": null,
  "automatic": null,
} satisfies FilterChunksByTagsRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as FilterChunksByTagsRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


