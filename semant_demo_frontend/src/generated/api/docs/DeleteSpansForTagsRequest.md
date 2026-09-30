
# DeleteSpansForTagsRequest

Request body for bulk deletion of every span for the given tags within a single (collection, document) scope, regardless of ``type``.

## Properties

Name | Type
------------ | -------------
`collectionId` | string
`documentId` | string
`tagIds` | Array&lt;string&gt;

## Example

```typescript
import type { DeleteSpansForTagsRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "collectionId": null,
  "documentId": null,
  "tagIds": null,
} satisfies DeleteSpansForTagsRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DeleteSpansForTagsRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


