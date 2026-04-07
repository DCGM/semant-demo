
# TagData


## Properties

Name | Type
------------ | -------------
`tagName` | string
`tagShorthand` | string
`tagColor` | string
`tagPictogram` | string
`tagDefinition` | string
`tagExamples` | Array&lt;string&gt;
`collectionName` | string
`tagUuid` | string

## Example

```typescript
import type { TagData } from ''

// TODO: Update the object below with actual values
const example = {
  "tagName": null,
  "tagShorthand": null,
  "tagColor": null,
  "tagPictogram": null,
  "tagDefinition": null,
  "tagExamples": null,
  "collectionName": null,
  "tagUuid": null,
} satisfies TagData

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TagData
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


