
# PublicationYearDistribution

Documents per decade of ``Documents.yearIssued``; bins run without gaps from the earliest to the latest represented decade (empty decades have count 0).

## Properties

Name | Type
------------ | -------------
`available` | boolean
`unavailableReason` | string
`binWidthYears` | number
`bins` | [Array&lt;YearBin&gt;](YearBin.md)
`unknownCount` | number

## Example

```typescript
import type { PublicationYearDistribution } from ''

// TODO: Update the object below with actual values
const example = {
  "available": null,
  "unavailableReason": null,
  "binWidthYears": null,
  "bins": null,
  "unknownCount": null,
} satisfies PublicationYearDistribution

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PublicationYearDistribution
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


