
# Document

Bibliographic metadata of a corpus document, as stored on the ``Documents`` object.  The one document model of every read (document, browse, collection documents, document view, search hits). Properties that a store does not hold are absent (``None``); the type unions accept the variants found in existing stores.

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
`author` | Array&lt;string&gt;
`publisher` | string
`language` | string
`description` | string
`url` | [Url](Url.md)
`_public` | boolean
`documentType` | string
`keywords` | Array&lt;string&gt;
`genre` | string
`placeTerm` | string
`placeOfPublication` | string
`editors` | Array&lt;string&gt;
`seriesName` | string
`edition` | string
`illustrators` | Array&lt;string&gt;
`translators` | Array&lt;string&gt;
`redaktors` | Array&lt;string&gt;
`seriesNumber` | string

## Example

```typescript
import type { Document } from ''

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
  "placeOfPublication": null,
  "editors": null,
  "seriesName": null,
  "edition": null,
  "illustrators": null,
  "translators": null,
  "redaktors": null,
  "seriesNumber": null,
} satisfies Document

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as Document
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


