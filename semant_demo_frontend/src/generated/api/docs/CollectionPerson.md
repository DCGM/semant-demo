
# CollectionPerson

Someone who can use a collection now: its owner or a user it is shared with, by id, to name the actors of its annotations (#460).

## Properties

Name | Type
------------ | -------------
`id` | string
`name` | string
`username` | string
`role` | string

## Example

```typescript
import type { CollectionPerson } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "name": null,
  "username": null,
  "role": null,
} satisfies CollectionPerson

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as CollectionPerson
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


