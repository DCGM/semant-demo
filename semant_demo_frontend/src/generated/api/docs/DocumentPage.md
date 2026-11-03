
# DocumentPage

One page of a document\'s page list. ``order`` is its index in the list, the page number used by the chunks\' ``from_page``/``to_page``. Each URL is present only when that asset is available; a page may have none (a cover, a blank or a page not imported).

## Properties

Name | Type
------------ | -------------
`pageId` | string
`order` | number
`label` | string
`pageType` | string
`width` | number
`height` | number
`imageUrl` | string
`layoutUrl` | string
`thumbnailUrl` | string

## Example

```typescript
import type { DocumentPage } from ''

// TODO: Update the object below with actual values
const example = {
  "pageId": null,
  "order": null,
  "label": null,
  "pageType": null,
  "width": null,
  "height": null,
  "imageUrl": null,
  "layoutUrl": null,
  "thumbnailUrl": null,
} satisfies DocumentPage

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as DocumentPage
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


