import { computed, ref, watch } from 'vue'
import type { Ref } from 'vue'
import { Notify } from 'quasar'
import { api } from 'src/boot/axios'
import type { SearchResponse, SummaryResponse, TextChunkWithDocument } from 'src/models'

export type SummaryToken =
  | { type: 'text'; value: string }
  | { type: 'citation'; docNumber: number }

export const SUMMARY_BREVITY_OPTIONS = [
  { label: 'Short', value: 'short' },
  { label: 'Detailed', value: 'detailed' }
]

export const SUMMARY_SCOPE_OPTIONS = [
  { label: 'Focused', value: 'focused' },
  { label: 'Broader', value: 'broader' },
  { label: 'Extensive', value: 'extensive' },
  { label: 'Selected', value: 'selected' }
]

const scopeDefault = 'broader'

const scopeOptionsKMapping: Record<string, number | null> = {
  focused: 3,
  broader: 10,
  extensive: null // all of it
}

/**
 * Splits the summary into text and citations. Citations ([docN]) are numbered
 * within the summarized subset, so they are translated to result numbers.
 */
function parseSummaryTokens (text: string, indicesMap: number[]): SummaryToken[] {
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
 * Summarization of search results.
 *
 * @param results all search results
 * @param selectedResults ids of results selected by the user
 * @param getSearchResponse the response of the last search
 */
export function useSearchSummary (
  results: Ref<TextChunkWithDocument[]>,
  selectedResults: Ref<string[]>,
  getSearchResponse: () => SearchResponse | null
) {
  const brevity = ref('short')
  const scope = ref(scopeDefault)
  const summarizing = ref(false)
  const summary = ref('')
  const timeSpent = ref(0)
  const summarizedResultIndices = ref<number[]>([])

  const tokens = computed(() => parseSummaryTokens(summary.value, summarizedResultIndices.value))

  watch(selectedResults, () => {
    scope.value = selectedResults.value.length === 0 ? scopeDefault : 'selected'
  })

  function reset () {
    summary.value = ''
    timeSpent.value = 0
    summarizedResultIndices.value = []
  }

  async function summarize () {
    const searchResponse = getSearchResponse()
    if (!results.value.length || !searchResponse) return
    summarizing.value = true

    // select the focus
    const summarizeK = scopeOptionsKMapping[scope.value]
    const scopedSearchResponse: SearchResponse = {
      ...searchResponse
    }

    let currentIndices: number[] = []

    if (scope.value === 'selected') {
      if (selectedResults.value.length === 0) {
        Notify.create({ message: 'Please select at least one result for summarization.', position: 'top', color: 'warning' })
        summarizing.value = false
        return
      }
      scopedSearchResponse.results = []
      results.value.forEach((r, index) => {
        if (selectedResults.value.includes(r.id)) {
          scopedSearchResponse.results.push(r)
          currentIndices.push(index + 1)
        }
      })
    } else if (summarizeK !== null) {
      scopedSearchResponse.results = results.value.slice(0, summarizeK)
      currentIndices = scopedSearchResponse.results.map((_, i) => i + 1)
    } else {
      scopedSearchResponse.results = results.value
      currentIndices = results.value.map((_, i) => i + 1)
    }

    try {
      const { data } = await api.post<SummaryResponse>('/summarize/results', scopedSearchResponse)
      summarizedResultIndices.value = currentIndices
      summary.value = data.summary
      timeSpent.value = data.time_spent
    } catch (e) {
      summary.value = 'Failed to summarize.'
      timeSpent.value = 0
    } finally {
      summarizing.value = false
    }
  }

  return {
    brevity,
    scope,
    summarizing,
    summary,
    timeSpent,
    tokens,
    summarize,
    reset
  }
}
