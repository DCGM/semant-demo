
# SearchVectorInfo

A configured search vector as clients see it (``vectors.py``).

## Properties

Name | Type
------------ | -------------
`id` | string
`name` | string
`description` | string

## Example

```typescript
import type { SearchVectorInfo } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "name": null,
  "description": null,
} satisfies SearchVectorInfo

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchVectorInfo
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


