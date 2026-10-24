
# AttributeAssignResult

Per-annotation outcome (best effort, nothing is rolled back; ADR 0002). ``versions`` and ``values`` are given for every annotation whose current state is known, saved or refused for a conflict, so a client can show it instead of its stale copy.

## Properties

Name | Type
------------ | -------------
`outcome` | [WriteOutcome](WriteOutcome.md)
`succeeded` | Array&lt;string&gt;
`failed` | [Array&lt;StepFailure&gt;](StepFailure.md)
`versions` | { [key: string]: number; }
`values` | { [key: string]: Array&lt;string&gt;; }

## Example

```typescript
import type { AttributeAssignResult } from ''

// TODO: Update the object below with actual values
const example = {
  "outcome": null,
  "succeeded": null,
  "failed": null,
  "versions": null,
  "values": null,
} satisfies AttributeAssignResult

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as AttributeAssignResult
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


