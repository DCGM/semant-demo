
# DiscussSpanRequest

Request body for ``POST /api/ai/discuss_span``.  The frontend sends the full chat history each call (the new user turn is the last message). The backend resolves span / document / tag / chunk context server-side and prepends it as a system message.

## Properties

Name | Type
------------ | -------------
`spanId` | string
`collectionId` | string
`messages` | [Array&lt;SpanChatMessage&gt;](SpanChatMessage.md)

## Example

```typescript
import type { DiscussSpanRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "spanId": null,
  "collectionId": null,
  "messages": null,
} satisfies DiscussSpanRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DiscussSpanRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


