
# RankingDescription

How the search ranked the ids, as its answer reported it (``DocumentSearchResponse``: ``retrieval.type``, ``retrieval.vector``, ``bounded``; ``PassageSearchResponse``: the request\'s ``type``, ``vector``, ``bounded``). It describes the population and is echoed; it is not trusted for access or eligibility, which are checked again.

## Properties

Name | Type
------------ | -------------
`type` | [SearchType](SearchType.md)
`vector` | string
`bounded` | boolean

## Example

```typescript
import type { RankingDescription } from ''

// TODO: Update the object below with actual values
const example = {
  "type": null,
  "vector": null,
  "bounded": null,
} satisfies RankingDescription

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as RankingDescription
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


