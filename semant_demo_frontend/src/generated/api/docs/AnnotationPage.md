
# AnnotationPage

One page of a collection\'s concordance rows and the number of all matching rows.

## Properties

Name | Type
------------ | -------------
`rows` | [Array&lt;AnnotationListRow&gt;](AnnotationListRow.md)
`total` | number
`offset` | number
`limit` | number

## Example

```typescript
import type { AnnotationPage } from ''

// TODO: Update the object below with actual values
const example = {
  "rows": null,
  "total": null,
  "offset": null,
  "limit": null,
} satisfies AnnotationPage

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationPage
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


