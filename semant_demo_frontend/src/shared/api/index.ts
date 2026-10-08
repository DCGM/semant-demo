// Frontend transport: one backend URL, one token source, one error format.
export { BACKEND_URL, apiUrl } from './config'
export { getAuthToken, setAuthToken, clearAuthToken, authHeaders } from './auth'
export { useApi, createApiClients, type ApiClients } from './client'
export { ApiError, apiErrorMessage, errorStatus, isAbortError } from './errors'
export { postNdjson, readNdjson } from './ndjson'
export { createContextGuard, type ContextGuard } from './context'
export { createScope, type Scope } from './scope'
