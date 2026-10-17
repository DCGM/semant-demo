
# QuotaStatusResponse


## Properties

Name | Type
------------ | -------------
`principal` | string
`day` | string
`limitUsd` | number
`usedUsd` | number
`chargedUsd` | number
`reservedUsd` | number
`remainingUsd` | number
`resetAt` | Date
`nearLimit` | boolean
`exhausted` | boolean

## Example

```typescript
import type { QuotaStatusResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "principal": null,
  "day": null,
  "limitUsd": null,
  "usedUsd": null,
  "chargedUsd": null,
  "reservedUsd": null,
  "remainingUsd": null,
  "resetAt": null,
  "nearLimit": null,
  "exhausted": null,
} satisfies QuotaStatusResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as QuotaStatusResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


