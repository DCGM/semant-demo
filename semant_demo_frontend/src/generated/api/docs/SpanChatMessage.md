
# SpanChatMessage

One message in a span-discussion chat history.

## Properties

Name | Type
------------ | -------------
`role` | string
`content` | string

## Example

```typescript
import type { SpanChatMessage } from ''

// TODO: Update the object below with actual values
const example = {
  "role": null,
  "content": null,
} satisfies SpanChatMessage

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SpanChatMessage
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


