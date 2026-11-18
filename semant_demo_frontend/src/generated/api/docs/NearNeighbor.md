
# NearNeighbor

A neighbor annotation that made a row match the proximity filter (#333), placed relative to the row\'s annotation so it can be marked in the row\'s text: ``start``/``end`` are UTF-16 offsets from the annotation\'s first character (negative: before it, in or beyond the left context; from the annotation\'s length on: in or beyond the right context). The stored contexts are the exact document text next to the annotation, so these offsets index them directly.

## Properties

Name | Type
------------ | -------------
`id` | string
`tagId` | string
`start` | number
`end` | number

## Example

```typescript
import type { NearNeighbor } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "tagId": null,
  "start": null,
  "end": null,
} satisfies NearNeighbor

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as NearNeighbor
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


