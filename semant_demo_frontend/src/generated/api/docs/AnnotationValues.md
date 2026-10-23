
# AnnotationValues

Values of an annotation a review or boundary edit changed, as an undo puts them back (#461): only the fields that are set. ``chunk_id``, ``start`` and ``end`` are its range (offsets counted from that chunk, as ``PatchSpan``); ``chunk_id`` needs both offsets.

## Properties

Name | Type
------------ | -------------
`type` | [SpanType](SpanType.md)
`tagId` | string
`chunkId` | string
`start` | number
`end` | number

## Example

```typescript
import type { AnnotationValues } from ''

// TODO: Update the object below with actual values
const example = {
  "type": null,
  "tagId": null,
  "chunkId": null,
  "start": null,
  "end": null,
} satisfies AnnotationValues

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationValues
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


