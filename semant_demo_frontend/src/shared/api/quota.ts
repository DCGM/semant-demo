import { QuotaExhaustedResponseFromJSON, ResponseError, type QuotaExhaustedResponse } from 'src/generated/api'
import { ApiError, apiErrorMessage } from './errors'

/**
 * The daily AI allowance (#371, #398) as seen by any request: the backend refuses an AI
 * operation it cannot admit with a 429 `QuotaExhaustedResponse` (`code:
 * "llm_quota_exhausted"`), before anything is generated. The allowance itself is shown by
 * `features/quota`; features report their AI operations here so it can be updated.
 */

const QUOTA_CODE = 'llm_quota_exhausted'

/** The refusal of an AI operation for the daily allowance, or null for any other error. */
export async function quotaRefusalOf (err: unknown): Promise<QuotaExhaustedResponse | null> {
  let body: unknown = null
  if (err instanceof ApiError && err.status === 429) {
    body = err.body
  } else if (err instanceof ResponseError && err.response.status === 429) {
    try {
      // Cloned: other readers (apiErrorMessage) can still read the body.
      body = await err.response.clone().json()
    } catch {
      return null
    }
  }
  if ((body as { code?: unknown } | null)?.code !== QUOTA_CODE) return null
  return QuotaExhaustedResponseFromJSON(body)
}

/**
 * When the allowance resets, in the user's local time: "today at 23:00" or "tomorrow at
 * 02:00" (the reset is the next UTC midnight, less than a day away).
 */
export function formatQuotaReset (resetAt: Date, now: Date = new Date()): string {
  const time = resetAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const day = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const days = Math.round((day(resetAt) - day(now)) / 86_400_000)
  if (days === 0) return `today at ${time}`
  if (days === 1) return `tomorrow at ${time}`
  return resetAt.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

/**
 * The message for a refused AI operation. Nothing was generated and nothing is retried;
 * a guest is told that signing in gives a separate allowance (not an unlimited one).
 */
export function quotaRefusalMessage (refusal: QuotaExhaustedResponse, now: Date = new Date()): string {
  const guest = refusal.principal === 'guest' ? ' Logging in gives you a separate daily allowance.' : ''
  return 'Today\'s AI allowance has no room for this request, so nothing was generated. ' +
    `It resets ${formatQuotaReset(refusal.resetAt, now)}; search and browsing still work.${guest}`
}

/**
 * {@link apiErrorMessage} for an AI operation: a refusal for the daily allowance gets
 * {@link quotaRefusalMessage}, any other failure the backend's `detail` or `fallback`.
 */
export async function aiErrorMessage (err: unknown, fallback: string): Promise<string> {
  const refusal = await quotaRefusalOf(err)
  return refusal ? quotaRefusalMessage(refusal) : apiErrorMessage(err, fallback)
}

type Listener = () => void
const listeners = new Set<Listener>()

/**
 * An AI operation of this browser ended (answered, failed, refused or cancelled), so the
 * allowance shown may have changed. Called by the features that start AI operations.
 */
export function reportAiOperation (): void {
  listeners.forEach((listener) => listener())
}

/** Calls `listener` after every reported AI operation; returns the unsubscribe function. */
export function onAiOperation (listener: Listener): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
