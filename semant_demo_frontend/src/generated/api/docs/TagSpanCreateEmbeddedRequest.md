
# TagSpanCreateEmbeddedRequest


## Properties

Name | Type
------------ | -------------
`chunkId` | string
`tagId` | string
`spans` | [Array&lt;TagSpan&gt;](TagSpan.md)

## Example

```typescript
import type { TagSpanCreateEmbeddedRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "chunkId": null,
  "tagId": null,
  "spans": null,
} satisfies TagSpanCreateEmbeddedRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TagSpanCreateEmbeddedRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


