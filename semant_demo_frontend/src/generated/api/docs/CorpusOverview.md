
# CorpusOverview


## Properties

Name | Type
------------ | -------------
`scope` | string
`unit` | string
`totalDocuments` | number
`computedAt` | Date
`dataSource` | string
`publicationYear` | [PublicationYearDistribution](PublicationYearDistribution.md)
`libraries` | [CategoryDistribution](CategoryDistribution.md)
`languages` | [CategoryDistribution](CategoryDistribution.md)

## Example

```typescript
import type { CorpusOverview } from ''

// TODO: Update the object below with actual values
const example = {
  "scope": null,
  "unit": null,
  "totalDocuments": null,
  "computedAt": null,
  "dataSource": null,
  "publicationYear": null,
  "libraries": null,
  "languages": null,
} satisfies CorpusOverview

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CorpusOverview
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


