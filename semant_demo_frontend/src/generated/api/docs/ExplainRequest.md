
# ExplainRequest


## Properties

Name | Type
------------ | -------------
`ragId` | string
`selectedText` | string
`fullAnswer` | string
`history` | [Array&lt;RagChatMessage&gt;](RagChatMessage.md)
`sources` | [Array&lt;TextChunkWithDocument&gt;](TextChunkWithDocument.md)

## Example

```typescript
import type { ExplainRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "ragId": null,
  "selectedText": null,
  "fullAnswer": null,
  "history": null,
  "sources": null,
} satisfies ExplainRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ExplainRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


