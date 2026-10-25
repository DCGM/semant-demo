
# AttributeChangeValue

A value of a change record with its label and kind as defined when the change was made. The id is the identity; label and kind are only what the history shows, so a later rename, retirement or deletion of the value does not change what a past decision says. Descriptions and examples are not kept: reading a decision as its definition then meant needs versioned definitions (#502).

## Properties

Name | Type
------------ | -------------
`id` | string
`label` | string
`kind` | [ValueKind](ValueKind.md)

## Example

```typescript
import type { AttributeChangeValue } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "label": null,
  "kind": null,
} satisfies AttributeChangeValue

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AttributeChangeValue
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


