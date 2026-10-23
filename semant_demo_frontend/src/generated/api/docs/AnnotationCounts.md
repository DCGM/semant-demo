
# AnnotationCounts

How many annotations a collection holds per type (of some tags only, when asked), e.g. what deleting a tag or the collection would delete along (#479).

## Properties

Name | Type
------------ | -------------
`approved` | number
`suggestions` | number
`rejected` | number

## Example

```typescript
import type { AnnotationCounts } from ''

// TODO: Update the object below with actual values
const example = {
  "approved": null,
  "suggestions": null,
  "rejected": null,
} satisfies AnnotationCounts

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationCounts
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


