
# DocumentReadResponse


## Properties

Name | Type
------------ | -------------
`items` | [Array&lt;DocumentHit&gt;](DocumentHit.md)
`timeSpent` | number

## Example

```typescript
import type { DocumentReadResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "items": null,
  "timeSpent": null,
} satisfies DocumentReadResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentReadResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


