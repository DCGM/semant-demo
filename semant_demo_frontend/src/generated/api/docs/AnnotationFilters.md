
# AnnotationFilters

The annotation query (#663): which of a collection\'s annotations the concordance lists, a selection resolves (#459) and the source filter offers, one definition for all of them. Different filters combine with AND; the values of one filter are alternatives (OR), except attributes (below).  Document metadata is filtered by the shared ``DocumentFilters`` of Search, document browsing and Analytics (#526): the same validation and predicates select the same documents. They are evaluated against the documents of the matching annotations, joined per query, never copied onto annotations (ADR 0009).

## Properties

Name | Type
------------ | -------------
`tagIds` | Array&lt;string&gt;
`types` | [Array&lt;SpanType&gt;](SpanType.md)
`q` | string
`textScope` | [TextScope](TextScope.md)
`documentIds` | Array&lt;string&gt;
`documentFilters` | [DocumentFilters](DocumentFilters.md)
`attributeValues` | Array&lt;string&gt;
`attributeUnassigned` | Array&lt;string&gt;
`near` | [NearFilter](NearFilter.md)

## Example

```typescript
import type { AnnotationFilters } from ''

// TODO: Update the object below with actual values
const example = {
  "tagIds": null,
  "types": null,
  "q": null,
  "textScope": null,
  "documentIds": null,
  "documentFilters": null,
  "attributeValues": null,
  "attributeUnassigned": null,
  "near": null,
} satisfies AnnotationFilters

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AnnotationFilters
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


