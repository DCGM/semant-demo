import { computed, ref, watch, type Ref } from 'vue'
import type { SummaryLength } from 'src/generated/api'
import { createContextGuard, isAbortError, quotaRefusalMessage, quotaRefusalOf, reportAiOperation, useApi } from 'src/shared/api'
import { tokenizeCitations } from 'src/shared/citationTokens'
import { SUMMARY_LENGTH_DEFAULT } from 'src/shared/summaryLength'
import { selectResults, type ResultScope, type SearchResultsContext } from './searchResults'

export type SummaryToken =
  | { type: 'text'; value: string }
  | { type: 'citation'; docNumber: number }

export type SummaryScopeOption = 'focused' | 'broader' | 'extensive' | 'selected'

export const SUMMARY_SCOPE_OPTIONS: { label: string, value: SummaryScopeOption }[] = [
  { label: 'Focused', value: 'focused' },
  { label: 'Broader', value: 'broader' },
  { label: 'Extensive', value: 'extensive' },
  { label: 'Selected', value: 'selected' }
]

const scopeDefault: SummaryScopeOption = 'broader'

const topCounts: Record<Exclude<SummaryScopeOption, 'selected'>, number | null> = {
  focused: 3,
  broader: 10,
  extensive: null // all of it
}

export function resultScope (option: SummaryScopeOption, selectedIds: readonly string[]): ResultScope {
  return option === 'selected' ? { kind: 'selected', ids: selectedIds } : { kind: 'top', count: topCounts[option] }
}

/**
 * Splits the summary into text and citations. Citations ([docN]) are numbered
 * within the summarized subset, so they are translated to result numbers.
 */
export function parseSummaryTokens (text: string, indicesMap: number[]): SummaryToken[] {
  return tokenizeCitations(text, number => ({ docNumber: indicesMap[number - 1] ?? number }))
}

/**
 * Summary of search results. Works only on the given context's retrieved results (or the
 * selected ones), never on a re-run query. A new search context, a change of the summarized
 * subset (scope or selection) or of the length level, or a new summary request makes an
 * unfinished request stale:
 * its answer is dropped and it no longer controls `summarizing`; a shown summary of another
 * subset is cleared.
 *
 * @param context the current search results (null while there are none)
 * @param selectedIds ids of the results the user selected
 */
export function useSearchSummary (
  context: Ref<SearchResultsContext | null>,
  selectedIds: Ref<string[]>
) {
  const api = useApi().default
  const length = ref<SummaryLength>(SUMMARY_LENGTH_DEFAULT)
  const scope = ref<SummaryScopeOption>(scopeDefault)
  const summarizing = ref(false)
  const summary = ref('')
  const error = ref<string | null>(null)
  const timeSpent = ref(0)
  const summarizedResultNumbers = ref<number[]>([])
  const guard = createContextGuard()
  let abort: AbortController | null = null

  const tokens = computed(() => parseSummaryTokens(summary.value, summarizedResultNumbers.value))

  watch(selectedIds, () => {
    scope.value = selectedIds.value.length === 0 ? scopeDefault : 'selected'
  })

  function reset () {
    abort?.abort()
    abort = null
    guard.enter()
    summarizing.value = false
    summary.value = ''
    error.value = null
    timeSpent.value = 0
    summarizedResultNumbers.value = []
  }

  // What a summary is: the results it is about (the search and, for the "selected" scope,
  // the selection) and its length level. When they change (another search, another scope,
  // another selection, another length), a running request and the shown summary no longer
  // match what the panel says and are dropped.
  const summaryKey = computed(() => {
    const id = context.value?.id ?? null
    if (scope.value !== 'selected') return `${id}:${length.value}:${scope.value}`
    return `${id}:${length.value}:selected:${[...selectedIds.value].sort().join(',')}`
  })
  // Synchronous, so the invalidation happens before anything done after the change.
  watch(summaryKey, reset, { flush: 'sync' })

  async function summarize () {
    const current = context.value
    if (!current) return
    const subset = selectResults(current, resultScope(scope.value, selectedIds.value))
    if (!subset) {
      // An empty selection is reported, never widened to other results.
      reset()
      error.value = scope.value === 'selected'
        ? 'Please select at least one result for summarization.'
        : 'There are no results to summarize.'
      return
    }

    reset()
    const isCurrent = guard.capture()
    const controller = new AbortController()
    abort = controller
    summarizing.value = true
    try {
      const data = await api.summarizeApiSummarizeSummaryTypePost({
        summaryType: 'results',
        searchResponse: { ...current.response, results: subset.results },
        length: length.value
      }, { signal: controller.signal })
      if (!isCurrent()) return
      summarizedResultNumbers.value = subset.numbers
      summary.value = data.summary
      timeSpent.value = data.timeSpent
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Summarization failed', e)
      // Refused for the daily AI allowance: nothing was generated and nothing is retried.
      const refusal = await quotaRefusalOf(e)
      if (!isCurrent()) return
      error.value = refusal ? quotaRefusalMessage(refusal) : 'Failed to summarize.'
    } finally {
      reportAiOperation()
      if (isCurrent()) {
        summarizing.value = false
        abort = null
      }
    }
  }

  return {
    length,
    scope,
    summarizing,
    summary,
    error,
    timeSpent,
    tokens,
    summarize,
    reset
  }
}
