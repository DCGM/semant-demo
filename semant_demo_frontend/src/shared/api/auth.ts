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

/**
 * The user id a token was issued for (the JWT `sub` claim), or null when it cannot be read.
 * Not verified (the backend does that); only tells a renewed token of the same user from
 * another account's token.
 */
export function tokenSubject (token: string): string | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(payload.length / 4) * 4, '='))
    const sub = (JSON.parse(json) as { sub?: unknown }).sub
    return typeof sub === 'string' ? sub : null
  } catch {
    return null
  }
}

/**
 * Calls `listener` with the stored token (or null) whenever another browser tab signs in,
 * signs out or switches accounts. The browser reports only changes made by other tabs, so
 * this tab's own writes never come back here. Returns a function that unsubscribes.
 */
export function onStoredTokenChange (listener: (token: string | null) => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const handler = (event: StorageEvent) => {
    // key null: the other tab cleared the whole storage
    if (event.key !== null && event.key !== TOKEN_KEY) return
    if (event.storageArea !== null && event.storageArea !== storage()) return
    listener(getAuthToken())
  }
  window.addEventListener('storage', handler)
  return () => { window.removeEventListener('storage', handler) }
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
