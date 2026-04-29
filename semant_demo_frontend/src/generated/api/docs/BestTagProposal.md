
# BestTagProposal


## Properties

Name | Type
------------ | -------------
`tagId` | string
`confidence` | number
`start` | number
`end` | number
`tag` | [TagData](TagData.md)

## Example

```typescript
import type { BestTagProposal } from ''

// TODO: Update the object below with actual values
const example = {
  "tagId": null,
  "confidence": null,
  "start": null,
  "end": null,
  "tag": null,
} satisfies BestTagProposal

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as BestTagProposal
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


