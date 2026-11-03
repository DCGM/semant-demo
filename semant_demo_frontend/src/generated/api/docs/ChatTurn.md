
# ChatTurn

An earlier turn of the conversation.  ``chunk_ids`` (assistant turns): the chunks its citations refer to, ``[docK]`` in ``text`` citing ``chunk_ids[K - 1]``. The server renumbers them for the current request and removes citations of chunks outside the scope; it never reads text from them.

## Properties

Name | Type
------------ | -------------
`role` | string
`text` | string
`chunkIds` | Array&lt;string&gt;

## Example

```typescript
import type { ChatTurn } from ''

// TODO: Update the object below with actual values
const example = {
  "role": null,
  "text": null,
  "chunkIds": null,
} satisfies ChatTurn

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ChatTurn
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


