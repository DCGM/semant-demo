
# SearchChatRequest

A question about search results (#245). ``chunk_ids`` are the results the page chose (the first ``MAX_SEARCH_CHAT_RESULTS`` selected or loaded ones), in result order; ``criteria`` and ``user_collection_id`` are those of the search. The server reads the passages again under them, so an id the search could not have returned is left out (ADR 0006).

## Properties

Name | Type
------------ | -------------
`question` | string
`history` | [Array&lt;ChatTurn&gt;](ChatTurn.md)
`chunkIds` | Array&lt;string&gt;
`criteria` | [SearchCriteria](SearchCriteria.md)
`userCollectionId` | string

## Example

```typescript
import type { SearchChatRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "question": null,
  "history": null,
  "chunkIds": null,
  "criteria": null,
  "userCollectionId": null,
} satisfies SearchChatRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchChatRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


