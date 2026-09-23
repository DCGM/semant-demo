# DefaultApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**addDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPost**](DefaultApi.md#adddocumenttocollectionapicollectionscollectioniddocumentsdocumentidpost) | **POST** /api/collections/{collection_id}/documents/{document_id} | Add Document To Collection |
| [**browseDocumentsApiDocumentsBrowseGet**](DefaultApi.md#browsedocumentsapidocumentsbrowseget) | **GET** /api/documents/browse | Browse Documents |
| [**bulkUpdateTagSpansApiTagSpansBulkUpdatePost**](DefaultApi.md#bulkupdatetagspansapitagspansbulkupdatepost) | **POST** /api/tag_spans/bulk_update | Bulk Update Tag Spans |
| [**countDocumentChunksApiDocumentsDocumentIdChunksCountGet**](DefaultApi.md#countdocumentchunksapidocumentsdocumentidchunkscountget) | **GET** /api/documents/{document_id}/chunks/count | Count Document Chunks |
| [**createTagApiTagsPost**](DefaultApi.md#createtagapitagspost) | **POST** /api/tags | Create Tag |
| [**createTagSpanApiTagSpansPost**](DefaultApi.md#createtagspanapitagspanspost) | **POST** /api/tag_spans | Create Tag Span |
| [**createUserCollectionApiUserCollectionsPost**](DefaultApi.md#createusercollectionapiusercollectionspost) | **POST** /api/user_collections | Create User Collection |
| [**deleteAutoSpansApiAiAutoSpansDeletePost**](DefaultApi.md#deleteautospansapiaiautospansdeletepost) | **POST** /api/ai/auto_spans/delete | Delete Auto Spans |
| [**deleteCollectionApiCollectionsCollectionIdDelete**](DefaultApi.md#deletecollectionapicollectionscollectioniddelete) | **DELETE** /api/collections/{collection_id} | Delete Collection |
| [**deleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePost**](DefaultApi.md#deletespansfortagsindocumentapitagspansindocumentdeletepost) | **POST** /api/tag_spans/in_document/delete | Delete Spans For Tags In Document |
| [**deleteTagApiTagsTagUuidDelete**](DefaultApi.md#deletetagapitagstaguuiddelete) | **DELETE** /api/tags/{tag_uuid} | Delete Tag |
| [**deleteTagSpanApiTagSpansSpanIdDelete**](DefaultApi.md#deletetagspanapitagspansspaniddelete) | **DELETE** /api/tag_spans/{span_id} | Delete Tag Span |
| [**discussSpanApiAiDiscussSpanPost**](DefaultApi.md#discussspanapiaidiscussspanpost) | **POST** /api/ai/discuss_span | Discuss Span |
| [**explainSelectionApiRagExplainPost**](DefaultApi.md#explainselectionapiragexplainpost) | **POST** /api/rag/explain | Explain Selection |
| [**fetchCollectionApiUserCollectionsCollectionIdGet**](DefaultApi.md#fetchcollectionapiusercollectionscollectionidget) | **GET** /api/user_collections/{collection_id} | Fetch Collection |
| [**fetchCollectionsApiUserCollectionsGet**](DefaultApi.md#fetchcollectionsapiusercollectionsget) | **GET** /api/user_collections | Fetch Collections |
| [**fetchDocumentApiDocumentDocumentIdGet**](DefaultApi.md#fetchdocumentapidocumentdocumentidget) | **GET** /api/document/{document_id} | Fetch Document |
| [**fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet**](DefaultApi.md#fetchdocumentchunksapidocumentsdocumentidcollectionidchunksget) | **GET** /api/documents/{document_id}/{collection_id}/chunks | Fetch Document Chunks |
| [**getAvailableSearchFiltersApiSearchFiltersGet**](DefaultApi.md#getavailablesearchfiltersapisearchfiltersget) | **GET** /api/search/filters | Get Available Search Filters |
| [**getAvalaibleRagConfigurationsApiRagConfigurationsGet**](DefaultApi.md#getavalaibleragconfigurationsapiragconfigurationsget) | **GET** /api/rag/configurations | Get Avalaible Rag Configurations |
| [**getChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGet**](DefaultApi.md#getchunksinrangeapicollectionscollectioniddocumentsdocumentidchunksget) | **GET** /api/collections/{collection_id}/documents/{document_id}/chunks | Get Chunks In Range |
| [**getCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGet**](DefaultApi.md#getcollectiondocumentchunksapicollectionscollectioniddocumentsdocumentidget) | **GET** /api/collections/{collection_id}/documents/{document_id} | Get Collection Document Chunks |
| [**getCollectionDocumentsApiUserCollectionCollectionIdDocumentsGet**](DefaultApi.md#getcollectiondocumentsapiusercollectioncollectioniddocumentsget) | **GET** /api/user_collection/{collection_id}/documents | Get Collection Documents |
| [**getCollectionMembersApiCollectionsCollectionIdMembersGet**](DefaultApi.md#getcollectionmembersapicollectionscollectionidmembersget) | **GET** /api/collections/{collection_id}/members | Get Collection Members |
| [**getCollectionStatsApiUserCollectionCollectionIdStatsGet**](DefaultApi.md#getcollectionstatsapiusercollectioncollectionidstatsget) | **GET** /api/user_collection/{collection_id}/stats | Get Collection Stats |
| [**getCollectionTagsApiCollectionsCollectionIdTagsGet**](DefaultApi.md#getcollectiontagsapicollectionscollectionidtagsget) | **GET** /api/collections/{collection_id}/tags | Get Collection Tags |
| [**getDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGet**](DefaultApi.md#getdocumentstatsapicollectionscollectioniddocumentsdocumentidstatsget) | **GET** /api/collections/{collection_id}/documents/{document_id}/stats | Get Document Stats |
| [**getNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGet**](DefaultApi.md#getneighbourchunkapicollectionscollectioniddocumentsdocumentidneighbourget) | **GET** /api/collections/{collection_id}/documents/{document_id}/neighbour | Get Neighbour Chunk |
| [**getTagApiTagsTagUuidGet**](DefaultApi.md#gettagapitagstaguuidget) | **GET** /api/tags/{tag_uuid} | Get Tag |
| [**healthHealthGet**](DefaultApi.md#healthhealthget) | **GET** /health | Health |
| [**questionApiQuestionQuestionTextPost**](DefaultApi.md#questionapiquestionquestiontextpost) | **POST** /api/question/{question_text} | Question |
| [**ragApiRagPost**](DefaultApi.md#ragapiragpost) | **POST** /api/rag | Rag |
| [**readTagSpansApiTagSpansGet**](DefaultApi.md#readtagspansapitagspansget) | **GET** /api/tag_spans | Read Tag Spans |
| [**readTagSpansBatchApiTagSpansBatchPost**](DefaultApi.md#readtagspansbatchapitagspansbatchpost) | **POST** /api/tag_spans/batch | Read Tag Spans Batch |
| [**removeDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDelete**](DefaultApi.md#removedocumentfromcollectionapicollectionscollectioniddocumentsdocumentiddelete) | **DELETE** /api/collections/{collection_id}/documents/{document_id} | Remove Document From Collection |
| [**saveAppFeedbackApiV1FeedbackPost**](DefaultApi.md#saveappfeedbackapiv1feedbackpost) | **POST** /api/v1/feedback | Save App Feedback |
| [**saveFeedbackApiRagFeedbackPost**](DefaultApi.md#savefeedbackapiragfeedbackpost) | **POST** /api/rag/feedback | Save Feedback |
| [**searchApiSearchPost**](DefaultApi.md#searchapisearchpost) | **POST** /api/search | Search |
| [**searchUsersApiUsersSearchGet**](DefaultApi.md#searchusersapiuserssearchget) | **GET** /api/users/search | Search Users |
| [**shareCollectionApiCollectionsCollectionIdSharePost**](DefaultApi.md#sharecollectionapicollectionscollectionidsharepost) | **POST** /api/collections/{collection_id}/share | Share Collection |
| [**suggestSpansOptimizedApiAiSuggestSpansOptimizedPost**](DefaultApi.md#suggestspansoptimizedapiaisuggestspansoptimizedpost) | **POST** /api/ai/suggest_spans/optimized | Suggest Spans Optimized |
| [**suggestSpansSelectionApiAiSuggestSpansSelectionPost**](DefaultApi.md#suggestspansselectionapiaisuggestspansselectionpost) | **POST** /api/ai/suggest_spans/selection | Suggest Spans Selection |
| [**suggestSpansThoroughApiAiSuggestSpansThoroughPost**](DefaultApi.md#suggestspansthoroughapiaisuggestspansthoroughpost) | **POST** /api/ai/suggest_spans/thorough | Suggest Spans Thorough |
| [**summarizeApiSummarizeSummaryTypePost**](DefaultApi.md#summarizeapisummarizesummarytypepost) | **POST** /api/summarize/{summary_type} | Summarize |
| [**unshareCollectionApiCollectionsCollectionIdShareUserIdDelete**](DefaultApi.md#unsharecollectionapicollectionscollectionidshareuseriddelete) | **DELETE** /api/collections/{collection_id}/share/{user_id} | Unshare Collection |
| [**updateCollectionApiUserCollectionsCollectionIdPatch**](DefaultApi.md#updatecollectionapiusercollectionscollectionidpatch) | **PATCH** /api/user_collections/{collection_id} | Update Collection |
| [**updateCollectionOwnerApiCollectionsCollectionIdOwnerPatch**](DefaultApi.md#updatecollectionownerapicollectionscollectionidownerpatch) | **PATCH** /api/collections/{collection_id}/owner | Update Collection Owner |
| [**updateTagApiTagsTagUuidPatch**](DefaultApi.md#updatetagapitagstaguuidpatch) | **PATCH** /api/tags/{tag_uuid} | Update Tag |
| [**updateTagSpanApiTagSpansSpanIdPatch**](DefaultApi.md#updatetagspanapitagspansspanidpatch) | **PATCH** /api/tag_spans/{span_id} | Update Tag Span |



## addDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPost

> any addDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPost(collectionId, documentId)

Add Document To Collection

Adds document to collection and also links all its chunks to that collection

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { AddDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    documentId: documentId_example,
  } satisfies AddDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPostRequest;

  try {
    const data = await api.addDocumentToCollectionApiCollectionsCollectionIdDocumentsDocumentIdPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **documentId** | `string` |  | [Defaults to `undefined`] |

### Return type

**any**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## browseDocumentsApiDocumentsBrowseGet

> DocumentBrowse browseDocumentsApiDocumentsBrowseGet(collectionId, limit, offset, sortBy, sortDesc, title, author, publisher, documentType)

Browse Documents

Browses documents which belong to collection given by id with pagination, filtering and sorting options

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { BrowseDocumentsApiDocumentsBrowseGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string (optional)
    collectionId: collectionId_example,
    // number (optional)
    limit: 56,
    // number (optional)
    offset: 56,
    // string (optional)
    sortBy: sortBy_example,
    // boolean (optional)
    sortDesc: true,
    // string (optional)
    title: title_example,
    // string (optional)
    author: author_example,
    // string (optional)
    publisher: publisher_example,
    // string (optional)
    documentType: documentType_example,
  } satisfies BrowseDocumentsApiDocumentsBrowseGetRequest;

  try {
    const data = await api.browseDocumentsApiDocumentsBrowseGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Optional] [Defaults to `undefined`] |
| **limit** | `number` |  | [Optional] [Defaults to `50`] |
| **offset** | `number` |  | [Optional] [Defaults to `0`] |
| **sortBy** | `string` |  | [Optional] [Defaults to `undefined`] |
| **sortDesc** | `boolean` |  | [Optional] [Defaults to `false`] |
| **title** | `string` |  | [Optional] [Defaults to `undefined`] |
| **author** | `string` |  | [Optional] [Defaults to `undefined`] |
| **publisher** | `string` |  | [Optional] [Defaults to `undefined`] |
| **documentType** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

[**DocumentBrowse**](DocumentBrowse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## bulkUpdateTagSpansApiTagSpansBulkUpdatePost

> BulkUpdateSpansResponse bulkUpdateTagSpansApiTagSpansBulkUpdatePost(bulkUpdateSpansRequest)

Bulk Update Tag Spans

Apply the same :class:&#x60;PatchSpan&#x60; to many spans in one round-trip.  Used by the AI-assist \&quot;Approve / Reject all selected\&quot; action — collapses N PATCH calls into one and lets the server fan them out concurrently.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { BulkUpdateTagSpansApiTagSpansBulkUpdatePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // BulkUpdateSpansRequest
    bulkUpdateSpansRequest: ...,
  } satisfies BulkUpdateTagSpansApiTagSpansBulkUpdatePostRequest;

  try {
    const data = await api.bulkUpdateTagSpansApiTagSpansBulkUpdatePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **bulkUpdateSpansRequest** | [BulkUpdateSpansRequest](BulkUpdateSpansRequest.md) |  | |

### Return type

[**BulkUpdateSpansResponse**](BulkUpdateSpansResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## countDocumentChunksApiDocumentsDocumentIdChunksCountGet

> number countDocumentChunksApiDocumentsDocumentIdChunksCountGet(documentId)

Count Document Chunks

Returns the total number of chunks in the given document.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CountDocumentChunksApiDocumentsDocumentIdChunksCountGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    documentId: documentId_example,
  } satisfies CountDocumentChunksApiDocumentsDocumentIdChunksCountGetRequest;

  try {
    const data = await api.countDocumentChunksApiDocumentsDocumentIdChunksCountGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **documentId** | `string` |  | [Defaults to `undefined`] |

### Return type

**number**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createTagApiTagsPost

> Tag createTagApiTagsPost(collectionId, postTag)

Create Tag

Creates a tag in weaviate db, or not if the same tag already exists

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateTagApiTagsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    collectionId: collectionId_example,
    // PostTag
    postTag: ...,
  } satisfies CreateTagApiTagsPostRequest;

  try {
    const data = await api.createTagApiTagsPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **postTag** | [PostTag](PostTag.md) |  | |

### Return type

[**Tag**](Tag.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **201** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createTagSpanApiTagSpansPost

> TagSpan createTagSpanApiTagSpansPost(postSpan)

Create Tag Span

Adds new TagSpan

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateTagSpanApiTagSpansPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // PostSpan
    postSpan: ...,
  } satisfies CreateTagSpanApiTagSpansPostRequest;

  try {
    const data = await api.createTagSpanApiTagSpansPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **postSpan** | [PostSpan](PostSpan.md) |  | |

### Return type

[**TagSpan**](TagSpan.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## createUserCollectionApiUserCollectionsPost

> Collection createUserCollectionApiUserCollectionsPost(postCollection)

Create User Collection

Creates user collection in weaviate db, or not if the same user collection already exists

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateUserCollectionApiUserCollectionsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // PostCollection
    postCollection: ...,
  } satisfies CreateUserCollectionApiUserCollectionsPostRequest;

  try {
    const data = await api.createUserCollectionApiUserCollectionsPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **postCollection** | [PostCollection](PostCollection.md) |  | |

### Return type

[**Collection**](Collection.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **201** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## deleteAutoSpansApiAiAutoSpansDeletePost

> DeleteAutoSpansResponse deleteAutoSpansApiAiAutoSpansDeletePost(deleteAutoSpansRequest)

Delete Auto Spans

Bulk-delete unresolved AI proposals (&#x60;&#x60;type &#x3D;&#x3D; \&#39;auto\&#39;&#x60;&#x60;) within a single (collection, document) for the given tag UUIDs.  Useful for cleaning up suggestions the user did not get around to approving or rejecting.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteAutoSpansApiAiAutoSpansDeletePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // DeleteAutoSpansRequest
    deleteAutoSpansRequest: ...,
  } satisfies DeleteAutoSpansApiAiAutoSpansDeletePostRequest;

  try {
    const data = await api.deleteAutoSpansApiAiAutoSpansDeletePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **deleteAutoSpansRequest** | [DeleteAutoSpansRequest](DeleteAutoSpansRequest.md) |  | |

### Return type

[**DeleteAutoSpansResponse**](DeleteAutoSpansResponse.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## deleteCollectionApiCollectionsCollectionIdDelete

> deleteCollectionApiCollectionsCollectionIdDelete(collectionId)

Delete Collection

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteCollectionApiCollectionsCollectionIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies DeleteCollectionApiCollectionsCollectionIdDeleteRequest;

  try {
    const data = await api.deleteCollectionApiCollectionsCollectionIdDelete(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

`void` (Empty response body)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **204** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## deleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePost

> DeleteSpansForTagsResponse deleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePost(deleteSpansForTagsRequest)

Delete Spans For Tags In Document

Bulk-delete approved (&#x60;&#x60;type &#x3D;&#x3D; \&#39;pos\&#39;&#x60;&#x60;) spans for the given tag ids within a single (collection, document) scope. Negatives and unresolved auto suggestions are left untouched.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // DeleteSpansForTagsRequest
    deleteSpansForTagsRequest: ...,
  } satisfies DeleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePostRequest;

  try {
    const data = await api.deleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **deleteSpansForTagsRequest** | [DeleteSpansForTagsRequest](DeleteSpansForTagsRequest.md) |  | |

### Return type

[**DeleteSpansForTagsResponse**](DeleteSpansForTagsResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## deleteTagApiTagsTagUuidDelete

> deleteTagApiTagsTagUuidDelete(tagUuid)

Delete Tag

Deletes tag

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteTagApiTagsTagUuidDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    tagUuid: tagUuid_example,
  } satisfies DeleteTagApiTagsTagUuidDeleteRequest;

  try {
    const data = await api.deleteTagApiTagsTagUuidDelete(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **tagUuid** | `string` |  | [Defaults to `undefined`] |

### Return type

`void` (Empty response body)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **204** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## deleteTagSpanApiTagSpansSpanIdDelete

> deleteTagSpanApiTagSpansSpanIdDelete(spanId)

Delete Tag Span

Delete a TagSpan\&#39;s information

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteTagSpanApiTagSpansSpanIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    spanId: spanId_example,
  } satisfies DeleteTagSpanApiTagSpansSpanIdDeleteRequest;

  try {
    const data = await api.deleteTagSpanApiTagSpansSpanIdDelete(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **spanId** | `string` |  | [Defaults to `undefined`] |

### Return type

`void` (Empty response body)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **204** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## discussSpanApiAiDiscussSpanPost

> discussSpanApiAiDiscussSpanPost(discussSpanRequest)

Discuss Span

Stream an assistant reply discussing whether the given span fits its tag.  The request body carries the full chat history; the backend resolves span / document / tag context and prepends it as a system message before forwarding to the configured OpenAI-compatible Chat Completions endpoint.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DiscussSpanApiAiDiscussSpanPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // DiscussSpanRequest
    discussSpanRequest: ...,
  } satisfies DiscussSpanApiAiDiscussSpanPostRequest;

  try {
    const data = await api.discussSpanApiAiDiscussSpanPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **discussSpanRequest** | [DiscussSpanRequest](DiscussSpanRequest.md) |  | |

### Return type

`void` (Empty response body)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## explainSelectionApiRagExplainPost

> any explainSelectionApiRagExplainPost(explainRequest)

Explain Selection

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ExplainSelectionApiRagExplainPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // ExplainRequest
    explainRequest: ...,
  } satisfies ExplainSelectionApiRagExplainPostRequest;

  try {
    const data = await api.explainSelectionApiRagExplainPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **explainRequest** | [ExplainRequest](ExplainRequest.md) |  | |

### Return type

**any**

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## fetchCollectionApiUserCollectionsCollectionIdGet

> Collection fetchCollectionApiUserCollectionsCollectionIdGet(collectionId)

Fetch Collection

Retrieves collection by its id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FetchCollectionApiUserCollectionsCollectionIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies FetchCollectionApiUserCollectionsCollectionIdGetRequest;

  try {
    const data = await api.fetchCollectionApiUserCollectionsCollectionIdGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Collection**](Collection.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## fetchCollectionsApiUserCollectionsGet

> Array&lt;Collection&gt; fetchCollectionsApiUserCollectionsGet()

Fetch Collections

Retrieves all collections for given user

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FetchCollectionsApiUserCollectionsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  try {
    const data = await api.fetchCollectionsApiUserCollectionsGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**Array&lt;Collection&gt;**](Collection.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## fetchDocumentApiDocumentDocumentIdGet

> SemantDemoSchemaDocumentsDocument fetchDocumentApiDocumentDocumentIdGet(documentId)

Fetch Document

Retrieves document by its id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FetchDocumentApiDocumentDocumentIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    documentId: documentId_example,
  } satisfies FetchDocumentApiDocumentDocumentIdGetRequest;

  try {
    const data = await api.fetchDocumentApiDocumentDocumentIdGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **documentId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**SemantDemoSchemaDocumentsDocument**](SemantDemoSchemaDocumentsDocument.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet

> DocumentDetail fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet(documentId, collectionId)

Fetch Document Chunks

Retrieves all chunks for one document and marks whether each chunk belongs to the selected collection.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    documentId: documentId_example,
    // string
    collectionId: collectionId_example,
  } satisfies FetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGetRequest;

  try {
    const data = await api.fetchDocumentChunksApiDocumentsDocumentIdCollectionIdChunksGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **documentId** | `string` |  | [Defaults to `undefined`] |
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**DocumentDetail**](DocumentDetail.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getAvailableSearchFiltersApiSearchFiltersGet

> SearchFiltersResponse getAvailableSearchFiltersApiSearchFiltersGet()

Get Available Search Filters

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetAvailableSearchFiltersApiSearchFiltersGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getAvailableSearchFiltersApiSearchFiltersGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**SearchFiltersResponse**](SearchFiltersResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getAvalaibleRagConfigurationsApiRagConfigurationsGet

> Array&lt;RagRouteConfig&gt; getAvalaibleRagConfigurationsApiRagConfigurationsGet()

Get Avalaible Rag Configurations

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetAvalaibleRagConfigurationsApiRagConfigurationsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  try {
    const data = await api.getAvalaibleRagConfigurationsApiRagConfigurationsGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

[**Array&lt;RagRouteConfig&gt;**](RagRouteConfig.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGet

> Array&lt;Chunk | null&gt; getChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGet(collectionId, documentId, orderGt, orderLt)

Get Chunks In Range

Returns all chunks of a document with order strictly greater than order_gt and/or strictly less than order_lt. Used for bulk loading gaps and neighbours.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    documentId: documentId_example,
    // number (optional)
    orderGt: 56,
    // number (optional)
    orderLt: 56,
  } satisfies GetChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGetRequest;

  try {
    const data = await api.getChunksInRangeApiCollectionsCollectionIdDocumentsDocumentIdChunksGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **documentId** | `string` |  | [Defaults to `undefined`] |
| **orderGt** | `number` |  | [Optional] [Defaults to `undefined`] |
| **orderLt** | `number` |  | [Optional] [Defaults to `undefined`] |

### Return type

[**Array&lt;Chunk | null&gt;**](Chunk.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGet

> Array&lt;Chunk&gt; getCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGet(collectionId, documentId)

Get Collection Document Chunks

Returns chunks which belong to document and collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    documentId: documentId_example,
  } satisfies GetCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGetRequest;

  try {
    const data = await api.getCollectionDocumentChunksApiCollectionsCollectionIdDocumentsDocumentIdGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **documentId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Array&lt;Chunk&gt;**](Chunk.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getCollectionDocumentsApiUserCollectionCollectionIdDocumentsGet

> Array&lt;SemantDemoSchemaDocumentsDocument&gt; getCollectionDocumentsApiUserCollectionCollectionIdDocumentsGet(collectionId)

Get Collection Documents

Returns documents which belong to collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionDocumentsApiUserCollectionCollectionIdDocumentsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies GetCollectionDocumentsApiUserCollectionCollectionIdDocumentsGetRequest;

  try {
    const data = await api.getCollectionDocumentsApiUserCollectionCollectionIdDocumentsGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Array&lt;SemantDemoSchemaDocumentsDocument&gt;**](SemantDemoSchemaDocumentsDocument.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getCollectionMembersApiCollectionsCollectionIdMembersGet

> Array&lt;UserSearchResult&gt; getCollectionMembersApiCollectionsCollectionIdMembersGet(collectionId)

Get Collection Members

Returns the users a collection is currently shared with.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionMembersApiCollectionsCollectionIdMembersGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies GetCollectionMembersApiCollectionsCollectionIdMembersGetRequest;

  try {
    const data = await api.getCollectionMembersApiCollectionsCollectionIdMembersGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Array&lt;UserSearchResult&gt;**](UserSearchResult.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getCollectionStatsApiUserCollectionCollectionIdStatsGet

> CollectionStats getCollectionStatsApiUserCollectionCollectionIdStatsGet(collectionId)

Get Collection Stats

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionStatsApiUserCollectionCollectionIdStatsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies GetCollectionStatsApiUserCollectionCollectionIdStatsGetRequest;

  try {
    const data = await api.getCollectionStatsApiUserCollectionCollectionIdStatsGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**CollectionStats**](CollectionStats.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getCollectionTagsApiCollectionsCollectionIdTagsGet

> Array&lt;Tag&gt; getCollectionTagsApiCollectionsCollectionIdTagsGet(collectionId)

Get Collection Tags

Returns tags which belong to collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionTagsApiCollectionsCollectionIdTagsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies GetCollectionTagsApiCollectionsCollectionIdTagsGetRequest;

  try {
    const data = await api.getCollectionTagsApiCollectionsCollectionIdTagsGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Array&lt;Tag&gt;**](Tag.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGet

> DocumentStats getDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGet(collectionId, documentId)

Get Document Stats

Returns per-document statistics within the given collection: chunks in collection / total, annotation count, distinct tag count.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    documentId: documentId_example,
  } satisfies GetDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGetRequest;

  try {
    const data = await api.getDocumentStatsApiCollectionsCollectionIdDocumentsDocumentIdStatsGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **documentId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**DocumentStats**](DocumentStats.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGet

> Chunk getNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGet(collectionId, documentId, direction, boundaryOrder)

Get Neighbour Chunk

Returns the chunk immediately before (direction&#x3D;prev) or after (direction&#x3D;next) the given boundary_order within the document. Marks in_collection accordingly.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    documentId: documentId_example,
    // string
    direction: direction_example,
    // number
    boundaryOrder: 56,
  } satisfies GetNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGetRequest;

  try {
    const data = await api.getNeighbourChunkApiCollectionsCollectionIdDocumentsDocumentIdNeighbourGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **documentId** | `string` |  | [Defaults to `undefined`] |
| **direction** | `string` |  | [Defaults to `undefined`] |
| **boundaryOrder** | `number` |  | [Defaults to `undefined`] |

### Return type

[**Chunk**](Chunk.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getTagApiTagsTagUuidGet

> Tag getTagApiTagsTagUuidGet(tagUuid)

Get Tag

Retrieve tag by its id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetTagApiTagsTagUuidGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    tagUuid: tagUuid_example,
  } satisfies GetTagApiTagsTagUuidGetRequest;

  try {
    const data = await api.getTagApiTagsTagUuidGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **tagUuid** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Tag**](Tag.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## healthHealthGet

> any healthHealthGet()

Health

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { HealthHealthGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.healthHealthGet();
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters

This endpoint does not need any parameter.

### Return type

**any**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## questionApiQuestionQuestionTextPost

> SummaryResponse questionApiQuestionQuestionTextPost(questionText, searchResponseInput)

Question

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { QuestionApiQuestionQuestionTextPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    questionText: questionText_example,
    // SearchResponseInput
    searchResponseInput: ...,
  } satisfies QuestionApiQuestionQuestionTextPostRequest;

  try {
    const data = await api.questionApiQuestionQuestionTextPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **questionText** | `string` |  | [Defaults to `undefined`] |
| **searchResponseInput** | [SearchResponseInput](SearchResponseInput.md) |  | |

### Return type

[**SummaryResponse**](SummaryResponse.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## ragApiRagPost

> RagResponse ragApiRagPost(ragRequestMain)

Rag

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RagApiRagPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // RagRequestMain
    ragRequestMain: ...,
  } satisfies RagApiRagPostRequest;

  try {
    const data = await api.ragApiRagPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **ragRequestMain** | [RagRequestMain](RagRequestMain.md) |  | |

### Return type

[**RagResponse**](RagResponse.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## readTagSpansApiTagSpansGet

> Array&lt;TagSpan&gt; readTagSpansApiTagSpansGet(chunkId, collectionId)

Read Tag Spans

Get stored TagSpans for a given chunk ID and collection ID.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReadTagSpansApiTagSpansGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string | Filter spans by chunk ID (optional)
    chunkId: chunkId_example,
    // string | Filter spans by collection ID (optional)
    collectionId: collectionId_example,
  } satisfies ReadTagSpansApiTagSpansGetRequest;

  try {
    const data = await api.readTagSpansApiTagSpansGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **chunkId** | `string` | Filter spans by chunk ID | [Optional] [Defaults to `undefined`] |
| **collectionId** | `string` | Filter spans by collection ID | [Optional] [Defaults to `undefined`] |

### Return type

[**Array&lt;TagSpan&gt;**](TagSpan.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## readTagSpansBatchApiTagSpansBatchPost

> { [key: string]: Array&lt;TagSpan&gt;; } readTagSpansBatchApiTagSpansBatchPost(tagSpanBatchRequest)

Read Tag Spans Batch

Get stored TagSpans for multiple chunk IDs in a single request.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReadTagSpansBatchApiTagSpansBatchPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // TagSpanBatchRequest
    tagSpanBatchRequest: ...,
  } satisfies ReadTagSpansBatchApiTagSpansBatchPostRequest;

  try {
    const data = await api.readTagSpansBatchApiTagSpansBatchPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **tagSpanBatchRequest** | [TagSpanBatchRequest](TagSpanBatchRequest.md) |  | |

### Return type

**{ [key: string]: Array<TagSpan>; }**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## removeDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDelete

> any removeDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDelete(collectionId, documentId)

Remove Document From Collection

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    documentId: documentId_example,
  } satisfies RemoveDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDeleteRequest;

  try {
    const data = await api.removeDocumentFromCollectionApiCollectionsCollectionIdDocumentsDocumentIdDelete(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **documentId** | `string` |  | [Defaults to `undefined`] |

### Return type

**any**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## saveAppFeedbackApiV1FeedbackPost

> any saveAppFeedbackApiV1FeedbackPost(appFeedbackRequest)

Save App Feedback

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SaveAppFeedbackApiV1FeedbackPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // AppFeedbackRequest
    appFeedbackRequest: ...,
  } satisfies SaveAppFeedbackApiV1FeedbackPostRequest;

  try {
    const data = await api.saveAppFeedbackApiV1FeedbackPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **appFeedbackRequest** | [AppFeedbackRequest](AppFeedbackRequest.md) |  | |

### Return type

**any**

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## saveFeedbackApiRagFeedbackPost

> any saveFeedbackApiRagFeedbackPost(feedbackRequest)

Save Feedback

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SaveFeedbackApiRagFeedbackPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // FeedbackRequest
    feedbackRequest: ...,
  } satisfies SaveFeedbackApiRagFeedbackPostRequest;

  try {
    const data = await api.saveFeedbackApiRagFeedbackPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **feedbackRequest** | [FeedbackRequest](FeedbackRequest.md) |  | |

### Return type

**any**

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## searchApiSearchPost

> SearchResponseOutput searchApiSearchPost(searchRequest)

Search

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SearchApiSearchPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // SearchRequest
    searchRequest: ...,
  } satisfies SearchApiSearchPostRequest;

  try {
    const data = await api.searchApiSearchPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **searchRequest** | [SearchRequest](SearchRequest.md) |  | |

### Return type

[**SearchResponseOutput**](SearchResponseOutput.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## searchUsersApiUsersSearchGet

> Array&lt;UserSearchResult&gt; searchUsersApiUsersSearchGet(q)

Search Users

Search users by username substring. Returns at most 4 matches. Requires authentication.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SearchUsersApiUsersSearchGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string | Username substring to search (min 3 characters)
    q: q_example,
  } satisfies SearchUsersApiUsersSearchGetRequest;

  try {
    const data = await api.searchUsersApiUsersSearchGet(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **q** | `string` | Username substring to search (min 3 characters) | [Defaults to `undefined`] |

### Return type

[**Array&lt;UserSearchResult&gt;**](UserSearchResult.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## shareCollectionApiCollectionsCollectionIdSharePost

> Collection shareCollectionApiCollectionsCollectionIdSharePost(collectionId, shareCollectionRequest)

Share Collection

Shares a collection with another user. Only the collection\&#39;s owner may share it.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ShareCollectionApiCollectionsCollectionIdSharePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    collectionId: collectionId_example,
    // ShareCollectionRequest
    shareCollectionRequest: ...,
  } satisfies ShareCollectionApiCollectionsCollectionIdSharePostRequest;

  try {
    const data = await api.shareCollectionApiCollectionsCollectionIdSharePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **shareCollectionRequest** | [ShareCollectionRequest](ShareCollectionRequest.md) |  | |

### Return type

[**Collection**](Collection.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## suggestSpansOptimizedApiAiSuggestSpansOptimizedPost

> suggestSpansOptimizedApiAiSuggestSpansOptimizedPost(suggestSpansRequest)

Suggest Spans Optimized

Optimized AI span suggestion: per tag, the Topicer service uses vector similarity to pre-filter only the most relevant chunks before invoking the LLM. NDJSON results are streamed straight through to the client as they arrive.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SuggestSpansOptimizedApiAiSuggestSpansOptimizedPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // SuggestSpansRequest
    suggestSpansRequest: ...,
  } satisfies SuggestSpansOptimizedApiAiSuggestSpansOptimizedPostRequest;

  try {
    const data = await api.suggestSpansOptimizedApiAiSuggestSpansOptimizedPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **suggestSpansRequest** | [SuggestSpansRequest](SuggestSpansRequest.md) |  | |

### Return type

`void` (Empty response body)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/x-ndjson`, `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Stream of SuggestSpansChunkResult, one JSON object per line. |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## suggestSpansSelectionApiAiSuggestSpansSelectionPost

> suggestSpansSelectionApiAiSuggestSpansSelectionPost(suggestSpansSelectionRequest)

Suggest Spans Selection

Run AI span suggestion on a single user-selected passage that may span multiple consecutive chunks. The frontend sends the chunk IDs in document order; offsets are measured against the concatenation of their text.  The endpoint streams NDJSON (&#x60;&#x60;application/x-ndjson&#x60;&#x60;) — one :class:&#x60;SuggestSpansChunkResult&#x60; per persisted span — so the UI can render suggestions incrementally and abort the run mid-flight by closing the connection.  Each persisted span is anchored on the chunk that contains its *start* offset (mirroring how non-AI cross-chunk spans are stored), not on the first chunk of the selection.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SuggestSpansSelectionApiAiSuggestSpansSelectionPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // SuggestSpansSelectionRequest
    suggestSpansSelectionRequest: ...,
  } satisfies SuggestSpansSelectionApiAiSuggestSpansSelectionPostRequest;

  try {
    const data = await api.suggestSpansSelectionApiAiSuggestSpansSelectionPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **suggestSpansSelectionRequest** | [SuggestSpansSelectionRequest](SuggestSpansSelectionRequest.md) |  | |

### Return type

`void` (Empty response body)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/x-ndjson`, `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Stream of SuggestSpansChunkResult, one JSON object per line. One event per persisted auto span; a final event with empty &#x60;&#x60;spans&#x60;&#x60; and a populated &#x60;&#x60;error&#x60;&#x60; is emitted on Topicer failure. |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## suggestSpansThoroughApiAiSuggestSpansThoroughPost

> suggestSpansThoroughApiAiSuggestSpansThoroughPost(suggestSpansRequest)

Suggest Spans Thorough

Thorough AI span suggestion: every collection chunk in the document is sent to the LLM together with all selected tags.  Persists each accepted proposal as a span with type &#x60;&#x60;auto&#x60;&#x60;. The endpoint streams NDJSON lines (&#x60;&#x60;application/x-ndjson&#x60;&#x60;); each line is a :class:&#x60;SuggestSpansChunkResult&#x60;.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SuggestSpansThoroughApiAiSuggestSpansThoroughPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // SuggestSpansRequest
    suggestSpansRequest: ...,
  } satisfies SuggestSpansThoroughApiAiSuggestSpansThoroughPostRequest;

  try {
    const data = await api.suggestSpansThoroughApiAiSuggestSpansThoroughPost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **suggestSpansRequest** | [SuggestSpansRequest](SuggestSpansRequest.md) |  | |

### Return type

`void` (Empty response body)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/x-ndjson`, `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Stream of SuggestSpansChunkResult, one JSON object per line. |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## summarizeApiSummarizeSummaryTypePost

> SummaryResponse summarizeApiSummarizeSummaryTypePost(summaryType, searchResponseInput)

Summarize

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SummarizeApiSummarizeSummaryTypePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    summaryType: summaryType_example,
    // SearchResponseInput
    searchResponseInput: ...,
  } satisfies SummarizeApiSummarizeSummaryTypePostRequest;

  try {
    const data = await api.summarizeApiSummarizeSummaryTypePost(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **summaryType** | `string` |  | [Defaults to `undefined`] |
| **searchResponseInput** | [SearchResponseInput](SearchResponseInput.md) |  | |

### Return type

[**SummaryResponse**](SummaryResponse.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## unshareCollectionApiCollectionsCollectionIdShareUserIdDelete

> Collection unshareCollectionApiCollectionsCollectionIdShareUserIdDelete(collectionId, userId)

Unshare Collection

Revokes a collection share. Only the collection\&#39;s owner may unshare it.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UnshareCollectionApiCollectionsCollectionIdShareUserIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    collectionId: collectionId_example,
    // string
    userId: 38400000-8cf0-11bd-b23e-10b96e4ef00d,
  } satisfies UnshareCollectionApiCollectionsCollectionIdShareUserIdDeleteRequest;

  try {
    const data = await api.unshareCollectionApiCollectionsCollectionIdShareUserIdDelete(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **userId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**Collection**](Collection.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## updateCollectionApiUserCollectionsCollectionIdPatch

> Collection updateCollectionApiUserCollectionsCollectionIdPatch(collectionId, patchCollection)

Update Collection

Updates collection name/description/color

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateCollectionApiUserCollectionsCollectionIdPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
    // PatchCollection
    patchCollection: ...,
  } satisfies UpdateCollectionApiUserCollectionsCollectionIdPatchRequest;

  try {
    const data = await api.updateCollectionApiUserCollectionsCollectionIdPatch(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **patchCollection** | [PatchCollection](PatchCollection.md) |  | |

### Return type

[**Collection**](Collection.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## updateCollectionOwnerApiCollectionsCollectionIdOwnerPatch

> Collection updateCollectionOwnerApiCollectionsCollectionIdOwnerPatch(collectionId, patchCollectionOwner)

Update Collection Owner

Reassigns ownership of a collection to a different user. Admin only.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateCollectionOwnerApiCollectionsCollectionIdOwnerPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string
    collectionId: collectionId_example,
    // PatchCollectionOwner
    patchCollectionOwner: ...,
  } satisfies UpdateCollectionOwnerApiCollectionsCollectionIdOwnerPatchRequest;

  try {
    const data = await api.updateCollectionOwnerApiCollectionsCollectionIdOwnerPatch(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **collectionId** | `string` |  | [Defaults to `undefined`] |
| **patchCollectionOwner** | [PatchCollectionOwner](PatchCollectionOwner.md) |  | |

### Return type

[**Collection**](Collection.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## updateTagApiTagsTagUuidPatch

> Tag updateTagApiTagsTagUuidPatch(tagUuid, patchTag)

Update Tag

Updates a tag

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateTagApiTagsTagUuidPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    tagUuid: tagUuid_example,
    // PatchTag
    patchTag: ...,
  } satisfies UpdateTagApiTagsTagUuidPatchRequest;

  try {
    const data = await api.updateTagApiTagsTagUuidPatch(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **tagUuid** | `string` |  | [Defaults to `undefined`] |
| **patchTag** | [PatchTag](PatchTag.md) |  | |

### Return type

[**Tag**](Tag.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## updateTagSpanApiTagSpansSpanIdPatch

> TagSpan updateTagSpanApiTagSpansSpanIdPatch(spanId, patchSpan)

Update Tag Span

Update TagSpan\&#39;s information (start, end, tagId, ...)

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateTagSpanApiTagSpansSpanIdPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    spanId: spanId_example,
    // PatchSpan
    patchSpan: ...,
  } satisfies UpdateTagSpanApiTagSpansSpanIdPatchRequest;

  try {
    const data = await api.updateTagSpanApiTagSpansSpanIdPatch(body);
    console.log(data);
  } catch (error) {
    console.error(error);
  }
}

// Run the test
example().catch(console.error);
```

### Parameters


| Name | Type | Description  | Notes |
|------------- | ------------- | ------------- | -------------|
| **spanId** | `string` |  | [Defaults to `undefined`] |
| **patchSpan** | [PatchSpan](PatchSpan.md) |  | |

### Return type

[**TagSpan**](TagSpan.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

