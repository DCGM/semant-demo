
# DocumentReadRequest

Documents of an earlier text-query document search (#607): a later page of its ``ranked``.  ``criteria`` and ``user_collection_id`` are those of the search. Access is checked again and the documents are read under the same eligibility, so an entry the search could not have returned is never answered; an evidence chunk is read only when it belongs to the document.

## Properties

Name | Type
------------ | -------------
`ranked` | [Array&lt;RankedDocument&gt;](RankedDocument.md)
`criteria` | [SearchCriteria](SearchCriteria.md)
`userCollectionId` | string

## Example

```typescript
import type { DocumentReadRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "ranked": null,
  "criteria": null,
  "userCollectionId": null,
} satisfies DocumentReadRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentReadRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


