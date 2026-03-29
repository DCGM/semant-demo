
# RagSearch


## Properties

Name | Type
------------ | -------------
`searchType` | [SearchType](SearchType.md)
`alpha` | number
`limit` | number
`searchQuery` | string
`minYear` | number
`maxYear` | number
`minDate` | Date
`maxDate` | Date
`language` | string

## Example

```typescript
import type { RagSearch } from ''

// TODO: Update the object below with actual values
const example = {
  "searchType": null,
  "alpha": null,
  "limit": null,
  "searchQuery": null,
  "minYear": null,
  "maxYear": null,
  "minDate": null,
  "maxDate": null,
  "language": null,
} satisfies RagSearch

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RagSearch
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


