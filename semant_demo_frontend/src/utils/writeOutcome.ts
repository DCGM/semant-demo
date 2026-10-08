import { WriteOutcome, type TagSpan, type TagSpanWriteResult, type WriteResult } from 'src/generated/api'

/**
 * Multi-write operations are best effort (ADR 0002): the backend keeps completed writes
 * and reports the rest. These helpers turn an incomplete result into a visible message.
 */
export function describeIncomplete (result: WriteResult, what: string): string {
  const failed = result.failed ?? []
  const uncertain = failed.filter((f) => f.uncertain).length
  const parts = [`${what} ${result.outcome === WriteOutcome.partial ? 'was only partly completed' : 'failed'}`]
  if (failed.length) {
    parts.push(`${failed.length} step(s) failed` + (uncertain ? ` (${uncertain} may still have been applied)` : ''))
  }
  if (result.unattempted?.length) parts.push(`${result.unattempted.length} not attempted`)
  return `${parts.join('; ')}. Completed changes were kept; you can retry.`
}

/** Thrown for a ``partial`` or ``failed`` result so existing error handling shows it. */
export class IncompleteWriteError extends Error {
  constructor (readonly result: WriteResult, what: string) {
    super(describeIncomplete(result, what))
    this.name = 'IncompleteWriteError'
  }
}

export function requireComplete<T extends WriteResult> (result: T, what: string): T {
  if (result.outcome !== WriteOutcome.complete) throw new IncompleteWriteError(result, what)
  return result
}

/**
 * A single span write saves the span first and then updates the chunk tag that
 * tag-filtered search uses. When only the second step failed the span change stands;
 * this returns the warning to show (or null when the write was complete).
 */
export function searchTagWarning (result: WriteResult, action: 'saved' | 'deleted'): string | null {
  if (result.outcome === WriteOutcome.complete) return null
  return action === 'saved'
    ? 'The annotation was saved, but tag search was not updated for it. Save the annotation again to retry.'
    : 'The annotation was deleted, but tag search may still find its passage.'
}

/** The span part of a span write result, without the outcome fields. */
export function spanOf (result: TagSpanWriteResult): TagSpan {
  const { id, chunkId, tagId, start, end, type, reason, confidence } = result
  return { id, chunkId, tagId, start, end, type, reason, confidence }
}

/**
 * Message of a write that stopped part way (tag creation, tag or collection deletion):
 * the backend answers 500 with `detail`, the failed `step` and the completed steps.
 * Returns `fallback` for any other error.
 */
export async function incompleteWriteMessage (err: unknown, fallback: string): Promise<string> {
  const response = (err as { response?: Response } | null)?.response
  if (!response || response.status !== 500) return fallback
  try {
    const body = await response.clone().json() as { detail?: unknown, step?: unknown }
    return typeof body.detail === 'string' && typeof body.step === 'string' ? body.detail : fallback
  } catch {
    return fallback
  }
}
