import type { QuotaExhaustedResponse, SearchRequest } from 'src/generated/api'
import { formatQuotaReset } from 'src/shared/api'

/** Whether a search asks for generated titles or summaries, which use the daily AI allowance. */
export function generatesText (request: SearchRequest): boolean {
  return !!(request.searchTitleGenerate || request.searchSummaryGenerate || request.searchResultsSummaryGenerate)
}

/**
 * Search keeps its results when the daily AI allowance has no room for the optional
 * generated titles and summaries (`SearchResponse.quotaExhausted`); this says why they are missing.
 */
export function searchQuotaMessage (refusal: QuotaExhaustedResponse, now: Date = new Date()): string {
  return 'AI titles and summaries were skipped: today\'s AI allowance has no room for them. ' +
    `The search results are complete; the allowance resets ${formatQuotaReset(refusal.resetAt, now)}.`
}
