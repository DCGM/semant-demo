
# AppFeedbackRequest


## Properties

Name | Type
------------ | -------------
`type` | string
`subject` | string
`message` | string
`email` | string

## Example

```typescript
import type { AppFeedbackRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "type": null,
  "subject": null,
  "message": null,
  "email": null,
} satisfies AppFeedbackRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AppFeedbackRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


