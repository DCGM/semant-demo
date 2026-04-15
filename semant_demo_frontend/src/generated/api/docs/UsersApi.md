# UsersApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**usersCurrentUserApiUsersMeGet**](UsersApi.md#userscurrentuserapiusersmeget) | **GET** /api/users/me | Users:Current User |
| [**usersDeleteUserApiUsersIdDelete**](UsersApi.md#usersdeleteuserapiusersiddelete) | **DELETE** /api/users/{id} | Users:Delete User |
| [**usersPatchCurrentUserApiUsersMePatch**](UsersApi.md#userspatchcurrentuserapiusersmepatch) | **PATCH** /api/users/me | Users:Patch Current User |
| [**usersPatchUserApiUsersIdPatch**](UsersApi.md#userspatchuserapiusersidpatch) | **PATCH** /api/users/{id} | Users:Patch User |
| [**usersUserApiUsersIdGet**](UsersApi.md#usersuserapiusersidget) | **GET** /api/users/{id} | Users:User |



## usersCurrentUserApiUsersMeGet

> UserRead usersCurrentUserApiUsersMeGet()

Users:Current User

### Example

```ts
import {
  Configuration,
  UsersApi,
} from '';
import type { UsersCurrentUserApiUsersMeGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new UsersApi(config);

  try {
    const data = await api.usersCurrentUserApiUsersMeGet();
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

[**UserRead**](UserRead.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **401** | Missing token or inactive user. |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## usersDeleteUserApiUsersIdDelete

> usersDeleteUserApiUsersIdDelete(id)

Users:Delete User

### Example

```ts
import {
  Configuration,
  UsersApi,
} from '';
import type { UsersDeleteUserApiUsersIdDeleteRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new UsersApi(config);

  const body = {
    // string
    id: id_example,
  } satisfies UsersDeleteUserApiUsersIdDeleteRequest;

  try {
    const data = await api.usersDeleteUserApiUsersIdDelete(body);
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
| **id** | `string` |  | [Defaults to `undefined`] |

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
| **401** | Missing token or inactive user. |  -  |
| **403** | Not a superuser. |  -  |
| **404** | The user does not exist. |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## usersPatchCurrentUserApiUsersMePatch

> UserRead usersPatchCurrentUserApiUsersMePatch(userUpdate)

Users:Patch Current User

### Example

```ts
import {
  Configuration,
  UsersApi,
} from '';
import type { UsersPatchCurrentUserApiUsersMePatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new UsersApi(config);

  const body = {
    // UserUpdate
    userUpdate: ...,
  } satisfies UsersPatchCurrentUserApiUsersMePatchRequest;

  try {
    const data = await api.usersPatchCurrentUserApiUsersMePatch(body);
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
| **userUpdate** | [UserUpdate](UserUpdate.md) |  | |

### Return type

[**UserRead**](UserRead.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **401** | Missing token or inactive user. |  -  |
| **400** | Bad Request |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## usersPatchUserApiUsersIdPatch

> UserRead usersPatchUserApiUsersIdPatch(id, userUpdate)

Users:Patch User

### Example

```ts
import {
  Configuration,
  UsersApi,
} from '';
import type { UsersPatchUserApiUsersIdPatchRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new UsersApi(config);

  const body = {
    // string
    id: id_example,
    // UserUpdate
    userUpdate: ...,
  } satisfies UsersPatchUserApiUsersIdPatchRequest;

  try {
    const data = await api.usersPatchUserApiUsersIdPatch(body);
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
| **id** | `string` |  | [Defaults to `undefined`] |
| **userUpdate** | [UserUpdate](UserUpdate.md) |  | |

### Return type

[**UserRead**](UserRead.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **401** | Missing token or inactive user. |  -  |
| **403** | Not a superuser. |  -  |
| **404** | The user does not exist. |  -  |
| **400** | Bad Request |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## usersUserApiUsersIdGet

> UserRead usersUserApiUsersIdGet(id)

Users:User

### Example

```ts
import {
  Configuration,
  UsersApi,
} from '';
import type { UsersUserApiUsersIdGetRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new UsersApi(config);

  const body = {
    // string
    id: id_example,
  } satisfies UsersUserApiUsersIdGetRequest;

  try {
    const data = await api.usersUserApiUsersIdGet(body);
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
| **id** | `string` |  | [Defaults to `undefined`] |

### Return type

[**UserRead**](UserRead.md)

### Authorization

[OAuth2PasswordBearer password](../README.md#OAuth2PasswordBearer-password)

### HTTP request headers

- **Content-Type**: Not defined
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **401** | Missing token or inactive user. |  -  |
| **403** | Not a superuser. |  -  |
| **404** | The user does not exist. |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

