
# LiveQuery

What a live filter keeps: the annotation query (#663) and how the workspace lists it.  A Find similar source is not kept (it names one annotation); a similarity text is, as ``filters.ranking_query`` (#716), so opening ranks again by it.

## Properties

Name | Type
------------ | -------------
`filters` | [AnnotationFilters](AnnotationFilters.md)
`sort` | [AnnotationSort](AnnotationSort.md)
`sortAttribute` | string
`descending` | boolean
`shownAttributeIds` | Array&lt;string&gt;

## Example

```typescript
import type { LiveQuery } from ''

// TODO: Update the object below with actual values
const example = {
  "filters": null,
  "sort": null,
  "sortAttribute": null,
  "descending": null,
  "shownAttributeIds": null,
} satisfies LiveQuery

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as LiveQuery
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


