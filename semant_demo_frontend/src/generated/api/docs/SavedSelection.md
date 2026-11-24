
# SavedSelection

A named, server-side research selection of one collection. Every reader of the collection sees it; its creator and the collection owner may rename, replace or delete it.

## Properties

Name | Type
------------ | -------------
`id` | string
`collectionId` | string
`kind` | [SavedSelectionKind](SavedSelectionKind.md)
`name` | string
`query` | [LiveQuery](LiveQuery.md)
`unreadable` | boolean
`createdBy` | string
`createdAt` | Date
`updatedBy` | string
`updatedAt` | Date
`canEdit` | boolean

## Example

```typescript
import type { SavedSelection } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "collectionId": null,
  "kind": null,
  "name": null,
  "query": null,
  "unreadable": null,
  "createdBy": null,
  "createdAt": null,
  "updatedBy": null,
  "updatedAt": null,
  "canEdit": null,
} satisfies SavedSelection

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SavedSelection
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


