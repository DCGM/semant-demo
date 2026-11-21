
# DeleteAutoSpansRequest

Delete unresolved suggestions by tag (Clear unresolved) or by selected span ids.

## Properties

Name | Type
------------ | -------------
`collectionId` | string
`documentId` | string
`tagIds` | Array&lt;string&gt;
`spanIds` | Array&lt;string&gt;
`expectedVersions` | { [key: string]: number; }

## Example

```typescript
import type { DeleteAutoSpansRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "collectionId": null,
  "documentId": null,
  "tagIds": null,
  "spanIds": null,
  "expectedVersions": null,
} satisfies DeleteAutoSpansRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DeleteAutoSpansRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


