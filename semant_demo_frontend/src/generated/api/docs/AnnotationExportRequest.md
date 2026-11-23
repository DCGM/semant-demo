
# AnnotationExportRequest

A CSV or JSON export of a collection\'s annotations (#719): one row per annotation, in no particular order; the annotations are resolved by id when the export starts. The identity, status, text, context, document position and accepted attribute columns are always present; the optional groups add columns only.

## Properties

Name | Type
------------ | -------------
`scope` | [AnnotationExportScope](AnnotationExportScope.md)
`annotationIds` | Array&lt;string&gt;
`filters` | [AnnotationFilters](AnnotationFilters.md)
`types` | [Array&lt;SpanType&gt;](SpanType.md)
`chunkMetadata` | boolean
`documentMetadata` | boolean
`provenance` | boolean
`delimiter` | [CsvDelimiter](CsvDelimiter.md)
`format` | [ExportFormat](ExportFormat.md)
`ranking` | [AnnotationRanking](AnnotationRanking.md)
`audit` | boolean

## Example

```typescript
import type { AnnotationExportRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "scope": null,
  "annotationIds": null,
  "filters": null,
  "types": null,
  "chunkMetadata": null,
  "documentMetadata": null,
  "provenance": null,
  "delimiter": null,
  "format": null,
  "ranking": null,
  "audit": null,
} satisfies AnnotationExportRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationExportRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


