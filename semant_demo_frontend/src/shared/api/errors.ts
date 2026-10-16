import { FetchError, ResponseError } from 'src/generated/api'

/**
 * A non-2xx answer to a hand-written request (NDJSON streams). The generated client
 * throws its own `ResponseError`; {@link apiErrorMessage} reads both.
 */
export class ApiError extends Error {
  constructor (readonly status: number, readonly detail: string | null, readonly body: unknown = null) {
    super(detail ? `${detail} (HTTP ${status})` : `Request failed (HTTP ${status})`)
    this.name = 'ApiError'
  }
}

/** Builds an {@link ApiError} from a failed response, reading FastAPI's `detail`. */
export async function apiErrorFromResponse (response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    const text = await response.text()
    try {
      body = JSON.parse(text)
    } catch {
      body = text || null
    }
  } catch {
    // body unreadable: keep the status only
  }
  return new ApiError(response.status, detailOf(body), body)
}

function detailOf (body: unknown): string | null {
  if (typeof body === 'string') return body || null
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  // FastAPI validation errors: [{ loc, msg, ... }]
  if (Array.isArray(detail)) {
    const messages = detail.map((d) => (d as { msg?: unknown })?.msg).filter((m) => typeof m === 'string')
    if (messages.length) return messages.join('; ')
  }
  return null
}

/** True for a request the caller cancelled (AbortController), not a failure to report. */
export function isAbortError (err: unknown): boolean {
  const name = (err as { name?: unknown } | null)?.name
  if (name === 'AbortError') return true
  // The generated client wraps fetch failures, including aborts, in FetchError.
  return err instanceof FetchError && (err.cause as { name?: unknown } | undefined)?.name === 'AbortError'
}

/** HTTP status of a failed request from either client, or null (network error, other). */
export function errorStatus (err: unknown): number | null {
  if (err instanceof ApiError) return err.status
  if (err instanceof ResponseError) return err.response.status
  return null
}

/**
 * A message for the user: the backend's `detail` when it sent one, otherwise `fallback`.
 * Reads the generated client's `ResponseError` body without consuming it for other readers.
 */
export async function apiErrorMessage (err: unknown, fallback: string): Promise<string> {
  if (err instanceof ApiError) return err.detail ?? fallback
  if (err instanceof ResponseError) {
    try {
      return detailOf(await err.response.clone().json()) ?? fallback
    } catch {
      return fallback
    }
  }
  return fallback
}
