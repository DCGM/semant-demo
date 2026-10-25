
# AttributeAssignRequest

One assignment of values of one attribute to up to ``MAX_ASSIGN_BATCH`` annotations, each on its own; ``expected_versions`` are their ``attributeVersion`` as the client knows it.

## Properties

Name | Type
------------ | -------------
`attributeId` | string
`annotationIds` | Array&lt;string&gt;
`expectedVersions` | { [key: string]: number; }
`mode` | [AssignMode](AssignMode.md)
`valueIds` | Array&lt;string&gt;
`source` | [AssignSource](AssignSource.md)
`runId` | string

## Example

```typescript
import type { AttributeAssignRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "attributeId": null,
  "annotationIds": null,
  "expectedVersions": null,
  "mode": null,
  "valueIds": null,
  "source": null,
  "runId": null,
} satisfies AttributeAssignRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AttributeAssignRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


