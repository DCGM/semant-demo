
# DocumentSummaryCitation

A chunk the document summary cites as ``[docN]``, N being this citation\'s 1-based position in :attr:`DocumentSummaryResponse.citations`.

## Properties

Name | Type
------------ | -------------
`chunkId` | string
`order` | number
`fromPage` | number
`toPage` | number

## Example

```typescript
import type { DocumentSummaryCitation } from ''

// TODO: Update the object below with actual values
const example = {
  "chunkId": null,
  "order": null,
  "fromPage": null,
  "toPage": null,
} satisfies DocumentSummaryCitation

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentSummaryCitation
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


