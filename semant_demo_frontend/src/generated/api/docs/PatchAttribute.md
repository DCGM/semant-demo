
# PatchAttribute

The cardinality cannot be changed: existing assignments would turn contradictory.

## Properties

Name | Type
------------ | -------------
`name` | string
`description` | string
`allTags` | boolean
`tagIds` | Array&lt;string&gt;
`retired` | boolean

## Example

```typescript
import type { PatchAttribute } from ''

// TODO: Update the object below with actual values
const example = {
  "name": null,
  "description": null,
  "allTags": null,
  "tagIds": null,
  "retired": null,
} satisfies PatchAttribute

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PatchAttribute
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


