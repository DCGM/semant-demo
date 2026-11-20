
# TextUploadResponse

The result of every file of a text upload, in request order, and the problems of the upload as a whole (the metadata CSV, the number of files); any problem means nothing was saved.

## Properties

Name | Type
------------ | -------------
`files` | [Array&lt;TextUploadFileResult&gt;](TextUploadFileResult.md)
`errors` | Array&lt;string&gt;

## Example

```typescript
import type { TextUploadResponse } from ''

// TODO: Update the object below with actual values
const example = {
  "files": null,
  "errors": null,
} satisfies TextUploadResponse

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as TextUploadResponse
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


