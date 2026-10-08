
# TagSpanWriteResult

A created or updated span with the outcome of the write. ``succeeded`` holds the span id. ``failed`` lists chunk tag updates (``update_chunk_tags``) that did not complete: the span is saved, but tag-filtered search does not reflect it until the span is saved again.

## Properties

Name | Type
------------ | -------------
`outcome` | [WriteOutcome](WriteOutcome.md)
`succeeded` | Array&lt;string&gt;
`failed` | [Array&lt;StepFailure&gt;](StepFailure.md)
`unattempted` | Array&lt;string&gt;
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
import type { TagSpanWriteResult } from ''

// TODO: Update the object below with actual values
const example = {
  "outcome": null,
  "succeeded": null,
  "failed": null,
  "unattempted": null,
  "id": null,
  "chunkId": null,
  "tagId": null,
  "start": null,
  "end": null,
  "type": null,
  "reason": null,
  "confidence": null,
} satisfies TagSpanWriteResult

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TagSpanWriteResult
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


