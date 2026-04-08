
# TextChunkWithDocumentInput


## Properties

Name | Type
------------ | -------------
`id` | string
`title` | string
`text` | string
`startPageId` | string
`fromPage` | number
`toPage` | number
`endParagraph` | boolean
`language` | string
`document` | string
`nerP` | Array&lt;string&gt;
`nerT` | Array&lt;string&gt;
`nerA` | Array&lt;string&gt;
`nerG` | Array&lt;string&gt;
`nerI` | Array&lt;string&gt;
`nerM` | Array&lt;string&gt;
`nerO` | Array&lt;string&gt;
`queryTitle` | string
`querySummary` | string
`summary` | string
`documentObject` | [DocumentInput](DocumentInput.md)

## Example

```typescript
import type { TextChunkWithDocumentInput } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "title": null,
  "text": null,
  "startPageId": null,
  "fromPage": null,
  "toPage": null,
  "endParagraph": null,
  "language": null,
  "document": null,
  "nerP": null,
  "nerT": null,
  "nerA": null,
  "nerG": null,
  "nerI": null,
  "nerM": null,
  "nerO": null,
  "queryTitle": null,
  "querySummary": null,
  "summary": null,
  "documentObject": null,
} satisfies TextChunkWithDocumentInput

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TextChunkWithDocumentInput
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


