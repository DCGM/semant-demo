
# PublicationYearCounts

Documents per publication year (``Documents.yearIssued``): only years with documents, ascending; the client groups them into wider bins.

## Properties

Name | Type
------------ | -------------
`available` | boolean
`unavailableReason` | string
`years` | [Array&lt;YearCount&gt;](YearCount.md)
`unknownCount` | number

## Example

```typescript
import type { PublicationYearCounts } from ''

// TODO: Update the object below with actual values
const example = {
  "available": null,
  "unavailableReason": null,
  "years": null,
  "unknownCount": null,
} satisfies PublicationYearCounts

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PublicationYearCounts
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


