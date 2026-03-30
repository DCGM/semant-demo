
# CollectionResponse


## Properties

Name | Type
------------ | -------------
`id` | string
`name` | string
`userId` | string
`description` | string
`createdAt` | Date
`updatedAt` | Date
`color` | string

## Example

```typescript
import type { CollectionResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "name": null,
  "userId": null,
  "description": null,
  "createdAt": null,
  "updatedAt": null,
  "color": null,
} satisfies CollectionResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CollectionResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


