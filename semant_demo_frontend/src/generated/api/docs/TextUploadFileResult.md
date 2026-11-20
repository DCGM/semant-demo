
# TextUploadFileResult

What happened to one uploaded text file (#785).  * ``completed``: the document, all its chunks with their vectors and its collection link   are saved and read back. * ``invalid``: the file or its metadata row is invalid (``error``); nothing of the upload   was saved. * ``not_written``: valid, but not saved because another file or the CSV is invalid. * ``failed``: saving stopped (``error``). The document is not in any collection and   nobody can read it; uploading the file again creates a new document. * ``uncertain``: everything was saved but adding the document to the collection could   not be confirmed; reload the collection before uploading again.

## Properties

Name | Type
------------ | -------------
`filename` | string
`status` | string
`documentId` | string
`title` | string
`chunks` | number
`error` | string

## Example

```typescript
import type { TextUploadFileResult } from ''

// TODO: Update the object below with actual values
const example = {
  "filename": null,
  "status": null,
  "documentId": null,
  "title": null,
  "chunks": null,
  "error": null,
} satisfies TextUploadFileResult

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TextUploadFileResult
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


