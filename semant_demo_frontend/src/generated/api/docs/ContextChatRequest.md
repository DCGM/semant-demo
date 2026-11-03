
# ContextChatRequest


## Properties

Name | Type
------------ | -------------
`question` | string
`history` | [Array&lt;ChatTurn&gt;](ChatTurn.md)

## Example

```typescript
import type { ContextChatRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "question": null,
  "history": null,
} satisfies ContextChatRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ContextChatRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


