
# SearchVectorsResponse


## Properties

Name | Type
------------ | -------------
`defaultVector` | string
`vectors` | [Array&lt;SearchVectorInfo&gt;](SearchVectorInfo.md)

## Example

```typescript
import type { SearchVectorsResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "defaultVector": null,
  "vectors": null,
} satisfies SearchVectorsResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchVectorsResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


