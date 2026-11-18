
# AnnotationFacetsRequest

The annotation query whose facet counts to compute (#667): the filters of #663, the retrieval ``ranking`` of #664 and the ``facets`` wanted: ``tag``, ``type``, ``document``, ``year``, ``library``, ``language`` and ``attribute:<attribute id>``.

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
`near` | [NearFilter](NearFilter.md)
`facets` | Array&lt;string&gt;
`ranking` | [AnnotationRanking](AnnotationRanking.md)

## Example

```typescript
import type { AnnotationFacetsRequest } from ''

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
  "near": null,
  "facets": null,
  "ranking": null,
} satisfies AnnotationFacetsRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationFacetsRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


