
# LayoutStart

Where a chunk\'s first character is on the page scans (#540, docs/PAGE_LAYOUT.md): the line ``lineId`` of the page layout file of ``pageId``, ``offset`` UTF-16 code units into that line\'s text. ``exact``: walking the layout lines from there reproduces the chunk text, so characters map exactly; ``approximate``: the text differs slightly (at most the import\'s edit ratio), so only whole lines may be highlighted.

## Properties

Name | Type
------------ | -------------
`pageId` | string
`lineId` | string
`offset` | number
`match` | string

## Example

```typescript
import type { LayoutStart } from ''

// TODO: Update the object below with actual values
const example = {
  "pageId": null,
  "lineId": null,
  "offset": null,
  "match": null,
} satisfies LayoutStart

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as LayoutStart
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


