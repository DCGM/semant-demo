
# TaggingConfigOutput


## Properties

Name | Type
------------ | -------------
`name` | string
`description` | string
`className` | string
`promptTemplate` | string
`params` | [TaggingConfigParams](TaggingConfigParams.md)

## Example

```typescript
import type { TaggingConfigOutput } from ''

// TODO: Update the object below with actual values
const example = {
  "name": null,
  "description": null,
  "className": null,
  "promptTemplate": null,
  "params": null,
} satisfies TaggingConfigOutput

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TaggingConfigOutput
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


