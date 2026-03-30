
# DocumentBrowseResponse


## Properties

Name | Type
------------ | -------------
`items` | [Array&lt;DocumentResponse&gt;](DocumentResponse.md)
`nextOffset` | number
`hasMore` | boolean
`totalCount` | number

## Example

```typescript
import type { DocumentBrowseResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "items": null,
  "nextOffset": null,
  "hasMore": null,
  "totalCount": null,
} satisfies DocumentBrowseResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentBrowseResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


