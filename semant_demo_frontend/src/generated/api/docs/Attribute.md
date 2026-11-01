
# Attribute


## Properties

Name | Type
------------ | -------------
`id` | string
`name` | string
`description` | string
`cardinality` | [Cardinality](Cardinality.md)
`allTags` | boolean
`tagIds` | Array&lt;string&gt;
`retired` | boolean
`revision` | number
`values` | [Array&lt;AttributeValue&gt;](AttributeValue.md)

## Example

```typescript
import type { Attribute } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "name": null,
  "description": null,
  "cardinality": null,
  "allTags": null,
  "tagIds": null,
  "retired": null,
  "revision": null,
  "values": null,
} satisfies Attribute

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as Attribute
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


