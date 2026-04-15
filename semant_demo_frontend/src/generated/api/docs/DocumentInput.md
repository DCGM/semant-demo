
# DocumentInput


## Properties

Name | Type
------------ | -------------
`id` | string
`library` | string
`title` | string
`subtitle` | string
`partNumber` | [Partnumber](Partnumber.md)
`partName` | string
`yearIssued` | number
`dateIssued` | Date
`author` | string
`publisher` | string
`language` | string
`description` | string
`url` | [Url](Url.md)
`_public` | boolean
`documentType` | string
`keywords` | [Keywords](Keywords.md)
`genre` | string
`placeTerm` | string

## Example

```typescript
import type { DocumentInput } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "library": null,
  "title": null,
  "subtitle": null,
  "partNumber": null,
  "partName": null,
  "yearIssued": null,
  "dateIssued": null,
  "author": null,
  "publisher": null,
  "language": null,
  "description": null,
  "url": null,
  "_public": null,
  "documentType": null,
  "keywords": null,
  "genre": null,
  "placeTerm": null,
} satisfies DocumentInput

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentInput
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


