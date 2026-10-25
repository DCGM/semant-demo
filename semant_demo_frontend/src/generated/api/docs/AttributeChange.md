
# AttributeChange

What the change record of one annotation and attribute holds (#331); immutable once written, readable without the current definitions.

## Properties

Name | Type
------------ | -------------
`id` | number
`annotationId` | string
`attributeId` | string
`attributeName` | string
`previous` | [Array&lt;AttributeChangeValue&gt;](AttributeChangeValue.md)
`current` | [Array&lt;AttributeChangeValue&gt;](AttributeChangeValue.md)
`actorId` | string
`at` | Date
`source` | [AssignSource](AssignSource.md)
`runId` | string
`annotationEditVersion` | number
`attributeRevision` | number

## Example

```typescript
import type { AttributeChange } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "annotationId": null,
  "attributeId": null,
  "attributeName": null,
  "previous": null,
  "current": null,
  "actorId": null,
  "at": null,
  "source": null,
  "runId": null,
  "annotationEditVersion": null,
  "attributeRevision": null,
} satisfies AttributeChange

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AttributeChange
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


