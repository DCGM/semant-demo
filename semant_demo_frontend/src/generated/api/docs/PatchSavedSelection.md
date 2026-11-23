
# PatchSavedSelection

Renames a saved selection and/or replaces its query.

## Properties

Name | Type
------------ | -------------
`name` | string
`query` | [LiveQuery](LiveQuery.md)

## Example

```typescript
import type { PatchSavedSelection } from ''

// TODO: Update the object below with actual values
const example = {
  "name": null,
  "query": null,
} satisfies PatchSavedSelection

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PatchSavedSelection
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


