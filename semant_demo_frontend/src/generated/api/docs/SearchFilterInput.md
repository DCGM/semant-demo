
# SearchFilterInput


## Properties

Name | Type
------------ | -------------
`id` | string
`values` | [Values](Values.md)
`minValue` | [MinValue1](MinValue1.md)
`maxValue` | [MaxValue1](MaxValue1.md)

## Example

```typescript
import type { SearchFilterInput } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "values": null,
  "minValue": null,
  "maxValue": null,
} satisfies SearchFilterInput

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchFilterInput
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


