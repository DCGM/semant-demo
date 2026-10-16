import { AuthApi, Configuration, DefaultApi, UsersApi, type Middleware } from 'src/generated/api'
import { authHeaders, reportUnauthorized } from './auth'
import { BACKEND_URL } from './config'

export interface ApiClients {
  default: DefaultApi
  auth: AuthApi
  users: UsersApi
}

/**
 * Adds the current bearer token to every request, including operations whose schema
 * declares no security (public reads that still honour a signed-in user). Read per
 * request, like the NDJSON transport does (`authHeaders`). A 401 answer to a request
 * sent with a token reports that token as no longer valid (`onUnauthorized`).
 */
const authentication: Middleware = {
  pre: async ({ url, init }) => ({
    url,
    // A request that names its token itself (`fetchCurrentUser`) keeps it.
    init: { ...init, headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) } }
  }),
  post: async ({ init, response }) => {
    if (response.status === 401) reportUnauthorized(init.headers as Record<string, string> | undefined)
    return response
  }
}

/**
 * The one configuration of the generated client: backend origin and authentication.
 * Hand-written requests (NDJSON streams) use the same sources (`config.ts`, `auth.ts`).
 */
export function createApiClients (basePath: string = BACKEND_URL): ApiClients {
  const configuration = new Configuration({ basePath, middleware: [authentication] })
  return {
    default: new DefaultApi(configuration),
    auth: new AuthApi(configuration),
    users: new UsersApi(configuration)
  }
}

let clients: ApiClients | null = null

/** The application's API clients. Usable in components, stores and plain modules. */
export function useApi (): ApiClients {
  clients ??= createApiClients()
  return clients
}
