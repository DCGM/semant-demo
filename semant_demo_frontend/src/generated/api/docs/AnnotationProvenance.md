
# AnnotationProvenance

Who created, last reviewed (approve/reject) and last changed an annotation, and when (#460): the current state only, no history. User ids are stored; the client resolves names. Absent values were not recorded (``origin`` ``unknown``: saved before).

## Properties

Name | Type
------------ | -------------
`origin` | [AnnotationOrigin](AnnotationOrigin.md)
`createdBy` | string
`createdAt` | Date
`reviewedBy` | string
`reviewedAt` | Date
`lastEditedBy` | string
`lastEditedAt` | Date
`aiRunId` | string

## Example

```typescript
import type { AnnotationProvenance } from ''

// TODO: Update the object below with actual values
const example = {
  "origin": null,
  "createdBy": null,
  "createdAt": null,
  "reviewedBy": null,
  "reviewedAt": null,
  "lastEditedBy": null,
  "lastEditedAt": null,
  "aiRunId": null,
} satisfies AnnotationProvenance

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationProvenance
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


