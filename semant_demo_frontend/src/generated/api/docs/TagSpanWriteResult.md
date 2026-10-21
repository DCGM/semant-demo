
# TagSpanWriteResult

A created or updated span with the outcome of the write. ``succeeded`` holds the span id. ``failed`` lists the later steps that did not complete; the span is saved either way, and saving it again retries them: ``update_chunk_tags`` (tag-filtered search does not reflect the span), ``derive_annotation`` (its stored text, context and positions could not be updated) and ``embed_annotation`` (its contextual vector could not be computed or stored; semantic search leaves the span out).

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
`editVersion` | number

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
  "editVersion": null,
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


