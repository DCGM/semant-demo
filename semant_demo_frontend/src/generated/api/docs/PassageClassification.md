
# PassageClassification

Included passages per value of one classification. A passage can hold several values, so the counts can add up to more than ``total_passages``.

## Properties

Name | Type
------------ | -------------
`dimension` | string
`available` | boolean
`unavailableReason` | string
`values` | [Array&lt;ClassificationValueCount&gt;](ClassificationValueCount.md)
`withoutValueCount` | number
`withoutValueApproximate` | boolean

## Example

```typescript
import type { PassageClassification } from ''

// TODO: Update the object below with actual values
const example = {
  "dimension": null,
  "available": null,
  "unavailableReason": null,
  "values": null,
  "withoutValueCount": null,
  "withoutValueApproximate": null,
} satisfies PassageClassification

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PassageClassification
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


