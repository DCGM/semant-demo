
# RankedResultsDistributions

Counts of exactly the ranked results named by the request that are still eligible: never the corpus, never another search. ``total_count`` results in ``unit`` were counted; ``input_count - total_count`` (``missing_count``) were named but are gone, no longer match the criteria, or are outside the collection or access. For each available dimension the counts add up to ``total_count`` (``sum(values or years) + other_count + unknown_count``).

## Properties

Name | Type
------------ | -------------
`scope` | string
`mode` | string
`unit` | string
`criteria` | [SearchCriteria](SearchCriteria.md)
`ranking` | [RankingScope](RankingScope.md)
`inputCount` | number
`totalCount` | number
`missingCount` | number
`distinctDocuments` | number
`computedAt` | Date
`publicationYear` | [PublicationYearCounts](PublicationYearCounts.md)
`libraries` | [CategoryDistribution](CategoryDistribution.md)
`languages` | [CategoryDistribution](CategoryDistribution.md)
`members` | [Array&lt;ResultMember&gt;](ResultMember.md)

## Example

```typescript
import type { RankedResultsDistributions } from ''

// TODO: Update the object below with actual values
const example = {
  "scope": null,
  "mode": null,
  "unit": null,
  "criteria": null,
  "ranking": null,
  "inputCount": null,
  "totalCount": null,
  "missingCount": null,
  "distinctDocuments": null,
  "computedAt": null,
  "publicationYear": null,
  "libraries": null,
  "languages": null,
  "members": null,
} satisfies RankedResultsDistributions

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RankedResultsDistributions
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


