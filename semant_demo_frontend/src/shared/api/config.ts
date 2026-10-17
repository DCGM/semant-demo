/**
 * The backend origin, e.g. `http://localhost:8000` (quasar.config.js sets BACKEND_URL for
 * every build). The generated client adds the `/api/...` path of each operation itself;
 * hand-written requests use {@link apiUrl}.
 */
export const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '')

/** Absolute URL of a backend API path, e.g. `apiUrl('/ai/discuss_span')`. */
export function apiUrl (path: string): string {
  return `${BACKEND_URL}/api${path.startsWith('/') ? path : `/${path}`}`
}

/**
 * Every request sends and keeps the backend's cookies, also when the frontend is served
 * from another origin (local development: :9000 → :8000). The backend's `semant_guest`
 * cookie identifies a signed-out visitor's daily AI allowance (#371); without it each
 * request would be a new guest. The backend allows credentials for `ALLOWED_ORIGIN` only.
 */
export const API_CREDENTIALS: RequestCredentials = 'include'
