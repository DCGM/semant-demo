
# QuestionRequest

A question answered from the snippets of ``search_response``. The question travels in the body, not the URL, so proxies and access logs never see it (#304).

## Properties

Name | Type
------------ | -------------
`questionText` | string
`searchResponse` | [SearchResponse](SearchResponse.md)

## Example

```typescript
import type { QuestionRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "questionText": null,
  "searchResponse": null,
} satisfies QuestionRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as QuestionRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


