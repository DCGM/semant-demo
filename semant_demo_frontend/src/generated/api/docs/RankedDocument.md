
# RankedDocument

One document of a text query\'s ranking: why it matched and its best-matching chunk, if any.

## Properties

Name | Type
------------ | -------------
`id` | string
`match` | string
`chunkId` | string

## Example

```typescript
import type { RankedDocument } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "match": null,
  "chunkId": null,
} satisfies RankedDocument

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RankedDocument
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


