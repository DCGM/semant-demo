
# ResultMember

One counted result and the values it is counted under, in ranking order.

## Properties

Name | Type
------------ | -------------
`id` | string
`documentId` | string
`year` | number
`library` | string
`language` | string

## Example

```typescript
import type { ResultMember } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "documentId": null,
  "year": null,
  "library": null,
  "language": null,
} satisfies ResultMember

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ResultMember
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


