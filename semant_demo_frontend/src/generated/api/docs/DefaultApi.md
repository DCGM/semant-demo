# DefaultApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost**](DefaultApi.md#addchunktocollectionapiusercollectionscollectionidchunkschunkidpost) | **POST** /api/user_collections/{collection_id}/chunks/{chunk_id} | Add Chunk To Collection |
| [**addDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPost**](DefaultApi.md#adddocumenttocollectionapiusercollectionscollectioniddocumentsdocumentidpost) | **POST** /api/user_collections/{collection_id}/documents/{document_id} | Add Document To Collection |
| [**browseDocumentsApiDocumentsBrowseGet**](DefaultApi.md#browsedocumentsapidocumentsbrowseget) | **GET** /api/documents/browse | Browse Documents |
| [**bulkUpdateTagSpansApiTagSpansBulkUpdatePost**](DefaultApi.md#bulkupdatetagspansapitagspansbulkupdatepost) | **POST** /api/tag_spans/bulk_update | Bulk Update Tag Spans |
| [**corpusOverviewApiAnalyticsCorpusOverviewGet**](DefaultApi.md#corpusoverviewapianalyticscorpusoverviewget) | **GET** /api/analytics/corpus/overview | Corpus Overview |
| [**countDocumentChunksApiDocumentsDocumentIdChunksCountGet**](DefaultApi.md#countdocumentchunksapidocumentsdocumentidchunkscountget) | **GET** /api/documents/{document_id}/chunks/count | Count Document Chunks |
| [**createTagApiTagsPost**](DefaultApi.md#createtagapitagspost) | **POST** /api/tags | Create Tag |
| [**createTagSpanApiTagSpansPost**](DefaultApi.md#createtagspanapitagspanspost) | **POST** /api/tag_spans | Create Tag Span |
| [**createUserCollectionApiUserCollectionsPost**](DefaultApi.md#createusercollectionapiusercollectionspost) | **POST** /api/user_collections | Create User Collection |
| [**deleteAutoSpansApiAiAutoSpansDeletePost**](DefaultApi.md#deleteautospansapiaiautospansdeletepost) | **POST** /api/ai/auto_spans/delete | Delete Auto Spans |
| [**deleteCollectionApiUserCollectionsCollectionIdDelete**](DefaultApi.md#deletecollectionapiusercollectionscollectioniddelete) | **DELETE** /api/user_collections/{collection_id} | Delete Collection |
| [**deleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePost**](DefaultApi.md#deletespansfortagsindocumentapitagspansindocumentdeletepost) | **POST** /api/tag_spans/in_document/delete | Delete Spans For Tags In Document |
| [**deleteTagApiTagsTagUuidDelete**](DefaultApi.md#deletetagapitagstaguuiddelete) | **DELETE** /api/tags/{tag_uuid} | Delete Tag |
| [**deleteTagSpanApiTagSpansSpanIdDelete**](DefaultApi.md#deletetagspanapitagspansspaniddelete) | **DELETE** /api/tag_spans/{span_id} | Delete Tag Span |
| [**discussSpanApiAiDiscussSpanPost**](DefaultApi.md#discussspanapiaidiscussspanpost) | **POST** /api/ai/discuss_span | Discuss Span |
| [**explainSelectionApiRagExplainPost**](DefaultApi.md#explainselectionapiragexplainpost) | **POST** /api/rag/explain | Explain Selection |
| [**fetchCollectionApiUserCollectionsCollectionIdGet**](DefaultApi.md#fetchcollectionapiusercollectionscollectionidget) | **GET** /api/user_collections/{collection_id} | Fetch Collection |
| [**fetchCollectionDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdGet**](DefaultApi.md#fetchcollectiondocumentapiusercollectionscollectioniddocumentsdocumentidget) | **GET** /api/user_collections/{collection_id}/documents/{document_id} | Fetch Collection Document |
| [**fetchCollectionsApiUserCollectionsGet**](DefaultApi.md#fetchcollectionsapiusercollectionsget) | **GET** /api/user_collections | Fetch Collections |
| [**fetchDocumentApiDocumentDocumentIdGet**](DefaultApi.md#fetchdocumentapidocumentdocumentidget) | **GET** /api/document/{document_id} | Fetch Document |
| [**getAvailableSearchFiltersApiSearchFiltersGet**](DefaultApi.md#getavailablesearchfiltersapisearchfiltersget) | **GET** /api/search/filters | Get Available Search Filters |
| [**getAvailableSearchVectorsApiSearchVectorsGet**](DefaultApi.md#getavailablesearchvectorsapisearchvectorsget) | **GET** /api/search/vectors | Get Available Search Vectors |
| [**getAvalaibleRagConfigurationsApiRagConfigurationsGet**](DefaultApi.md#getavalaibleragconfigurationsapiragconfigurationsget) | **GET** /api/rag/configurations | Get Avalaible Rag Configurations |
| [**getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet**](DefaultApi.md#getchunksinrangeapiusercollectionscollectioniddocumentsdocumentidchunksrangeget) | **GET** /api/user_collections/{collection_id}/documents/{document_id}/chunks/range | Get Chunks In Range |
| [**getCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGet**](DefaultApi.md#getcollectiondocumentchunksapiusercollectionscollectioniddocumentsdocumentidchunksget) | **GET** /api/user_collections/{collection_id}/documents/{document_id}/chunks | Get Collection Document Chunks |
| [**getCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGet**](DefaultApi.md#getcollectiondocumentsapiusercollectionscollectioniddocumentsget) | **GET** /api/user_collections/{collection_id}/documents | Get Collection Documents |
| [**getCollectionMembersApiUserCollectionsCollectionIdMembersGet**](DefaultApi.md#getcollectionmembersapiusercollectionscollectionidmembersget) | **GET** /api/user_collections/{collection_id}/members | Get Collection Members |
| [**getCollectionStatsApiUserCollectionsCollectionIdStatsGet**](DefaultApi.md#getcollectionstatsapiusercollectionscollectionidstatsget) | **GET** /api/user_collections/{collection_id}/stats | Get Collection Stats |
| [**getCollectionTagsApiUserCollectionsCollectionIdTagsGet**](DefaultApi.md#getcollectiontagsapiusercollectionscollectionidtagsget) | **GET** /api/user_collections/{collection_id}/tags | Get Collection Tags |
| [**getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet**](DefaultApi.md#getdocumentstatsapiusercollectionscollectioniddocumentsdocumentidstatsget) | **GET** /api/user_collections/{collection_id}/documents/{document_id}/stats | Get Document Stats |
| [**getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet**](DefaultApi.md#getneighbourchunkapiusercollectionscollectioniddocumentsdocumentidchunksneighbourget) | **GET** /api/user_collections/{collection_id}/documents/{document_id}/chunks/neighbour | Get Neighbour Chunk |
| [**getTagApiTagsTagUuidGet**](DefaultApi.md#gettagapitagstaguuidget) | **GET** /api/tags/{tag_uuid} | Get Tag |
| [**healthHealthGet**](DefaultApi.md#healthhealthget) | **GET** /health | Health |
| [**questionApiQuestionPost**](DefaultApi.md#questionapiquestionpost) | **POST** /api/question | Question |
| [**ragApiRagPost**](DefaultApi.md#ragapiragpost) | **POST** /api/rag | Rag |
| [**readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet**](DefaultApi.md#readdocumentadjacentchunksapidocumentsdocumentidchunkschunkidadjacentget) | **GET** /api/documents/{document_id}/chunks/{chunk_id}/adjacent | Read Document Adjacent Chunks |
| [**readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet**](DefaultApi.md#readdocumentchunkwindowapidocumentsdocumentidchunkschunkidwindowget) | **GET** /api/documents/{document_id}/chunks/{chunk_id}/window | Read Document Chunk Window |
| [**readTagSpansApiTagSpansGet**](DefaultApi.md#readtagspansapitagspansget) | **GET** /api/tag_spans | Read Tag Spans |
| [**readTagSpansBatchApiTagSpansBatchPost**](DefaultApi.md#readtagspansbatchapitagspansbatchpost) | **POST** /api/tag_spans/batch | Read Tag Spans Batch |
| [**removeChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDelete**](DefaultApi.md#removechunkfromcollectionapiusercollectionscollectionidchunkschunkiddelete) | **DELETE** /api/user_collections/{collection_id}/chunks/{chunk_id} | Remove Chunk From Collection |
| [**removeDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDelete**](DefaultApi.md#removedocumentfromcollectionapiusercollectionscollectioniddocumentsdocumentiddelete) | **DELETE** /api/user_collections/{collection_id}/documents/{document_id} | Remove Document From Collection |
| [**saveAppFeedbackApiV1FeedbackPost**](DefaultApi.md#saveappfeedbackapiv1feedbackpost) | **POST** /api/v1/feedback | Save App Feedback |
| [**saveFeedbackApiRagFeedbackPost**](DefaultApi.md#savefeedbackapiragfeedbackpost) | **POST** /api/rag/feedback | Save Feedback |
| [**searchApiSearchPost**](DefaultApi.md#searchapisearchpost) | **POST** /api/search | Search |
| [**searchUsersApiUsersSearchGet**](DefaultApi.md#searchusersapiuserssearchget) | **GET** /api/users/search | Search Users |
| [**shareCollectionApiUserCollectionsCollectionIdSharePost**](DefaultApi.md#sharecollectionapiusercollectionscollectionidsharepost) | **POST** /api/user_collections/{collection_id}/share | Share Collection |
| [**suggestSpansOptimizedApiAiSuggestSpansOptimizedPost**](DefaultApi.md#suggestspansoptimizedapiaisuggestspansoptimizedpost) | **POST** /api/ai/suggest_spans/optimized | Suggest Spans Optimized |
| [**suggestSpansSelectionApiAiSuggestSpansSelectionPost**](DefaultApi.md#suggestspansselectionapiaisuggestspansselectionpost) | **POST** /api/ai/suggest_spans/selection | Suggest Spans Selection |
| [**suggestSpansThoroughApiAiSuggestSpansThoroughPost**](DefaultApi.md#suggestspansthoroughapiaisuggestspansthoroughpost) | **POST** /api/ai/suggest_spans/thorough | Suggest Spans Thorough |
| [**summarizeApiSummarizeSummaryTypePost**](DefaultApi.md#summarizeapisummarizesummarytypepost) | **POST** /api/summarize/{summary_type} | Summarize |
| [**summarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPost**](DefaultApi.md#summarizedocumentapiusercollectionscollectioniddocumentsdocumentidsummarypost) | **POST** /api/user_collections/{collection_id}/documents/{document_id}/summary | Summarize Document |
| [**unshareCollectionApiUserCollectionsCollectionIdShareUserIdDelete**](DefaultApi.md#unsharecollectionapiusercollectionscollectionidshareuseriddelete) | **DELETE** /api/user_collections/{collection_id}/share/{user_id} | Unshare Collection |
| [**updateCollectionApiUserCollectionsCollectionIdPatch**](DefaultApi.md#updatecollectionapiusercollectionscollectionidpatch) | **PATCH** /api/user_collections/{collection_id} | Update Collection |
| [**updateCollectionOwnerApiUserCollectionsCollectionIdOwnerPatch**](DefaultApi.md#updatecollectionownerapiusercollectionscollectionidownerpatch) | **PATCH** /api/user_collections/{collection_id}/owner | Update Collection Owner |
| [**updateTagApiTagsTagUuidPatch**](DefaultApi.md#updatetagapitagstaguuidpatch) | **PATCH** /api/tags/{tag_uuid} | Update Tag |
| [**updateTagSpanApiTagSpansSpanIdPatch**](DefaultApi.md#updatetagspanapitagspansspanidpatch) | **PATCH** /api/tag_spans/{span_id} | Update Tag Span |



## addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost

> WriteResult addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost(collectionId, chunkId)

Add Chunk To Collection

Connects chunk with user collection, and the chunk\&#39;s document with the collection. Owner only. The result reports each link; &#x60;&#x60;outcome&#x60;&#x60; is &#x60;&#x60;partial&#x60;&#x60; when the chunk was linked but its document could not be.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { AddChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPostRequest } from '';

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
    chunkId: chunkId_example,
  } satisfies AddChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPostRequest;

  try {
    const data = await api.addChunkToCollectionApiUserCollectionsCollectionIdChunksChunkIdPost(body);
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
| **chunkId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**WriteResult**](WriteResult.md)

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


## addDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPost

> WriteResult addDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPost(collectionId, documentId)

Add Document To Collection

Adds document to collection and also links all its chunks to that collection. Owner only. The result lists linked chunks/document and failed links; &#x60;&#x60;outcome&#x60;&#x60; tells whether the document was added completely, partially or not at all.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { AddDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPostRequest } from '';

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
    documentId: documentId_example,
  } satisfies AddDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPostRequest;

  try {
    const data = await api.addDocumentToCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdPost(body);
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

[**WriteResult**](WriteResult.md)

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


## browseDocumentsApiDocumentsBrowseGet

> DocumentBrowse browseDocumentsApiDocumentsBrowseGet(collectionId, limit, offset, sortBy, sortDesc, title, author, publisher, documentType)

Browse Documents

Browses the corpus with pagination, filtering and sorting options. With &#x60;&#x60;collection_id&#x60;&#x60; only that collection\&#39;s documents are browsed, which needs read access to it.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { BrowseDocumentsApiDocumentsBrowseGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## bulkUpdateTagSpansApiTagSpansBulkUpdatePost

> BulkUpdateSpansResponse bulkUpdateTagSpansApiTagSpansBulkUpdatePost(bulkUpdateSpansRequest)

Bulk Update Tag Spans

Apply the same :class:&#x60;PatchSpan&#x60; to many spans in one round-trip.  Used by the AI-assist \&quot;Approve / Reject all selected\&quot; action — collapses N PATCH calls into one and lets the server fan them out concurrently.  All spans must belong to one collection the user may annotate; otherwise nothing is updated. Updates are best effort: &#x60;&#x60;spans&#x60;&#x60; holds the updated spans and &#x60;&#x60;failed&#x60;&#x60; the spans that could not be updated (&#x60;&#x60;update_span&#x60;&#x60;) and the chunk tag updates that failed (&#x60;&#x60;update_chunk_tags&#x60;&#x60;, item &#x60;&#x60;chunk_id:tag_id&#x60;&#x60;).

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { BulkUpdateTagSpansApiTagSpansBulkUpdatePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## corpusOverviewApiAnalyticsCorpusOverviewGet

> CorpusOverview corpusOverviewApiAnalyticsCorpusOverviewGet()

Corpus Overview

Document counts of the searchable corpus (public): the total and the documents by publication decade, source library and document language, with unknown values and unavailable properties stated explicitly. A recent result may be served again (&#x60;&#x60;data_source&#x60;&#x60;, &#x60;&#x60;computed_at&#x60;&#x60;).

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CorpusOverviewApiAnalyticsCorpusOverviewGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.corpusOverviewApiAnalyticsCorpusOverviewGet();
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

[**CorpusOverview**](CorpusOverview.md)

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


## countDocumentChunksApiDocumentsDocumentIdChunksCountGet

> number countDocumentChunksApiDocumentsDocumentIdChunksCountGet(documentId)

Count Document Chunks

Returns the total number of chunks in the given document (public corpus data).

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

Creates a tag in the collection, or returns the existing tag with the same fields. If the tag cannot be added to its collection it is removed again and the request fails (500); creating it again is safe.

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

> TagSpanWriteResult createTagSpanApiTagSpansPost(postSpan)

Create Tag Span

Adds new TagSpan and the matching chunk tag reference. &#x60;&#x60;outcome&#x60;&#x60; is &#x60;&#x60;partial&#x60;&#x60; when the span was saved but the chunk tag could not be updated. Offsets outside the text of the chunk\&#39;s document are rejected (400).

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateTagSpanApiTagSpansPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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

[**TagSpanWriteResult**](TagSpanWriteResult.md)

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

Bulk-delete unresolved AI proposals (&#x60;&#x60;type &#x3D;&#x3D; \&#39;auto\&#39;&#x60;&#x60;) within a single (collection, document) for the given tag UUIDs.  Useful for cleaning up suggestions the user did not get around to approving or rejecting. Best effort: &#x60;&#x60;succeeded&#x60;&#x60; lists the deleted spans and &#x60;&#x60;failed&#x60;&#x60; those that could not be deleted (&#x60;&#x60;delete_span&#x60;&#x60;) and the chunk tag updates that failed (&#x60;&#x60;update_chunk_tags&#x60;&#x60;, item &#x60;&#x60;chunk_id:tag_id&#x60;&#x60;).

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


## deleteCollectionApiUserCollectionsCollectionIdDelete

> deleteCollectionApiUserCollectionsCollectionIdDelete(collectionId)

Delete Collection

Deletes a collection with its tags and annotations. Owner only. If a step fails, the request fails (500) with the completed steps in the body; completed deletions are kept and deleting again continues.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteCollectionApiUserCollectionsCollectionIdDeleteRequest } from '';

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
  } satisfies DeleteCollectionApiUserCollectionsCollectionIdDeleteRequest;

  try {
    const data = await api.deleteCollectionApiUserCollectionsCollectionIdDelete(body);
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

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

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

Bulk-delete approved (&#x60;&#x60;type &#x3D;&#x3D; \&#39;pos\&#39;&#x60;&#x60;) spans for the given tag ids within a single (collection, document) scope. Negatives and unresolved auto suggestions are left untouched.  Best effort: &#x60;&#x60;succeeded&#x60;&#x60; lists the deleted spans and &#x60;&#x60;failed&#x60;&#x60; those that could not be deleted (&#x60;&#x60;delete_span&#x60;&#x60;) and the chunk tag updates that failed (&#x60;&#x60;update_chunk_tags&#x60;&#x60;, item &#x60;&#x60;chunk_id:tag_id&#x60;&#x60;).

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteSpansForTagsInDocumentApiTagSpansInDocumentDeletePostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## deleteTagApiTagsTagUuidDelete

> deleteTagApiTagsTagUuidDelete(tagUuid)

Delete Tag

Deletes the tag with its annotations. If a step fails, the request fails (500) with the completed steps in the body; completed deletions are kept and deleting again continues.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteTagApiTagsTagUuidDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

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

> WriteResult deleteTagSpanApiTagSpansSpanIdDelete(spanId)

Delete Tag Span

Delete a TagSpan and the chunk tag reference no other span backs. &#x60;&#x60;outcome&#x60;&#x60; is &#x60;&#x60;partial&#x60;&#x60; when the span was deleted but the chunk tag could not be updated.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { DeleteTagSpanApiTagSpansSpanIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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

[**WriteResult**](WriteResult.md)

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


## discussSpanApiAiDiscussSpanPost

> discussSpanApiAiDiscussSpanPost(discussSpanRequest)

Discuss Span

Stream an assistant reply discussing whether the given span fits its tag.  The request body carries the full chat history; the backend resolves span / document / tag context and prepends it as a system message before streaming the reply from the span_chat feature\&#39;s model tier.

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
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## fetchCollectionDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdGet

> DocumentDetail fetchCollectionDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdGet(collectionId, documentId)

Fetch Collection Document

Retrieves the document with all its chunks and marks whether each chunk belongs to the collection. Collection-scoped (needs read access); corpus-only document reads stay under &#x60;&#x60;/api/documents&#x60;&#x60;.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FetchCollectionDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdGetRequest } from '';

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
    documentId: documentId_example,
  } satisfies FetchCollectionDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdGetRequest;

  try {
    const data = await api.fetchCollectionDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdGet(body);
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

[**DocumentDetail**](DocumentDetail.md)

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

> Document fetchDocumentApiDocumentDocumentIdGet(documentId)

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

[**Document**](Document.md)

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


## getAvailableSearchVectorsApiSearchVectorsGet

> SearchVectorsResponse getAvailableSearchVectorsApiSearchVectorsGet()

Get Available Search Vectors

The search vectors a search request may select, and the default one.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetAvailableSearchVectorsApiSearchVectorsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getAvailableSearchVectorsApiSearchVectorsGet();
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

[**SearchVectorsResponse**](SearchVectorsResponse.md)

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


## getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet

> Array&lt;CollectionChunk | null&gt; getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet(collectionId, documentId, orderGt, orderLt)

Get Chunks In Range

Returns all chunks of a document (also those outside the collection, marked by in_collection) with order strictly greater than order_gt and/or strictly less than order_lt. Used for bulk loading gaps and neighbours.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGetRequest } from '';

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
    documentId: documentId_example,
    // number (optional)
    orderGt: 56,
    // number (optional)
    orderLt: 56,
  } satisfies GetChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGetRequest;

  try {
    const data = await api.getChunksInRangeApiUserCollectionsCollectionIdDocumentsDocumentIdChunksRangeGet(body);
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

[**Array&lt;CollectionChunk | null&gt;**](CollectionChunk.md)

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


## getCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGet

> Array&lt;CollectionChunk&gt; getCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGet(collectionId, documentId)

Get Collection Document Chunks

Returns the document\&#39;s chunks that belong to the collection, in order.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGetRequest } from '';

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
    documentId: documentId_example,
  } satisfies GetCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGetRequest;

  try {
    const data = await api.getCollectionDocumentChunksApiUserCollectionsCollectionIdDocumentsDocumentIdChunksGet(body);
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

[**Array&lt;CollectionChunk&gt;**](CollectionChunk.md)

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


## getCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGet

> Array&lt;Document&gt; getCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGet(collectionId)

Get Collection Documents

Returns documents which belong to collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGetRequest } from '';

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
  } satisfies GetCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGetRequest;

  try {
    const data = await api.getCollectionDocumentsApiUserCollectionsCollectionIdDocumentsGet(body);
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

[**Array&lt;Document&gt;**](Document.md)

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


## getCollectionMembersApiUserCollectionsCollectionIdMembersGet

> Array&lt;UserSearchResult&gt; getCollectionMembersApiUserCollectionsCollectionIdMembersGet(collectionId)

Get Collection Members

Returns the users a collection is currently shared with. Owner and shared users.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionMembersApiUserCollectionsCollectionIdMembersGetRequest } from '';

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
  } satisfies GetCollectionMembersApiUserCollectionsCollectionIdMembersGetRequest;

  try {
    const data = await api.getCollectionMembersApiUserCollectionsCollectionIdMembersGet(body);
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


## getCollectionStatsApiUserCollectionsCollectionIdStatsGet

> CollectionStats getCollectionStatsApiUserCollectionsCollectionIdStatsGet(collectionId)

Get Collection Stats

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionStatsApiUserCollectionsCollectionIdStatsGetRequest } from '';

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
  } satisfies GetCollectionStatsApiUserCollectionsCollectionIdStatsGetRequest;

  try {
    const data = await api.getCollectionStatsApiUserCollectionsCollectionIdStatsGet(body);
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


## getCollectionTagsApiUserCollectionsCollectionIdTagsGet

> Array&lt;Tag&gt; getCollectionTagsApiUserCollectionsCollectionIdTagsGet(collectionId)

Get Collection Tags

Returns tags which belong to collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionTagsApiUserCollectionsCollectionIdTagsGetRequest } from '';

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
  } satisfies GetCollectionTagsApiUserCollectionsCollectionIdTagsGetRequest;

  try {
    const data = await api.getCollectionTagsApiUserCollectionsCollectionIdTagsGet(body);
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


## getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet

> DocumentStats getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet(collectionId, documentId)

Get Document Stats

Returns per-document statistics within the given collection: chunks in collection / total, annotation count, distinct tag count.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGetRequest } from '';

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
    documentId: documentId_example,
  } satisfies GetDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGetRequest;

  try {
    const data = await api.getDocumentStatsApiUserCollectionsCollectionIdDocumentsDocumentIdStatsGet(body);
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


## getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet

> CollectionChunk getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet(collectionId, documentId, direction, boundaryOrder)

Get Neighbour Chunk

Returns the chunk immediately before (direction&#x3D;prev) or after (direction&#x3D;next) the given boundary_order within the document. Marks in_collection accordingly.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGetRequest } from '';

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
    documentId: documentId_example,
    // string
    direction: direction_example,
    // number
    boundaryOrder: 56,
  } satisfies GetNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGetRequest;

  try {
    const data = await api.getNeighbourChunkApiUserCollectionsCollectionIdDocumentsDocumentIdChunksNeighbourGet(body);
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

[**CollectionChunk**](CollectionChunk.md)

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
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## questionApiQuestionPost

> SummaryResponse questionApiQuestionPost(questionRequest)

Question

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { QuestionApiQuestionPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // QuestionRequest
    questionRequest: ...,
  } satisfies QuestionApiQuestionPostRequest;

  try {
    const data = await api.questionApiQuestionPost(body);
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
| **questionRequest** | [QuestionRequest](QuestionRequest.md) |  | |

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


## readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet

> AdjacentChunks readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet(documentId, chunkId, direction, limit)

Read Document Adjacent Chunks

Returns up to &#x60;&#x60;limit&#x60;&#x60; chunks directly before or after the chunk, in document order, without the chunk itself (public corpus data). Extends a passage read with &#x60;&#x60;/window&#x60;&#x60; without reading the document metadata or chunk count again.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReadDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    documentId: documentId_example,
    // string
    chunkId: chunkId_example,
    // 'before' | 'after'
    direction: direction_example,
    // number (optional)
    limit: 56,
  } satisfies ReadDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGetRequest;

  try {
    const data = await api.readDocumentAdjacentChunksApiDocumentsDocumentIdChunksChunkIdAdjacentGet(body);
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
| **chunkId** | `string` |  | [Defaults to `undefined`] |
| **direction** | `before`, `after` |  | [Defaults to `undefined`] [Enum: before, after] |
| **limit** | `number` |  | [Optional] [Defaults to `5`] |

### Return type

[**AdjacentChunks**](AdjacentChunks.md)

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


## readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet

> DocumentChunkWindow readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet(documentId, chunkId, before, after)

Read Document Chunk Window

Returns the chunk and up to &#x60;&#x60;before&#x60;&#x60;/&#x60;&#x60;after&#x60;&#x60; neighbouring chunks of its document, in document order (public corpus data). Used to show a search hit in its context.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReadDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    documentId: documentId_example,
    // string
    chunkId: chunkId_example,
    // number (optional)
    before: 56,
    // number (optional)
    after: 56,
  } satisfies ReadDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGetRequest;

  try {
    const data = await api.readDocumentChunkWindowApiDocumentsDocumentIdChunksChunkIdWindowGet(body);
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
| **chunkId** | `string` |  | [Defaults to `undefined`] |
| **before** | `number` |  | [Optional] [Defaults to `3`] |
| **after** | `number` |  | [Optional] [Defaults to `3`] |

### Return type

[**DocumentChunkWindow**](DocumentChunkWindow.md)

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


## readTagSpansApiTagSpansGet

> Array&lt;TagSpan&gt; readTagSpansApiTagSpansGet(collectionId, chunkId)

Read Tag Spans

Get stored TagSpans of a collection, optionally for one chunk.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReadTagSpansApiTagSpansGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

  const body = {
    // string | Collection whose annotations to return
    collectionId: collectionId_example,
    // string | Filter spans by chunk ID (optional)
    chunkId: chunkId_example,
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
| **collectionId** | `string` | Collection whose annotations to return | [Defaults to `undefined`] |
| **chunkId** | `string` | Filter spans by chunk ID | [Optional] [Defaults to `undefined`] |

### Return type

[**Array&lt;TagSpan&gt;**](TagSpan.md)

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


## readTagSpansBatchApiTagSpansBatchPost

> { [key: string]: Array&lt;TagSpan&gt;; } readTagSpansBatchApiTagSpansBatchPost(tagSpanBatchRequest)

Read Tag Spans Batch

Get stored TagSpans of a collection for multiple chunk IDs in a single request.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ReadTagSpansBatchApiTagSpansBatchPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## removeChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDelete

> CreateResponse removeChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDelete(collectionId, chunkId)

Remove Chunk From Collection

Removes a chunk from a user collection. Owner only. Removing a chunk that is not in the collection succeeds without a change; an unknown chunk is 404.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDeleteRequest } from '';

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
    chunkId: chunkId_example,
  } satisfies RemoveChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDeleteRequest;

  try {
    const data = await api.removeChunkFromCollectionApiUserCollectionsCollectionIdChunksChunkIdDelete(body);
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
| **chunkId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**CreateResponse**](CreateResponse.md)

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


## removeDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDelete

> WriteResult removeDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDelete(collectionId, documentId)

Remove Document From Collection

Removes a document and its chunks from a collection. Owner only. If some chunks cannot be unlinked the document stays in the collection (&#x60;&#x60;outcome&#x60;&#x60; &#x60;&#x60;partial&#x60;&#x60;/&#x60;&#x60;failed&#x60;&#x60;). Removing a document that is not in the collection changes nothing; an unknown document is 404.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDeleteRequest } from '';

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
    documentId: documentId_example,
  } satisfies RemoveDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDeleteRequest;

  try {
    const data = await api.removeDocumentFromCollectionApiUserCollectionsCollectionIdDocumentsDocumentIdDelete(body);
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

[**WriteResult**](WriteResult.md)

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

> SearchResponse searchApiSearchPost(searchRequest)

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

[**SearchResponse**](SearchResponse.md)

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


## shareCollectionApiUserCollectionsCollectionIdSharePost

> Collection shareCollectionApiUserCollectionsCollectionIdSharePost(collectionId, shareCollectionRequest)

Share Collection

Shares a collection with another user. Only the collection\&#39;s owner may share it.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ShareCollectionApiUserCollectionsCollectionIdSharePostRequest } from '';

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
  } satisfies ShareCollectionApiUserCollectionsCollectionIdSharePostRequest;

  try {
    const data = await api.shareCollectionApiUserCollectionsCollectionIdSharePost(body);
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

Optimized AI span suggestion: per tag, the Topicer service uses vector similarity to pre-filter only the most relevant chunks before invoking the LLM. Results are streamed as they arrive, then a :class:&#x60;SuggestSpansRunEnd&#x60;.

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
| **200** | Stream of SuggestSpansChunkResult, one JSON object per line, ended by one SuggestSpansRunEnd line (&#x60;&#x60;event &#x3D;&#x3D; \&#39;end\&#39;&#x60;&#x60;). |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## suggestSpansSelectionApiAiSuggestSpansSelectionPost

> suggestSpansSelectionApiAiSuggestSpansSelectionPost(suggestSpansSelectionRequest)

Suggest Spans Selection

Run AI span suggestion on a single user-selected passage that may span multiple chunks of the collection. The frontend sends the chunk IDs in document order; offsets are measured in UTF-16 code units against the concatenation of their text.  The endpoint streams NDJSON (&#x60;&#x60;application/x-ndjson&#x60;&#x60;) — one :class:&#x60;SuggestSpansChunkResult&#x60; per proposal, then a :class:&#x60;SuggestSpansRunEnd&#x60; — so the UI can render suggestions incrementally and abort the run mid-flight by closing the connection.  Each persisted span is anchored on the chunk that contains its *start* offset (mirroring how non-AI cross-chunk spans are stored), not on the first chunk of the selection.

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
| **200** | Stream of SuggestSpansChunkResult, one JSON object per line. One event per proposal (the persisted auto span, or &#x60;&#x60;unsaved&#x60;&#x60; with the reason); an event with empty &#x60;&#x60;spans&#x60;&#x60; and a populated &#x60;&#x60;error&#x60;&#x60; on Topicer failure; ended by one SuggestSpansRunEnd line (&#x60;&#x60;event &#x3D;&#x3D; \&#39;end\&#39;&#x60;&#x60;). |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## suggestSpansThoroughApiAiSuggestSpansThoroughPost

> suggestSpansThoroughApiAiSuggestSpansThoroughPost(suggestSpansRequest)

Suggest Spans Thorough

Thorough AI span suggestion: every collection chunk in the document is sent to the LLM together with all selected tags.  Persists each accepted proposal as a span with type &#x60;&#x60;auto&#x60;&#x60;. The endpoint streams NDJSON lines (&#x60;&#x60;application/x-ndjson&#x60;&#x60;): one :class:&#x60;SuggestSpansChunkResult&#x60; per chunk, then a :class:&#x60;SuggestSpansRunEnd&#x60;.

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
| **200** | Stream of SuggestSpansChunkResult, one JSON object per line, ended by one SuggestSpansRunEnd line (&#x60;&#x60;event &#x3D;&#x3D; \&#39;end\&#39;&#x60;&#x60;). |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## summarizeApiSummarizeSummaryTypePost

> SummaryResponse summarizeApiSummarizeSummaryTypePost(summaryType, searchResponse)

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
    // SearchResponse
    searchResponse: ...,
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
| **searchResponse** | [SearchResponse](SearchResponse.md) |  | |

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


## summarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPost

> DocumentSummaryResponse summarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPost(collectionId, documentId)

Summarize Document

Summarizes the current document of a collection (#249), with citations to the chunks the summary was built from. Collection-scoped (needs read access, as the matching &#x60;&#x60;GET /api/user_collections/{collection_id}/documents/{document_id}&#x60;&#x60; route does); the document must belong to the collection. A generation failure answers 502 (413 for an input above the feature\&#39;s limit), the same convention &#x60;&#x60;POST /api/question&#x60;&#x60; uses, rather than a 200 whose &#x60;&#x60;summary&#x60;&#x60; is quietly the configured fallback text.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { SummarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPostRequest } from '';

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
    documentId: documentId_example,
  } satisfies SummarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPostRequest;

  try {
    const data = await api.summarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPost(body);
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

[**DocumentSummaryResponse**](DocumentSummaryResponse.md)

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


## unshareCollectionApiUserCollectionsCollectionIdShareUserIdDelete

> Collection unshareCollectionApiUserCollectionsCollectionIdShareUserIdDelete(collectionId, userId)

Unshare Collection

Revokes a collection share. Only the collection\&#39;s owner may unshare it.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UnshareCollectionApiUserCollectionsCollectionIdShareUserIdDeleteRequest } from '';

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
  } satisfies UnshareCollectionApiUserCollectionsCollectionIdShareUserIdDeleteRequest;

  try {
    const data = await api.unshareCollectionApiUserCollectionsCollectionIdShareUserIdDelete(body);
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

Updates collection name/description/color. Owner only.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateCollectionApiUserCollectionsCollectionIdPatchRequest } from '';

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


## updateCollectionOwnerApiUserCollectionsCollectionIdOwnerPatch

> Collection updateCollectionOwnerApiUserCollectionsCollectionIdOwnerPatch(collectionId, patchCollectionOwner)

Update Collection Owner

Reassigns ownership of a collection to a different user. Admin only.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateCollectionOwnerApiUserCollectionsCollectionIdOwnerPatchRequest } from '';

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
  } satisfies UpdateCollectionOwnerApiUserCollectionsCollectionIdOwnerPatchRequest;

  try {
    const data = await api.updateCollectionOwnerApiUserCollectionsCollectionIdOwnerPatch(body);
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

Updates a tag. Fields that are omitted or null are kept; at least one field must have a value (422 otherwise).

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateTagApiTagsTagUuidPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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


## updateTagSpanApiTagSpansSpanIdPatch

> TagSpanWriteResult updateTagSpanApiTagSpansSpanIdPatch(spanId, patchSpan)

Update Tag Span

Update TagSpan\&#39;s information (start, end, tagId, ...), then re-derive the chunk tag references of its (chunk, tag) pair (and the new pair on a tag change), so saving again retries a failed chunk tag update. &#x60;&#x60;outcome&#x60;&#x60; is &#x60;&#x60;partial&#x60;&#x60; when the span was updated but the chunk tags could not be.

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { UpdateTagSpanApiTagSpansSpanIdPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new DefaultApi(config);

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

[**TagSpanWriteResult**](TagSpanWriteResult.md)

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

