
# AnnotationResultSet

What a page of annotations is a page of (#664).

## Properties

Name | Type
------------ | -------------
`kind` | [ResultKind](ResultKind.md)
`mode` | [RetrievalMode](RetrievalMode.md)
`k` | number
`truncated` | boolean
`coverage` | [VectorCoverage](VectorCoverage.md)

## Example

```typescript
import type { AnnotationResultSet } from ''

// TODO: Update the object below with actual values
const example = {
  "kind": null,
  "mode": null,
  "k": null,
  "truncated": null,
  "coverage": null,
} satisfies AnnotationResultSet

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationResultSet
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


