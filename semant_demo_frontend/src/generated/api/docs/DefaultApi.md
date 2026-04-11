# DefaultApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**addChunk2CollectionApiUserCollectionChunksPost**](DefaultApi.md#addchunk2collectionapiusercollectionchunkspost) | **POST** /api/user_collection/chunks | Add Chunk 2 Collection |
| [**approveSelectedTagChunkApiTagApprovePut**](DefaultApi.md#approveselectedtagchunkapitagapproveput) | **PUT** /api/tag/approve | Approve Selected Tag Chunk |
| [**approveSelectedTagChunkApiTagDisapprovePut**](DefaultApi.md#approveselectedtagchunkapitagdisapproveput) | **PUT** /api/tag/disapprove | Approve Selected Tag Chunk |
| [**cancelTaskApiTagTaskTaskIdDelete**](DefaultApi.md#canceltaskapitagtasktaskiddelete) | **DELETE** /api/tag/task/{taskId} | Cancel Task |
| [**checkStatusApiTagTaskStatusTaskIdGet**](DefaultApi.md#checkstatusapitagtaskstatustaskidget) | **GET** /api/tag/task/status/{taskId} | Check Status |
| [**createTagApiTagPost**](DefaultApi.md#createtagapitagpost) | **POST** /api/tag | Create Tag |
| [**createUserCollectionApiUserCollectionPost**](DefaultApi.md#createusercollectionapiusercollectionpost) | **POST** /api/user_collection | Create User Collection |
| [**explainSelectionApiRagExplainPost**](DefaultApi.md#explainselectionapiragexplainpost) | **POST** /api/rag/explain | Explain Selection |
| [**fetchCollectionsApiUserCollectionsGet**](DefaultApi.md#fetchcollectionsapiusercollectionsget) | **GET** /api/user_collections | Fetch Collections |
| [**filterChunksByTagsApiTagsFilterPost**](DefaultApi.md#filterchunksbytagsapitagsfilterpost) | **POST** /api/tags/filter | Filter Chunks By Tags |
| [**getAvalaibleRagConfigurationsApiRagConfigurationsGet**](DefaultApi.md#getavalaibleragconfigurationsapiragconfigurationsget) | **GET** /api/rag/configurations | Get Avalaible Rag Configurations |
| [**getCollectionChunksApiUserCollectionChunksGet**](DefaultApi.md#getcollectionchunksapiusercollectionchunksget) | **GET** /api/user_collection/chunks | Get Collection Chunks |
| [**getConfigsApiTagConfigsGet**](DefaultApi.md#getconfigsapitagconfigsget) | **GET** /api/tag/configs | Get Configs |
| [**getSelectedTagsChunksApiTagTextChunksPost**](DefaultApi.md#getselectedtagschunksapitagtextchunkspost) | **POST** /api/tag/textChunks | Get Selected Tags Chunks |
| [**getTagTasksApiTagTasksInfoGet**](DefaultApi.md#gettagtasksapitagtasksinfoget) | **GET** /api/tag/tasks/info | Get Tag Tasks |
| [**getTagsApiTagsGet**](DefaultApi.md#gettagsapitagsget) | **GET** /api/tags | Get Tags |
| [**questionApiQuestionQuestionTextPost**](DefaultApi.md#questionapiquestionquestiontextpost) | **POST** /api/question/{question_text} | Question |
| [**ragApiRagPost**](DefaultApi.md#ragapiragpost) | **POST** /api/rag | Rag |
| [**removeAutomaticTagsApiTagsAutomaticDelete**](DefaultApi.md#removeautomatictagsapitagsautomaticdelete) | **DELETE** /api/tags/automatic | Remove Automatic Tags |
| [**removeTagsApiTagsDelete**](DefaultApi.md#removetagsapitagsdelete) | **DELETE** /api/tags | Remove Tags |
| [**saveFeedbackApiRagFeedbackPost**](DefaultApi.md#savefeedbackapiragfeedbackpost) | **POST** /api/rag/feedback | Save Feedback |
| [**searchApiSearchPost**](DefaultApi.md#searchapisearchpost) | **POST** /api/search | Search |
| [**startTaggingApiTagTaskPost**](DefaultApi.md#starttaggingapitagtaskpost) | **POST** /api/tag/task | Start Tagging |
| [**summarizeApiSummarizeSummaryTypePost**](DefaultApi.md#summarizeapisummarizesummarytypepost) | **POST** /api/summarize/{summary_type} | Summarize |



## addChunk2CollectionApiUserCollectionChunksPost

> CreateResponse addChunk2CollectionApiUserCollectionChunksPost(chunk2CollectionReq)

Add Chunk 2 Collection

Connects chunk with user collection

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { AddChunk2CollectionApiUserCollectionChunksPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // Chunk2CollectionReq
    chunk2CollectionReq: ...,
  } satisfies AddChunk2CollectionApiUserCollectionChunksPostRequest;

  try {
    const data = await api.addChunk2CollectionApiUserCollectionChunksPost(body);
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


## approveSelectedTagChunkApiTagApprovePut

> ApproveTagResponse approveSelectedTagChunkApiTagApprovePut(approveTagReq)

Approve Selected Tag Chunk

User approve a tag, changes the reference of the tag

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ApproveSelectedTagChunkApiTagApprovePutRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // ApproveTagReq
    approveTagReq: ...,
  } satisfies ApproveSelectedTagChunkApiTagApprovePutRequest;

  try {
    const data = await api.approveSelectedTagChunkApiTagApprovePut(body);
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


## approveSelectedTagChunkApiTagDisapprovePut

> ApproveTagResponse approveSelectedTagChunkApiTagDisapprovePut(approveTagReq)

Approve Selected Tag Chunk

User disapprove a tag, changes the reference of the tag

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { ApproveSelectedTagChunkApiTagDisapprovePutRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // ApproveTagReq
    approveTagReq: ...,
  } satisfies ApproveSelectedTagChunkApiTagDisapprovePutRequest;

  try {
    const data = await api.approveSelectedTagChunkApiTagDisapprovePut(body);
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


## cancelTaskApiTagTaskTaskIdDelete

> CancelTaskResponse cancelTaskApiTagTaskTaskIdDelete(taskId)

Cancel Task

Cancel running task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CancelTaskApiTagTaskTaskIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    taskId: taskId_example,
  } satisfies CancelTaskApiTagTaskTaskIdDeleteRequest;

  try {
    const data = await api.cancelTaskApiTagTaskTaskIdDelete(body);
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


## checkStatusApiTagTaskStatusTaskIdGet

> any checkStatusApiTagTaskStatusTaskIdGet(taskId)

Check Status

Polling to check task status

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { CheckStatusApiTagTaskStatusTaskIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    taskId: taskId_example,
  } satisfies CheckStatusApiTagTaskStatusTaskIdGetRequest;

  try {
    const data = await api.checkStatusApiTagTaskStatusTaskIdGet(body);
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

Creates a tag in weaviate db, or not if the same tag already exists

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


## fetchCollectionsApiUserCollectionsGet

> Array&lt;Collection&gt; fetchCollectionsApiUserCollectionsGet(userId)

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
  const api = new DefaultApi();

  const body = {
    // string
    userId: userId_example,
  } satisfies FetchCollectionsApiUserCollectionsGetRequest;

  try {
    const data = await api.fetchCollectionsApiUserCollectionsGet(body);
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

[**Array&lt;Collection&gt;**](Collection.md)

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


## filterChunksByTagsApiTagsFilterPost

> FilterChunksByTagsResponse filterChunksByTagsApiTagsFilterPost(filterChunksByTagsRequest)

Filter Chunks By Tags

Filter chunks by given tags and positive or/and automatic flags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { FilterChunksByTagsApiTagsFilterPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // FilterChunksByTagsRequest
    filterChunksByTagsRequest: ...,
  } satisfies FilterChunksByTagsApiTagsFilterPostRequest;

  try {
    const data = await api.filterChunksByTagsApiTagsFilterPost(body);
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


## getCollectionChunksApiUserCollectionChunksGet

> GetCollectionChunksResponse getCollectionChunksApiUserCollectionChunksGet(collectionId)

Get Collection Chunks

Returns chunks which belong to collection given by id

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetCollectionChunksApiUserCollectionChunksGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // string
    collectionId: collectionId_example,
  } satisfies GetCollectionChunksApiUserCollectionChunksGetRequest;

  try {
    const data = await api.getCollectionChunksApiUserCollectionChunksGet(body);
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


## getConfigsApiTagConfigsGet

> GetConfigsResponse getConfigsApiTagConfigsGet()

Get Configs

Load all config files

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetConfigsApiTagConfigsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getConfigsApiTagConfigsGet();
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


## getSelectedTagsChunksApiTagTextChunksPost

> GetTaggedChunksResponse getSelectedTagsChunksApiTagTextChunksPost(getTaggedChunksReq)

Get Selected Tags Chunks

Returns chunks which are tagged by certain type of tag (automatic, positive, negative)

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetSelectedTagsChunksApiTagTextChunksPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // GetTaggedChunksReq
    getTaggedChunksReq: ...,
  } satisfies GetSelectedTagsChunksApiTagTextChunksPostRequest;

  try {
    const data = await api.getSelectedTagsChunksApiTagTextChunksPost(body);
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


## getTagTasksApiTagTasksInfoGet

> any getTagTasksApiTagTasksInfoGet()

Get Tag Tasks

Get task info to see history of tasks

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetTagTasksApiTagTasksInfoGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getTagTasksApiTagTasksInfoGet();
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


## getTagsApiTagsGet

> GetTagsResponse getTagsApiTagsGet()

Get Tags

Retrieve all tags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { GetTagsApiTagsGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  try {
    const data = await api.getTagsApiTagsGet();
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


## removeAutomaticTagsApiTagsAutomaticDelete

> RemoveTagsResponse removeAutomaticTagsApiTagsAutomaticDelete(removeTagReq)

Remove Automatic Tags

Removes automatic tags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveAutomaticTagsApiTagsAutomaticDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // RemoveTagReq
    removeTagReq: ...,
  } satisfies RemoveAutomaticTagsApiTagsAutomaticDeleteRequest;

  try {
    const data = await api.removeAutomaticTagsApiTagsAutomaticDelete(body);
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


## removeTagsApiTagsDelete

> RemoveTagsResponse removeTagsApiTagsDelete(removeTagReq)

Remove Tags

Removes whole tags

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { RemoveTagsApiTagsDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // RemoveTagReq
    removeTagReq: ...,
  } satisfies RemoveTagsApiTagsDeleteRequest;

  try {
    const data = await api.removeTagsApiTagsDelete(body);
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


## startTaggingApiTagTaskPost

> TagStartResponse startTaggingApiTagTaskPost(taggingTaskReqTemplate)

Start Tagging

Starts tagging task in form of asyncio.create_task

### Example

```ts
import {
  Configuration,
  DefaultApi,
} from '';
import type { StartTaggingApiTagTaskPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new DefaultApi();

  const body = {
    // TaggingTaskReqTemplate
    taggingTaskReqTemplate: ...,
  } satisfies StartTaggingApiTagTaskPostRequest;

  try {
    const data = await api.startTaggingApiTagTaskPost(body);
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

