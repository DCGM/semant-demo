
# AnnotationListRow

One concordance (KWIC) row: an annotation with its stored text and context (#329).  ``start``/``end`` are the authoritative UTF-16 offsets on the anchor chunk ``chunkId``. ``text``, ``leftContext`` and ``rightContext`` are present only when ``textStatus`` is ``ready``. ``documentAvailable`` is false when the annotation\'s document cannot be read (deleted from the corpus); title and year are then absent.

## Properties

Name | Type
------------ | -------------
`id` | string
`tagId` | string
`type` | [SpanType](SpanType.md)
`chunkId` | string
`documentId` | string
`start` | number
`end` | number
`revision` | number
`textStatus` | [TextStatus](TextStatus.md)
`text` | string
`leftContext` | string
`rightContext` | string
`documentAvailable` | boolean
`documentTitle` | string
`documentYear` | number
`editVersion` | number
`provenance` | [AnnotationProvenance](AnnotationProvenance.md)
`attributes` | { [key: string]: Array&lt;string&gt;; }
`attributeVersion` | number

## Example

```typescript
import type { AnnotationListRow } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "tagId": null,
  "type": null,
  "chunkId": null,
  "documentId": null,
  "start": null,
  "end": null,
  "revision": null,
  "textStatus": null,
  "text": null,
  "leftContext": null,
  "rightContext": null,
  "documentAvailable": null,
  "documentTitle": null,
  "documentYear": null,
  "editVersion": null,
  "provenance": null,
  "attributes": null,
  "attributeVersion": null,
} satisfies AnnotationListRow

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationListRow
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


