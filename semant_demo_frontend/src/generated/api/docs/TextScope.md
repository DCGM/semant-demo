
# TextScope

Where the words of a lexical annotation query must occur (#663). Each word must occur inside a word of one of the scope\'s fields, ignoring case; different words may occur in different fields. Word containment, not a phrase or a literal substring. Words are runs of letters and digits of the query composed to NFC, as the corpus text is stored; stored text in decomposed form (a letter followed by a combining mark) is split at the mark by Weaviate\'s word tokenization, so such a letter cannot be searched.

## Properties

Name | Type
------------ | -------------

## Example

```typescript
import type { TextScope } from ''

// TODO: Update the object below with actual values
const example = {
} satisfies TextScope

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TextScope
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


