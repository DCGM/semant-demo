import { computed, ref } from 'vue'
import type { DocumentSummaryCitation } from 'src/generated/api'
import { createContextGuard, isAbortError, useApi } from 'src/shared/api'

export type SummaryToken =
  | { type: 'text'; value: string }
  | { type: 'citation'; chunkId: string; number: number }

/**
 * Splits a document summary into text and citation tokens. Unlike the search summary
 * (`features/search/useSearchSummary.ts`), a `[docN]` citation already carries the real
 * chunk id (`citations[N - 1]`): there is no "selected subset" to renumber against.
 * A label the response didn't actually send a citation for (should not happen, but the
 * text is model output) is shown as plain text rather than a dead link.
 */
export function parseDocumentSummaryTokens (text: string, citations: DocumentSummaryCitation[]): SummaryToken[] {
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
    const citation = citations[number - 1]
    tokens.push(citation ? { type: 'citation', chunkId: citation.chunkId, number } : { type: 'text', value: matchText })

    lastIndex = index + matchText.length
  }

  if (lastIndex < text.length) {
    tokens.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return tokens
}

export interface RequestedCitation {
  chunkId: string
  /** Bumped on every request, so clicking the same citation again still re-triggers the scroll. */
  token: number
}

// Module-scope singleton, the same cross-component pattern `useAiAssistance` uses
// (`highlightedAutoSpanId`): the summary panel lives inside `DocumentViewLayout`, but
// `DocumentReaderPage` is a sibling route with no prop/event path from the panel. Setting
// `requestedCitation` from the panel's `cite` event makes the reader page scroll to it.
const summarizing = ref(false)
const summary = ref('')
const citations = ref<DocumentSummaryCitation[]>([])
const error = ref<string | null>(null)
const timeSpent = ref(0)
const requestedCitation = ref<RequestedCitation | null>(null)
let citationToken = 0
let abort: AbortController | null = null
const guard = createContextGuard()

/**
 * Summary of the current document (#249). Works only on the document/collection explicitly
 * given to `summarize`, never a wider or re-derived scope. `reset()` must be called by the
 * owning page whenever the document, the collection or the page itself changes, so a stale
 * request is cancelled and its late answer dropped (the document view's existing
 * document/collection watchers and `onBeforeUnmount` do this the same way they do for
 * `useAiAssistance().reset()`).
 */
export function useDocumentSummary () {
  const api = useApi().default

  const tokens = computed(() => parseDocumentSummaryTokens(summary.value, citations.value))

  function reset () {
    abort?.abort()
    abort = null
    guard.enter()
    summarizing.value = false
    summary.value = ''
    citations.value = []
    error.value = null
    timeSpent.value = 0
  }

  async function summarize (collectionId: string, documentId: string) {
    if (summarizing.value) return
    reset()
    const isCurrent = guard.capture()
    const controller = new AbortController()
    abort = controller
    summarizing.value = true
    try {
      const data = await api.summarizeDocumentApiUserCollectionsCollectionIdDocumentsDocumentIdSummaryPost(
        { collectionId, documentId },
        { signal: controller.signal }
      )
      if (!isCurrent()) return
      summary.value = data.summary
      citations.value = data.citations
      timeSpent.value = data.timeSpent
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Document summarization failed', e)
      error.value = 'Failed to summarize the document.'
    } finally {
      if (isCurrent()) {
        summarizing.value = false
        abort = null
      }
    }
  }

  // Nothing of an in-flight, not-yet-answered request is worth keeping: cancelling it is
  // the same as resetting (unlike AI assist, there are no incremental results to retain).
  const cancel = reset

  /** Called from the summary panel's `cite` event; the reader page watches this to scroll. */
  function cite (chunkId: string) {
    requestedCitation.value = { chunkId, token: ++citationToken }
  }

  return {
    summarizing: computed(() => summarizing.value),
    summary: computed(() => summary.value),
    citations: computed(() => citations.value),
    error: computed(() => error.value),
    timeSpent: computed(() => timeSpent.value),
    tokens,
    summarize,
    cancel,
    reset,
    cite,
    requestedCitation
  }
}

export default useDocumentSummary
