
# AnnotationRestoreRequest

Undo of the last review or boundary change (#461): the previous values of up to ``MAX_REVIEW_BATCH`` annotations, each with the version the change left it at.

## Properties

Name | Type
------------ | -------------
`items` | [Array&lt;AnnotationRestoreItem&gt;](AnnotationRestoreItem.md)

## Example

```typescript
import type { AnnotationRestoreRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "items": null,
} satisfies AnnotationRestoreRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationRestoreRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


