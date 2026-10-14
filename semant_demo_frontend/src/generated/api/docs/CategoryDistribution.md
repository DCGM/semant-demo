
# CategoryDistribution

Documents per stored value of one document property, most documents first.

## Properties

Name | Type
------------ | -------------
`available` | boolean
`unavailableReason` | string
`values` | [Array&lt;CategoryCount&gt;](CategoryCount.md)
`otherCount` | number
`unknownCount` | number

## Example

```typescript
import type { CategoryDistribution } from ''

// TODO: Update the object below with actual values
const example = {
  "available": null,
  "unavailableReason": null,
  "values": null,
  "otherCount": null,
  "unknownCount": null,
} satisfies CategoryDistribution

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CategoryDistribution
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


