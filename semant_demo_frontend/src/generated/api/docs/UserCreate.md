
# UserCreate


## Properties

Name | Type
------------ | -------------
`email` | string
`password` | string
`isActive` | boolean
`isSuperuser` | boolean
`isVerified` | boolean
`username` | string
`name` | string
`institution` | string

## Example

```typescript
import type { UserCreate } from ''

// TODO: Update the object below with actual values
const example = {
  "email": null,
  "password": null,
  "isActive": null,
  "isSuperuser": null,
  "isVerified": null,
  "username": null,
  "name": null,
  "institution": null,
} satisfies UserCreate

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as UserCreate
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


