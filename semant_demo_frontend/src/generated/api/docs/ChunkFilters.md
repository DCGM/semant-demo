
# ChunkFilters

Which text chunks qualify: every given filter must match (AND), each by one of its values (OR). Values are the stored ones, matched as whole values (with the word-tokenization limitation of ``CategoryIn``, #533); a request may name them in any case and gets the configured spelling back (``validate_chunk_filters``). Missing values cannot be selected. Normalized: trimmed, de-duplicated and sorted.

## Properties

Name | Type
------------ | -------------
`languages` | Array&lt;string&gt;
`classifications` | { [key: string]: Array&lt;string&gt;; }

## Example

```typescript
import type { ChunkFilters } from ''

// TODO: Update the object below with actual values
const example = {
  "languages": null,
  "classifications": null,
} satisfies ChunkFilters

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ChunkFilters
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


