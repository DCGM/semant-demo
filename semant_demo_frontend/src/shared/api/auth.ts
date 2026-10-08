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
