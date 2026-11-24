
# AiSuggestionRunInfo

Persisted run metadata; also exists for runs with no surviving suggestions.

## Properties

Name | Type
------------ | -------------
`id` | string
`mode` | string
`configName` | string
`tagIds` | Array&lt;string&gt;
`startedAt` | Date
`finishedAt` | Date
`outcome` | string
`saved` | number
`unit` | string
`unitsTotal` | number
`unitsCompleted` | number
`providerFailures` | number
`saveFailures` | number

## Example

```typescript
import type { AiSuggestionRunInfo } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "mode": null,
  "configName": null,
  "tagIds": null,
  "startedAt": null,
  "finishedAt": null,
  "outcome": null,
  "saved": null,
  "unit": null,
  "unitsTotal": null,
  "unitsCompleted": null,
  "providerFailures": null,
  "saveFailures": null,
} satisfies AiSuggestionRunInfo

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AiSuggestionRunInfo
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


