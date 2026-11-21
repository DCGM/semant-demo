
# CollectionPassagesRequest

The included passages of one user collection: without ``dimension`` their total and detected languages, with it their values of that classification (and the total) only, so choosing another dimension never counts the rest again.

## Properties

Name | Type
------------ | -------------
`userCollectionId` | string
`dimension` | string

## Example

```typescript
import type { CollectionPassagesRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "userCollectionId": null,
  "dimension": null,
} satisfies CollectionPassagesRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CollectionPassagesRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


