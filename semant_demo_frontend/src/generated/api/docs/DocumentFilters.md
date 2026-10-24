
# DocumentFilters

Which documents to count; every given filter must match (AND), and a document matching any of the listed titles, libraries (or languages) matches that filter (OR). No filters: every document. Echoed in the response normalized: trimmed, de-duplicated and sorted, with each title reduced to the words actually searched.

## Properties

Name | Type
------------ | -------------
`yearMin` | number
`yearMax` | number
`titleContains` | Array&lt;string&gt;
`libraries` | Array&lt;string&gt;
`languages` | Array&lt;string&gt;

## Example

```typescript
import type { DocumentFilters } from ''

// TODO: Update the object below with actual values
const example = {
  "yearMin": null,
  "yearMax": null,
  "titleContains": null,
  "libraries": null,
  "languages": null,
} satisfies DocumentFilters

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentFilters
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


