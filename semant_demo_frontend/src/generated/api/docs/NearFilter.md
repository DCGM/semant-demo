
# NearFilter

Proximity (#333): only annotations with (or, ``absent``, without) a neighbor annotation of the same document that matches ``tag_ids``/``types``/``attribute_values`` and lies in ``relation`` to it. An annotation is never its own neighbor and is listed once however many neighbors match. Positions are the stored document-relative intervals (#463), so chunks outside the user collection count; annotations without current positions never match (and, with ``absent``, neither do annotations of a document holding a neighbor without positions).

## Properties

Name | Type
------------ | -------------
`tagIds` | Array&lt;string&gt;
`types` | [Array&lt;SpanType&gt;](SpanType.md)
`attributeValues` | Array&lt;string&gt;
`relation` | [NearRelation](NearRelation.md)
`distance` | number
`unit` | [DistanceUnit](DistanceUnit.md)
`direction` | [NearDirection](NearDirection.md)
`absent` | boolean

## Example

```typescript
import type { NearFilter } from ''

// TODO: Update the object below with actual values
const example = {
  "tagIds": null,
  "types": null,
  "attributeValues": null,
  "relation": null,
  "distance": null,
  "unit": null,
  "direction": null,
  "absent": null,
} satisfies NearFilter

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as NearFilter
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


