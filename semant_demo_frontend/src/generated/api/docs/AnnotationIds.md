
# AnnotationIds

The ids of all annotations matching a query when it was resolved (by id); the caller keeps them as a fixed set, so later changes of the filters or annotations never widen it. ``versions``: each one\'s ``editVersion`` then, which review actions send back (#460).

## Properties

Name | Type
------------ | -------------
`ids` | Array&lt;string&gt;
`versions` | { [key: string]: number; }

## Example

```typescript
import type { AnnotationIds } from ''

// TODO: Update the object below with actual values
const example = {
  "ids": null,
  "versions": null,
} satisfies AnnotationIds

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationIds
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


