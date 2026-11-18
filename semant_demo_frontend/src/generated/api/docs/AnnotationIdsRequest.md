
# AnnotationIdsRequest

The annotation query whose matching annotation ids to resolve (#459). ``within``: only these annotations, to learn which members of a selection the filters show.

## Properties

Name | Type
------------ | -------------
`tagIds` | Array&lt;string&gt;
`types` | [Array&lt;SpanType&gt;](SpanType.md)
`q` | string
`rankingQuery` | string
`textScope` | [TextScope](TextScope.md)
`documentIds` | Array&lt;string&gt;
`documentFilters` | [DocumentFilters](DocumentFilters.md)
`attributeValues` | Array&lt;string&gt;
`attributeUnassigned` | Array&lt;string&gt;
`within` | Array&lt;string&gt;
`ranking` | [AnnotationRanking](AnnotationRanking.md)

## Example

```typescript
import type { AnnotationIdsRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "tagIds": null,
  "types": null,
  "q": null,
  "rankingQuery": null,
  "textScope": null,
  "documentIds": null,
  "documentFilters": null,
  "attributeValues": null,
  "attributeUnassigned": null,
  "within": null,
  "ranking": null,
} satisfies AnnotationIdsRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationIdsRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


