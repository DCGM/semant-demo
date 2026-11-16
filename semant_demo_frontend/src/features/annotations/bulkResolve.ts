import type { BulkUpdateSpansResponse } from 'src/generated/api'

/**
 * Approving or rejecting a large selection of AI suggestions (#464): the ids are sent in
 * bounded batches, one request at a time, so neither the backend nor the browser handles
 * the whole selection at once, and progress is reported after every batch.
 */

/** Ids per request. The backend bounds its own concurrency per request. */
export const BULK_RESOLVE_BATCH_SIZE = 100

export interface BulkResolveProgress {
  total: number
  /** Ids whose batch has finished (saved or not). */
  processed: number
  saved: number
  notSaved: number
}

export interface BulkResolveSummary extends BulkResolveProgress {
  /** Saved spans whose chunk tag update failed: tag-filtered search may be stale. */
  staleSearch: number
  /** Ids not known to be saved (failed, uncertain or never sent); they can be retried. */
  unresolved: string[]
  /** How many of ``unresolved`` may have been written all the same (timeouts). */
  uncertain: number
  /** Stopped because the document or collection changed. */
  abandoned: boolean
  /** The request error that stopped the run, if any. */
  error: unknown
}

/** Sends one batch; resolves to null when its result no longer applies (scope changed). */
export type BulkBatch = (ids: string[]) => Promise<BulkUpdateSpansResponse | null>

export async function runBulkResolve (
  ids: string[],
  sendBatch: BulkBatch,
  onProgress: (progress: BulkResolveProgress) => void = () => undefined,
  batchSize = BULK_RESOLVE_BATCH_SIZE
): Promise<BulkResolveSummary> {
  const todo = [...new Set(ids)]
  const summary: BulkResolveSummary = {
    total: todo.length,
    processed: 0,
    saved: 0,
    notSaved: 0,
    staleSearch: 0,
    unresolved: [],
    uncertain: 0,
    abandoned: false,
    error: null
  }
  const report = () => onProgress({
    total: summary.total, processed: summary.processed, saved: summary.saved, notSaved: summary.notSaved
  })
  let next = 0
  while (next < todo.length) {
    const batch = todo.slice(next, next + batchSize)
    let result: BulkUpdateSpansResponse | null
    try {
      result = await sendBatch(batch)
    } catch (err) {
      summary.error = err
      break
    }
    if (!result) {
      summary.abandoned = true
      break
    }
    next += batch.length
    const saved = new Set(result.succeeded ?? [])
    const staleSearch = new Set<string>()
    const uncertain = new Set<string>()
    for (const f of result.failed ?? []) {
      if (!f.itemId) continue
      if (f.step === 'update_chunk_tags') staleSearch.add(f.itemId)
      else if (!saved.has(f.itemId) && f.uncertain) uncertain.add(f.itemId)
    }
    for (const id of batch) {
      if (!saved.has(id)) summary.unresolved.push(id)
    }
    summary.saved += saved.size
    summary.notSaved += batch.length - saved.size
    summary.staleSearch += [...staleSearch].filter((id) => saved.has(id)).length
    summary.uncertain += uncertain.size
    summary.processed += batch.length
    report()
  }
  // Ids never sent (stopped early) stay unresolved too.
  summary.unresolved.push(...todo.slice(next))
  return summary
}

/** The message for a run that did not save every selected suggestion, or null. */
export function describeBulkResolve (summary: BulkResolveSummary, verb: 'Confirmed' | 'Rejected'): string | null {
  const notSaved = summary.total - summary.saved
  if (!notSaved && !summary.staleSearch) return null
  const parts = [`${verb} ${summary.saved} of ${summary.total} suggestions`]
  if (notSaved) {
    parts.push(`${notSaved} not saved and still selected` +
      (summary.uncertain ? ` (${summary.uncertain} may have been saved; retrying is safe)` : ''))
  }
  if (summary.staleSearch) {
    parts.push(`${summary.staleSearch} saved, but tag search may not show them yet`)
  }
  if (summary.error) parts.push('the remaining requests were stopped after an error')
  return `${parts.join('; ')}.` + (notSaved ? ' Retry to process the remaining ones.' : '')
}
