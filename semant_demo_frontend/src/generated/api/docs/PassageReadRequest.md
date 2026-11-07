
# PassageReadRequest

Passages of an earlier passage search by id (#611): a later page of its ``ranked_ids``.  ``criteria`` and ``user_collection_id`` are those of the search. Access is checked again and the passages are read under the same restrictions as the search\'s ranking (the text query ranks nothing here), so an id the search could not have returned is never answered.

## Properties

Name | Type
------------ | -------------
`ids` | Array&lt;string&gt;
`criteria` | [SearchCriteria](SearchCriteria.md)
`userCollectionId` | string

## Example

```typescript
import type { PassageReadRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "ids": null,
  "criteria": null,
  "userCollectionId": null,
} satisfies PassageReadRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PassageReadRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


