
# RagResponse


## Properties

Name | Type
------------ | -------------
`ragAnswer` | string
`timeSpent` | number
`responseId` | string
`sources` | [Array&lt;TextChunkWithDocument&gt;](TextChunkWithDocument.md)

## Example

```typescript
import type { RagResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "ragAnswer": null,
  "timeSpent": null,
  "responseId": null,
  "sources": null,
} satisfies RagResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RagResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


