
# AnnotationPage

One page of a collection\'s concordance rows and the number of all rows of the result: every match (``complete``) or the ranked top ``k`` (``top_k``), in relevance order then id.

## Properties

Name | Type
------------ | -------------
`rows` | [Array&lt;AnnotationListRow&gt;](AnnotationListRow.md)
`total` | number
`offset` | number
`limit` | number
`result` | [AnnotationResultSet](AnnotationResultSet.md)
`unsortable` | number

## Example

```typescript
import type { AnnotationPage } from ''

// TODO: Update the object below with actual values
const example = {
  "rows": null,
  "total": null,
  "offset": null,
  "limit": null,
  "result": null,
  "unsortable": null,
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


