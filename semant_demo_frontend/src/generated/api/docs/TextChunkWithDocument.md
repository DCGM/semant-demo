
# TextChunkWithDocument

A search hit: the chunk, its document and optional generated summaries. ``text`` is display text (``service.display_text``: hyphenated line breaks joined), not the canonical stored text; span offsets do not apply to it. The document view reads canonical text (``DocumentDetail``).  ``metadata`` holds the chunk\'s stored classifications (``filters.TASK_CLASSES``) that have values: property name -> values, in ``TASK_CLASSES`` order.

## Properties

Name | Type
------------ | -------------
`id` | string
`text` | string
`startPageId` | string
`fromPage` | number
`toPage` | number
`document` | string
`title` | string
`endParagraph` | boolean
`language` | string
`order` | number
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
`documentObject` | [Document](Document.md)
`metadata` | { [key: string]: Array&lt;string&gt;; }

## Example

```typescript
import type { TextChunkWithDocument } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "text": null,
  "startPageId": null,
  "fromPage": null,
  "toPage": null,
  "document": null,
  "title": null,
  "endParagraph": null,
  "language": null,
  "order": null,
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
  "metadata": null,
} satisfies TextChunkWithDocument

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TextChunkWithDocument
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


