
# SemantDemoSchemaDocumentsDocument


## Properties

Name | Type
------------ | -------------
`id` | string
`title` | string
`_public` | boolean
`documentType` | string
`partNumber` | string
`dateIssued` | Date
`yearIssued` | number
`language` | string
`publisher` | string
`placeOfPublication` | string
`subtitle` | string
`editors` | Array&lt;string&gt;
`partName` | string
`seriesName` | string
`edition` | string
`author` | Array&lt;string&gt;
`illustrators` | Array&lt;string&gt;
`translators` | Array&lt;string&gt;
`redaktors` | Array&lt;string&gt;
`seriesNumber` | string
`keywords` | Array&lt;string&gt;

## Example

```typescript
import type { SemantDemoSchemaDocumentsDocument } from ''

// TODO: Update the object below with actual values
const example = {
  "id": null,
  "title": null,
  "_public": null,
  "documentType": null,
  "partNumber": null,
  "dateIssued": null,
  "yearIssued": null,
  "language": null,
  "publisher": null,
  "placeOfPublication": null,
  "subtitle": null,
  "editors": null,
  "partName": null,
  "seriesName": null,
  "edition": null,
  "author": null,
  "illustrators": null,
  "translators": null,
  "redaktors": null,
  "seriesNumber": null,
  "keywords": null,
} satisfies SemantDemoSchemaDocumentsDocument

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as SemantDemoSchemaDocumentsDocument
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


