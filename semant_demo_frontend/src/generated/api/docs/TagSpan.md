
# TagSpan


## Properties

Name | Type
------------ | -------------
`id` | string
`chunkId` | string
`tagId` | string
`start` | number
`end` | number
`type` | [SpanType](SpanType.md)
`reason` | string
`confidence` | number

## Example

```typescript
import type { TagSpan } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "chunkId": null,
  "tagId": null,
  "start": null,
  "end": null,
  "type": null,
  "reason": null,
  "confidence": null,
} satisfies TagSpan

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TagSpan
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


