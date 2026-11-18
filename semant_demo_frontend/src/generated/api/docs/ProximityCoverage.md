
# ProximityCoverage

What a proximity filter could evaluate (#333).

## Properties

Name | Type
------------ | -------------
`primary` | number
`unknown` | number
`neighbors` | number
`neighborsUnpositioned` | number

## Example

```typescript
import type { ProximityCoverage } from ''

// TODO: Update the object below with actual values
const example = {
  "primary": null,
  "unknown": null,
  "neighbors": null,
  "neighborsUnpositioned": null,
} satisfies ProximityCoverage

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ProximityCoverage
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


