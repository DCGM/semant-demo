
# Chunk


## Properties

Name | Type
------------ | -------------
`id` | string
`text` | string
`startPageId` | string
`fromPage` | number
`toPage` | number
`endParagraph` | boolean
`title` | string
`language` | string
`order` | number

## Example

```typescript
import type { Chunk } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "text": null,
  "startPageId": null,
  "fromPage": null,
  "toPage": null,
  "endParagraph": null,
  "title": null,
  "language": null,
  "order": null,
} satisfies Chunk

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as Chunk
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


