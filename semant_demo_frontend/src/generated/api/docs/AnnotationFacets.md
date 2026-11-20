
# AnnotationFacets

Facet counts of an annotation query (#667). ``population``: what is counted. With ``filtered`` every facet is counted with the query\'s filter on that same facet removed (``self_exclusion``), so the other choices of an active filter stay visible; with ``top_k`` the fixed top ``k`` set is counted as it is. Multi-valued attributes count an annotation once per value it holds, so value counts may add up to more than ``total``.

## Properties

Name | Type
------------ | -------------
`population` | [FacetPopulation](FacetPopulation.md)
`selfExclusion` | boolean
`k` | number
`facets` | [Array&lt;Facet&gt;](Facet.md)

## Example

```typescript
import type { AnnotationFacets } from ''

// TODO: Update the object below with actual values
const example = {
  "population": null,
  "selfExclusion": null,
  "k": null,
  "facets": null,
} satisfies AnnotationFacets

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationFacets
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


