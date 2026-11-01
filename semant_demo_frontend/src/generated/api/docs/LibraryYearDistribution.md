
# LibraryYearDistribution

The documents matching ``filters`` per source library and publication year: a document is counted in exactly one row and, with a valid year, in one year of it. The rows add up to ``total_documents``, and each year\'s counts add up to that year in the distributions.

## Properties

Name | Type
------------ | -------------
`scope` | string
`unit` | string
`filters` | [DocumentFilters](DocumentFilters.md)
`chunkFilters` | [ChunkFilters](ChunkFilters.md)
`totalDocuments` | number
`computedAt` | Date
`available` | boolean
`unavailableReason` | string
`unavailableProperty` | string
`rows` | [Array&lt;LibraryYears&gt;](LibraryYears.md)

## Example

```typescript
import type { LibraryYearDistribution } from ''

// TODO: Update the object below with actual values
const example = {
  "scope": null,
  "unit": null,
  "filters": null,
  "chunkFilters": null,
  "totalDocuments": null,
  "computedAt": null,
  "available": null,
  "unavailableReason": null,
  "unavailableProperty": null,
  "rows": null,
} satisfies LibraryYearDistribution

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as LibraryYearDistribution
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


