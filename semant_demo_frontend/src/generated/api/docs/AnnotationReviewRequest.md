
# AnnotationReviewRequest

One review action for some annotations of the collection (#459).

## Properties

Name | Type
------------ | -------------
`action` | [ReviewAction](ReviewAction.md)
`annotationIds` | Array&lt;string&gt;
`tagId` | string

## Example

```typescript
import type { AnnotationReviewRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "action": null,
  "annotationIds": null,
  "tagId": null,
} satisfies AnnotationReviewRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationReviewRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


