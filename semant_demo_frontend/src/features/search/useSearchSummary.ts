import { computed, ref, watch, type Ref } from 'vue'
import { createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { selectResults, type ResultScope, type SearchResultsContext } from './searchResults'

export type SummaryToken =
  | { type: 'text'; value: string }
  | { type: 'citation'; docNumber: number }

export type SummaryScopeOption = 'focused' | 'broader' | 'extensive' | 'selected'

export const SUMMARY_BREVITY_OPTIONS = [
  { label: 'Short', value: 'short' },
  { label: 'Detailed', value: 'detailed' }
]

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
  const tokens: SummaryToken[] = []
  const citationRegex = /\[(doc([1-9][0-9]*))]/g
  let lastIndex = 0

  for (const match of text.matchAll(citationRegex)) {
    const matchText = match[0]
    const number = parseInt(match[2], 10)
    const index = match.index ?? 0

    if (index > lastIndex) {
      tokens.push({ type: 'text', value: text.slice(lastIndex, index) })
    }
    const translatedNumber = indicesMap[number - 1] ?? number
    tokens.push({ type: 'citation', docNumber: translatedNumber })

    lastIndex = index + matchText.length
  }

  if (lastIndex < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return tokens
}

/**
 * Summary of search results. Works only on the given context's retrieved results (or the
 * selected ones), never on a re-run query. A new search context, a change of the summarized
 * subset (scope or selection) or a new summary request makes an unfinished request stale:
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
  const brevity = ref('short')
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

  // The results a summary is about: the search and, for the "selected" scope, the
  // selection. When they change (another search, another scope, another selection), a
  // running request and the shown summary no longer match what the panel says and are
  // dropped.
  const subsetKey = computed(() => {
    const id = context.value?.id ?? null
    if (scope.value !== 'selected') return `${id}:${scope.value}`
    return `${id}:selected:${[...selectedIds.value].sort().join(',')}`
  })
  // Synchronous, so the invalidation happens before anything done after the change.
  watch(subsetKey, reset, { flush: 'sync' })

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
        searchResponse: { ...current.response, results: subset.results }
      }, { signal: controller.signal })
      if (!isCurrent()) return
      summarizedResultNumbers.value = subset.numbers
      summary.value = data.summary
      timeSpent.value = data.timeSpent
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Summarization failed', e)
      error.value = 'Failed to summarize.'
    } finally {
      if (isCurrent()) {
        summarizing.value = false
        abort = null
      }
    }
  }

  return {
    brevity,
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
