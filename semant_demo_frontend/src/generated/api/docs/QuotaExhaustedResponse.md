
# QuotaExhaustedResponse

The body of a 429 answer to an AI operation refused for the daily allowance (``QuotaExhausted.body``); the answer also has a ``Retry-After`` header (seconds). AI routes declare it as their 429 response (``QUOTA_EXHAUSTED_RESPONSES``).

## Properties

Name | Type
------------ | -------------
`detail` | string
`code` | string
`principal` | string
`resetAt` | Date
`limitUsd` | number
`usedUsd` | number

## Example

```typescript
import type { QuotaExhaustedResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "detail": null,
  "code": null,
  "principal": null,
  "resetAt": null,
  "limitUsd": null,
  "usedUsd": null,
} satisfies QuotaExhaustedResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as QuotaExhaustedResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


