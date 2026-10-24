
# CorpusDistributions

The documents matching ``filters``, counted by year, library and language. All counts describe the same documents; ``total_documents`` is their number.

## Properties

Name | Type
------------ | -------------
`scope` | string
`unit` | string
`filters` | [DocumentFilters](DocumentFilters.md)
`totalDocuments` | number
`computedAt` | Date
`dataSource` | string
`publicationYear` | [PublicationYearCounts](PublicationYearCounts.md)
`libraries` | [CategoryDistribution](CategoryDistribution.md)
`languages` | [CategoryDistribution](CategoryDistribution.md)

## Example

```typescript
import type { CorpusDistributions } from ''

// TODO: Update the object below with actual values
const example = {
  "scope": null,
  "unit": null,
  "filters": null,
  "totalDocuments": null,
  "computedAt": null,
  "dataSource": null,
  "publicationYear": null,
  "libraries": null,
  "languages": null,
} satisfies CorpusDistributions

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CorpusDistributions
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


