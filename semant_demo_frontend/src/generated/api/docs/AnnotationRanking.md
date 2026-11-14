
# AnnotationRanking

The retrieval mode of an annotation query (#664). Ranked modes return at most ``k`` annotations by relevance among those matching every filter (filters apply before ranking), only those with a current vector of the configured model.

## Properties

Name | Type
------------ | -------------
`mode` | [RetrievalMode](RetrievalMode.md)
`k` | number
`similarTo` | string
`includeSource` | boolean

## Example

```typescript
import type { AnnotationRanking } from ''

// TODO: Update the object below with actual values
const example = {
  "mode": null,
  "k": null,
  "similarTo": null,
  "includeSource": null,
} satisfies AnnotationRanking

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationRanking
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


