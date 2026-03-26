# DefaultApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**addChunk2CollectionApiChunk2CollectionPost**](DefaultApi.md#addchunk2collectionapichunk2collectionpost) | **POST** /api/chunk_2_collection | Add Chunk 2 Collection |
| [**approveSelectedTagChunkApiTagApprovalPut**](DefaultApi.md#approveselectedtagchunkapitagapprovalput) | **PUT** /api/tag_approval | Approve Selected Tag Chunk |
| [**cancelTaskApiTaggingTaskTaskIdDelete**](DefaultApi.md#canceltaskapitaggingtasktaskiddelete) | **DELETE** /api/tagging_task/{taskId} | Cancel Task |
| [**checkStatusApiTagStatusTaskIdGet**](DefaultApi.md#checkstatusapitagstatustaskidget) | **GET** /api/tag_status/{taskId} | Check Status |
| [**createTagApiTagPost**](DefaultApi.md#createtagapitagpost) | **POST** /api/tag | Create Tag |
| [**createUserCollectionApiUserCollectionPost**](DefaultApi.md#createusercollectionapiusercollectionpost) | **POST** /api/user_collection | Create User Collection |
| [**explainSelectionApiRagExplainPost**](DefaultApi.md#explainselectionapiragexplainpost) | **POST** /api/rag/explain | Explain Selection |
| [**fetchCollectionsApiCollectionsGet**](DefaultApi.md#fetchcollectionsapicollectionsget) | **GET** /api/collections | Fetch Collections |
| [**filterChunksByTagsApiFilterTagsPost**](DefaultApi.md#filterchunksbytagsapifiltertagspost) | **POST** /api/filter_tags | Filter Chunks By Tags |
| [**getAvalaibleRagConfigurationsApiRagConfigurationsGet**](DefaultApi.md#getavalaibleragconfigurationsapiragconfigurationsget) | **GET** /api/rag/configurations | Get Avalaible Rag Configurations |
| [**getCollectionChunksApiChunksOfCollectionGet**](DefaultApi.md#getcollectionchunksapichunksofcollectionget) | **GET** /api/chunks_of_collection | Get Collection Chunks |
| [**getConfigsApiConfigsGet**](DefaultApi.md#getconfigsapiconfigsget) | **GET** /api/configs | Get Configs |
| [**getSelectedTagsChunksApiTaggedTextsPost**](DefaultApi.md#getselectedtagschunksapitaggedtextspost) | **POST** /api/tagged_texts | Get Selected Tags Chunks |
| [**getTagTasksApiAllTasksGet**](DefaultApi.md#gettagtasksapialltasksget) | **GET** /api/all_tasks | Get Tag Tasks |
| [**getTagsApiAllTagsGet**](DefaultApi.md#gettagsapialltagsget) | **GET** /api/all_tags | Get Tags |
| [**questionApiQuestionQuestionTextPost**](DefaultApi.md#questionapiquestionquestiontextpost) | **POST** /api/question/{question_text} | Question |
| [**ragApiRagPost**](DefaultApi.md#ragapiragpost) | **POST** /api/rag | Rag |
| [**removeAutomaticTagsApiAutomaticTagsDelete**](DefaultApi.md#removeautomatictagsapiautomatictagsdelete) | **DELETE** /api/automatic_tags | Remove Automatic Tags |
| [**removeTagsApiWholeTagsDelete**](DefaultApi.md#removetagsapiwholetagsdelete) | **DELETE** /api/whole_tags | Remove Tags |
| [**saveFeedbackApiRagFeedbackPost**](DefaultApi.md#savefeedbackapiragfeedbackpost) | **POST** /api/rag/feedback | Save Feedback |
| [**searchApiSearchPost**](DefaultApi.md#searchapisearchpost) | **POST** /api/search | Search |
| [**startTaggingApiTaggingTaskPost**](DefaultApi.md#starttaggingapitaggingtaskpost) | **POST** /api/tagging_task | Start Tagging |
| [**summarizeApiSummarizeSummaryTypePost**](DefaultApi.md#summarizeapisummarizesummarytypepost) | **POST** /api/summarize/{summary_type} | Summarize |



## addChunk2CollectionApiChunk2CollectionPost

> CreateResponse addChunk2CollectionApiChunk2CollectionPost(chunk2CollectionReq)

Add Chunk 2 Collection

Creates user collection in weaviate db, or not if the same user collection already exists

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { AddChunk2CollectionApiChunk2CollectionPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // Chunk2CollectionReq
    chunk2CollectionReq: ...,
  } satisfies AddChunk2CollectionApiChunk2CollectionPostRequest;

  try {
    const data = await api.addChunk2CollectionApiChunk2CollectionPost(body);
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
| **chunk2CollectionReq** | [Chunk2CollectionReq](Chunk2CollectionReq.md) |  | |

### Return type

[**CreateResponse**](CreateResponse.md)

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


## approveSelectedTagChunkApiTagApprovalPut

> ApproveTagResponse approveSelectedTagChunkApiTagApprovalPut(approveTagReq)

Approve Selected Tag Chunk

User approve or disapprove a tag, changes the reference of the tag

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ApproveSelectedTagChunkApiTagApprovalPutRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // ApproveTagReq
    approveTagReq: ...,
  } satisfies ApproveSelectedTagChunkApiTagApprovalPutRequest;

  try {
    const data = await api.approveSelectedTagChunkApiTagApprovalPut(body);
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
| **approveTagReq** | [ApproveTagReq](ApproveTagReq.md) |  | |

### Return type

[**ApproveTagResponse**](ApproveTagResponse.md)

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


## cancelTaskApiTaggingTaskTaskIdDelete

> CancelTaskResponse cancelTaskApiTaggingTaskTaskIdDelete(taskId)

Cancel Task

Cancel running task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CancelTaskApiTaggingTaskTaskIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    taskId: taskId_example,
  } satisfies CancelTaskApiTaggingTaskTaskIdDeleteRequest;

  try {
    const data = await api.cancelTaskApiTaggingTaskTaskIdDelete(body);
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
| **taskId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**CancelTaskResponse**](CancelTaskResponse.md)

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


## checkStatusApiTagStatusTaskIdGet

> any checkStatusApiTagStatusTaskIdGet(taskId)

Check Status

Polling to check task status

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CheckStatusApiTagStatusTaskIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    taskId: taskId_example,
  } satisfies CheckStatusApiTagStatusTaskIdGetRequest;

  try {
    const data = await api.checkStatusApiTagStatusTaskIdGet(body);
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
| **taskId** | `string` |  | [Defaults to `undefined`] |

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


## createTagApiTagPost

> CreateResponse createTagApiTagPost(tagReqTemplate)

Create Tag

Creates tag in weaviate db, or not if the same tag already exists

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateTagApiTagPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // TagReqTemplate
    tagReqTemplate: ...,
  } satisfies CreateTagApiTagPostRequest;

  try {
    const data = await api.createTagApiTagPost(body);
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
| **tagReqTemplate** | [TagReqTemplate](TagReqTemplate.md) |  | |

### Return type

[**CreateResponse**](CreateResponse.md)

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


## createUserCollectionApiUserCollectionPost

> CreateResponse createUserCollectionApiUserCollectionPost(userCollectionReqTemplate)

Create User Collection

Creates user collection in weaviate db, or not if the same user collection already exists

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CreateUserCollectionApiUserCollectionPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // UserCollectionReqTemplate
    userCollectionReqTemplate: ...,
  } satisfies CreateUserCollectionApiUserCollectionPostRequest;

  try {
    const data = await api.createUserCollectionApiUserCollectionPost(body);
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
| **userCollectionReqTemplate** | [UserCollectionReqTemplate](UserCollectionReqTemplate.md) |  | |

### Return type

[**CreateResponse**](CreateResponse.md)

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
  const api = new DefaultApi();

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


## fetchCollectionsApiCollectionsGet

> GetCollectionsResponse fetchCollectionsApiCollectionsGet(userId)

Fetch Collections

Retrieves all collections for given user

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FetchCollectionsApiCollectionsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    userId: userId_example,
  } satisfies FetchCollectionsApiCollectionsGetRequest;

  try {
    const data = await api.fetchCollectionsApiCollectionsGet(body);
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
| **userId** | `string` |  | [Defaults to `undefined`] |

### Return type

[**GetCollectionsResponse**](GetCollectionsResponse.md)

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


## filterChunksByTagsApiFilterTagsPost

> FilterChunksByTagsResponse filterChunksByTagsApiFilterTagsPost(filterChunksByTagsRequest)

Filter Chunks By Tags

Filter chunks by given tags and positive or/and automatic flags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FilterChunksByTagsApiFilterTagsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // FilterChunksByTagsRequest
    filterChunksByTagsRequest: ...,
  } satisfies FilterChunksByTagsApiFilterTagsPostRequest;

  try {
    const data = await api.filterChunksByTagsApiFilterTagsPost(body);
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
| **filterChunksByTagsRequest** | [FilterChunksByTagsRequest](FilterChunksByTagsRequest.md) |  | |

### Return type

[**FilterChunksByTagsResponse**](FilterChunksByTagsResponse.md)

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
  const api = new DefaultApi();

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

No authorization required

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## getCollectionChunksApiChunksOfCollectionGet

> GetCollectionChunksResponse getCollectionChunksApiChunksOfCollectionGet(collectionId)

Get Collection Chunks

Returns chunks which belong to collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionChunksApiChunksOfCollectionGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies GetCollectionChunksApiChunksOfCollectionGetRequest;

  try {
    const data = await api.getCollectionChunksApiChunksOfCollectionGet(body);
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

[**GetCollectionChunksResponse**](GetCollectionChunksResponse.md)

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


## getConfigsApiConfigsGet

> GetConfigsResponse getConfigsApiConfigsGet()

Get Configs

Load all config files

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetConfigsApiConfigsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getConfigsApiConfigsGet();
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

[**GetConfigsResponse**](GetConfigsResponse.md)

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


## getSelectedTagsChunksApiTaggedTextsPost

> GetTaggedChunksResponse getSelectedTagsChunksApiTaggedTextsPost(getTaggedChunksReq)

Get Selected Tags Chunks

Returns chunks which are tagged by certain type of tag (automatic, positive, negative)

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetSelectedTagsChunksApiTaggedTextsPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // GetTaggedChunksReq
    getTaggedChunksReq: ...,
  } satisfies GetSelectedTagsChunksApiTaggedTextsPostRequest;

  try {
    const data = await api.getSelectedTagsChunksApiTaggedTextsPost(body);
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
| **getTaggedChunksReq** | [GetTaggedChunksReq](GetTaggedChunksReq.md) |  | |

### Return type

[**GetTaggedChunksResponse**](GetTaggedChunksResponse.md)

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


## getTagTasksApiAllTasksGet

> any getTagTasksApiAllTasksGet()

Get Tag Tasks

Get task info to see history of tasks

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetTagTasksApiAllTasksGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getTagTasksApiAllTasksGet();
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


## getTagsApiAllTagsGet

> GetTagsResponse getTagsApiAllTagsGet()

Get Tags

Retrieve all tags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetTagsApiAllTagsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getTagsApiAllTagsGet();
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

[**GetTagsResponse**](GetTagsResponse.md)

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
  const api = new DefaultApi();

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
  const api = new DefaultApi();

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


## removeAutomaticTagsApiAutomaticTagsDelete

> RemoveTagsResponse removeAutomaticTagsApiAutomaticTagsDelete(removeTagReq)

Remove Automatic Tags

Removes automatic tags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveAutomaticTagsApiAutomaticTagsDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // RemoveTagReq
    removeTagReq: ...,
  } satisfies RemoveAutomaticTagsApiAutomaticTagsDeleteRequest;

  try {
    const data = await api.removeAutomaticTagsApiAutomaticTagsDelete(body);
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
| **removeTagReq** | [RemoveTagReq](RemoveTagReq.md) |  | |

### Return type

[**RemoveTagsResponse**](RemoveTagsResponse.md)

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


## removeTagsApiWholeTagsDelete

> RemoveTagsResponse removeTagsApiWholeTagsDelete(removeTagReq)

Remove Tags

Removes whole tags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveTagsApiWholeTagsDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // RemoveTagReq
    removeTagReq: ...,
  } satisfies RemoveTagsApiWholeTagsDeleteRequest;

  try {
    const data = await api.removeTagsApiWholeTagsDelete(body);
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
| **removeTagReq** | [RemoveTagReq](RemoveTagReq.md) |  | |

### Return type

[**RemoveTagsResponse**](RemoveTagsResponse.md)

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
  const api = new DefaultApi();

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
  const api = new DefaultApi();

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


## startTaggingApiTaggingTaskPost

> TagStartResponse startTaggingApiTaggingTaskPost(taggingTaskReqTemplate)

Start Tagging

Starts tagging task in form of asyncio.create_task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { StartTaggingApiTaggingTaskPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // TaggingTaskReqTemplate
    taggingTaskReqTemplate: ...,
  } satisfies StartTaggingApiTaggingTaskPostRequest;

  try {
    const data = await api.startTaggingApiTaggingTaskPost(body);
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
| **taggingTaskReqTemplate** | [TaggingTaskReqTemplate](TaggingTaskReqTemplate.md) |  | |

### Return type

[**TagStartResponse**](TagStartResponse.md)

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
  const api = new DefaultApi();

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

