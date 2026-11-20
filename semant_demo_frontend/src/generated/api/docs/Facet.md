
# Facet


## Properties

Name | Type
------------ | -------------
`facet` | string
`values` | [Array&lt;FacetValue&gt;](FacetValue.md)
`missing` | number
`total` | number
`distinct` | number
`truncated` | boolean

## Example

```typescript
import type { Facet } from ''

// TODO: Update the object below with actual values
const example = {
  "facet": null,
  "values": null,
  "missing": null,
  "total": null,
  "distinct": null,
  "truncated": null,
} satisfies Facet

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as Facet
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


