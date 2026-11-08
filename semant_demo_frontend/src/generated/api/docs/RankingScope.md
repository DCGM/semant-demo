
# RankingScope

The ranking that was counted: as the client described it, with the server\'s limit.

## Properties

Name | Type
------------ | -------------
`type` | [SearchType](SearchType.md)
`vector` | string
`bounded` | boolean
`retrievalLimit` | number

## Example

```typescript
import type { RankingScope } from ''

// TODO: Update the object below with actual values
const example = {
  "type": null,
  "vector": null,
  "bounded": null,
  "retrievalLimit": null,
} satisfies RankingScope

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RankingScope
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


