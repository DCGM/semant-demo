# AuthApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
|------------- | ------------- | -------------|
| [**authJwtLoginApiAuthJwtLoginPost**](AuthApi.md#authjwtloginapiauthjwtloginpost) | **POST** /api/auth/jwt/login | Auth:Jwt.Login |
| [**authJwtLogoutApiAuthJwtLogoutPost**](AuthApi.md#authjwtlogoutapiauthjwtlogoutpost) | **POST** /api/auth/jwt/logout | Auth:Jwt.Logout |
| [**registerRegisterApiAuthRegisterPost**](AuthApi.md#registerregisterapiauthregisterpost) | **POST** /api/auth/register | Register:Register |



## authJwtLoginApiAuthJwtLoginPost

> BearerResponse authJwtLoginApiAuthJwtLoginPost(username, password, grantType, scope, clientId, clientSecret)

Auth:Jwt.Login

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { AuthJwtLoginApiAuthJwtLoginPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AuthApi();

  const body = {
    // string
    username: username_example,
    // string
    password: password_example,
    // string (optional)
    grantType: grantType_example,
    // string (optional)
    scope: scope_example,
    // string (optional)
    clientId: clientId_example,
    // string (optional)
    clientSecret: clientSecret_example,
  } satisfies AuthJwtLoginApiAuthJwtLoginPostRequest;

  try {
    const data = await api.authJwtLoginApiAuthJwtLoginPost(body);
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
| **username** | `string` |  | [Defaults to `undefined`] |
| **password** | `string` |  | [Defaults to `undefined`] |
| **grantType** | `string` |  | [Optional] [Defaults to `undefined`] |
| **scope** | `string` |  | [Optional] [Defaults to `&#39;&#39;`] |
| **clientId** | `string` |  | [Optional] [Defaults to `undefined`] |
| **clientSecret** | `string` |  | [Optional] [Defaults to `undefined`] |

### Return type

[**BearerResponse**](BearerResponse.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/x-www-form-urlencoded`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **200** | Successful Response |  -  |
| **400** | Bad Request |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)


## authJwtLogoutApiAuthJwtLogoutPost

> any authJwtLogoutApiAuthJwtLogoutPost()

Auth:Jwt.Logout

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { AuthJwtLogoutApiAuthJwtLogoutPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const config = new Configuration({ 
    // To configure OAuth2 access token for authorization: OAuth2PasswordBearer password
    accessToken: "YOUR ACCESS TOKEN",
  });
  const api = new AuthApi(config);

  try {
    const data = await api.authJwtLogoutApiAuthJwtLogoutPost();
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


## registerRegisterApiAuthRegisterPost

> UserRead registerRegisterApiAuthRegisterPost(userCreate)

Register:Register

### Example

```ts
import {
  Configuration,
  AuthApi,
} from '';
import type { RegisterRegisterApiAuthRegisterPostRequest } from '';

async function example() {
  console.log("🚀 Testing  SDK...");
  const api = new AuthApi();

  const body = {
    // UserCreate
    userCreate: ...,
  } satisfies RegisterRegisterApiAuthRegisterPostRequest;

  try {
    const data = await api.registerRegisterApiAuthRegisterPost(body);
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
| **userCreate** | [UserCreate](UserCreate.md) |  | |

### Return type

[**UserRead**](UserRead.md)

### Authorization

No authorization required

### HTTP request headers

- **Content-Type**: `application/json`
- **Accept**: `application/json`


### HTTP response details
| Status code | Description | Response headers |
|-------------|-------------|------------------|
| **201** | Successful Response |  -  |
| **400** | Bad Request |  -  |
| **422** | Validation Error |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)

