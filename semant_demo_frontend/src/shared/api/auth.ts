/**
 * The signed-in user's bearer token. Every request (generated client and NDJSON streams)
 * reads it here at send time, so logging in or out takes effect for the next request.
 */
const TOKEN_KEY = 'auth_token'

function storage (): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null // storage blocked (privacy settings)
  }
}

export function getAuthToken (): string | null {
  return storage()?.getItem(TOKEN_KEY) ?? null
}

export function setAuthToken (token: string): void {
  storage()?.setItem(TOKEN_KEY, token)
}

export function clearAuthToken (): void {
  storage()?.removeItem(TOKEN_KEY)
}

/** `Authorization` header for hand-written requests; empty when signed out. */
export function authHeaders (): Record<string, string> {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

type UnauthorizedListener = (token: string) => void
const unauthorizedListeners = new Set<UnauthorizedListener>()

/**
 * Calls `listener` with the token a request was sent with when the backend rejected it
 * as unauthenticated (401: expired or revoked). Returns a function that unsubscribes.
 */
export function onUnauthorized (listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener)
  return () => { unauthorizedListeners.delete(listener) }
}

/** Reports a 401 answer to a request sent with `headers`; requests without a token are ignored. */
export function reportUnauthorized (headers: Record<string, string> | undefined): void {
  const token = headers?.Authorization?.match(/^Bearer (.+)$/)?.[1]
  if (token) unauthorizedListeners.forEach((listener) => listener(token))
}
