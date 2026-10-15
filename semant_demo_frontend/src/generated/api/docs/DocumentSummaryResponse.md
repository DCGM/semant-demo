
# DocumentSummaryResponse

A summary of one document (#249). Self-contained (text, citations and the document id) rather than nested inside a search-specific type, so it stays reusable as Document Chat context once #243 defines a shared transcript, without a second incompatible summary shape.  ``summarized_chunks``/``total_chunks``/``truncated`` (#358 review) let the client show a \"partial summary\" notice rather than silently presenting a summary of only the first ``chunk_limit`` chunks of a long document as if it covered the whole thing.

## Properties

Name | Type
------------ | -------------
`documentId` | string
`summary` | string
`citations` | [Array&lt;DocumentSummaryCitation&gt;](DocumentSummaryCitation.md)
`timeSpent` | number
`totalChunks` | number
`summarizedChunks` | number
`truncated` | boolean

## Example

```typescript
import type { DocumentSummaryResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "documentId": null,
  "summary": null,
  "citations": null,
  "timeSpent": null,
  "totalChunks": null,
  "summarizedChunks": null,
  "truncated": null,
} satisfies DocumentSummaryResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentSummaryResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


