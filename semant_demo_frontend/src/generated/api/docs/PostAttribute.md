
# PostAttribute


## Properties

Name | Type
------------ | -------------
`name` | string
`description` | string
`cardinality` | [Cardinality](Cardinality.md)
`tagIds` | Array&lt;string&gt;
`values` | [Array&lt;PostAttributeValue&gt;](PostAttributeValue.md)

## Example

```typescript
import type { PostAttribute } from ''

// TODO: Update the object below with actual values
const example = {
  "name": null,
  "description": null,
  "cardinality": null,
  "tagIds": null,
  "values": null,
} satisfies PostAttribute

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PostAttribute
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


