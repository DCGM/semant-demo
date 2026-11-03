
# DocumentPages

A document\'s page manifest (public). ``available`` is false, with no pages, when the document has no imported pages: it is then a text-only document.

## Properties

Name | Type
------------ | -------------
`documentId` | string
`available` | boolean
`pages` | [Array&lt;DocumentPage&gt;](DocumentPage.md)

## Example

```typescript
import type { DocumentPages } from ''

// TODO: Update the object below with actual values
const example = {
  "documentId": null,
  "available": null,
  "pages": null,
} satisfies DocumentPages

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentPages
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


