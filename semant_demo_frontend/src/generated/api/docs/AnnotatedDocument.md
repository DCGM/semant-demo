
# AnnotatedDocument

A document with annotations matching a concordance query, for the source and year filters (#329). ``available`` is false when the document cannot be read.

## Properties

Name | Type
------------ | -------------
`id` | string
`title` | string
`year` | number
`count` | number
`available` | boolean

## Example

```typescript
import type { AnnotatedDocument } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "title": null,
  "year": null,
  "count": null,
  "available": null,
} satisfies AnnotatedDocument

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotatedDocument
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


