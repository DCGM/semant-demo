import { computed, ref } from 'vue'
import type { DocumentSummaryCitation, DocumentSummaryResponse } from 'src/generated/api'
import { aiErrorMessage, createContextGuard, isAbortError, reportAiOperation, useApi } from 'src/shared/api'
import { tokenizeCitations } from 'src/shared/citationTokens'

const SUMMARY_FAILED_FALLBACK = 'Failed to summarize the document.'

export type SummaryToken =
  | { type: 'text'; value: string }
  | { type: 'citation'; chunkId: string; number: number; order: number | null }

/**
 * Splits a document summary into text and citation tokens. Unlike the search summary
 * (`features/search/useSearchSummary.ts`), a `[docN]` citation already carries the real
 * chunk id (`citations[N - 1]`): there is no "selected subset" to renumber against.
 * A label the response didn't actually send a citation for (should not happen, but the
 * text is model output) is shown as plain text rather than a dead link.
 */
export function parseDocumentSummaryTokens (text: string, citations: DocumentSummaryCitation[]): SummaryToken[] {
  return tokenizeCitations(text, number => {
    const citation = citations[number - 1]
    return citation ? { chunkId: citation.chunkId, number, order: citation.order ?? null } : null
  })
}

export interface RequestedCitation {
  chunkId: string
  /** The cited chunk's position in the document, when known; lets the reader load it into
   * the displayed window on demand (useChunkWindow.loadUntil) if it isn't shown yet. */
  order: number | null
  /** Bumped on every request, so clicking the same citation again still re-triggers the scroll. */
  token: number
}

// Module-scope singleton, the same cross-component pattern `useAiAssistance` uses
// (`highlightedAutoSpanId`): the summary panel lives inside `DocumentViewLayout`, but
// `DocumentReaderPage` is a sibling route with no prop/event path from the panel. Setting
// `requestedCitation` from the panel's `cite` event makes the reader page scroll to it.
const summarizing = ref(false)
// The six DocumentSummaryResponse fields are always set and reset together, so one slot
// carries all of them rather than one ref each (#358 review).
const result = ref<DocumentSummaryResponse | null>(null)
const error = ref<string | null>(null)
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

  const tokens = computed(() =>
    result.value ? parseDocumentSummaryTokens(result.value.summary, result.value.citations) : [])

  function reset () {
    abort?.abort()
    abort = null
    guard.enter()
    summarizing.value = false
    result.value = null
    error.value = null
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
      result.value = data
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Document summarization failed', e)
      // The backend answers 502 with a safe, pre-sanitized detail on generation failure
      // (never provider internals) — show it directly, same as other composables do; a
      // refusal for the daily AI allowance gets its own message.
      const message = await aiErrorMessage(e, SUMMARY_FAILED_FALLBACK)
      if (!isCurrent()) return
      error.value = message
    } finally {
      reportAiOperation()
      if (isCurrent()) {
        summarizing.value = false
        abort = null
      }
    }
  }

  // Nothing of an in-flight, not-yet-answered request is worth keeping: cancelling it is
  // the same as resetting (unlike AI assist, there are no incremental results to retain).
  const cancel = reset

  /** Called from the summary panel's `cite` event; the reader page watches this to scroll
   * (loading the chunk into its window first if it isn't displayed yet). */
  function cite (chunkId: string, order: number | null) {
    requestedCitation.value = { chunkId, order, token: ++citationToken }
  }

  return {
    summarizing: computed(() => summarizing.value),
    summary: computed(() => result.value?.summary ?? ''),
    citations: computed(() => result.value?.citations ?? []),
    error: computed(() => error.value),
    timeSpent: computed(() => result.value?.timeSpent ?? 0),
    totalChunks: computed(() => result.value?.totalChunks ?? 0),
    summarizedChunks: computed(() => result.value?.summarizedChunks ?? 0),
    truncated: computed(() => result.value?.truncated ?? false),
    tokens,
    summarize,
    cancel,
    reset,
    cite,
    requestedCitation
  }
}

export default useDocumentSummary
