
# SearchFilter


## Properties

Name | Type
------------ | -------------
`id` | string
`name` | string
`type` | [FilterType](FilterType.md)
`description` | string
`targetProperty` | string
`values` | [Array&lt;NominalFilterValue&gt;](NominalFilterValue.md)
`minValue` | [MinValue](MinValue.md)
`maxValue` | [MaxValue](MaxValue.md)

## Example

```typescript
import type { SearchFilter } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "name": null,
  "type": null,
  "description": null,
  "targetProperty": null,
  "values": null,
  "minValue": null,
  "maxValue": null,
} satisfies SearchFilter

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SearchFilter
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


