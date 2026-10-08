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
