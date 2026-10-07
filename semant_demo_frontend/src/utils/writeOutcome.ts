import { WriteOutcome, type WriteResult } from 'src/generated/api'

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
