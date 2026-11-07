import { ref, shallowRef } from 'vue'
import type { Document } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { toSearchCriteria, type Criteria } from './criteria'

/** Documents of the first page (#606). */
export const FIRST_DOCUMENT_PAGE = 20
/** Documents each Load more adds; the server returns at most 100 at once. */
export const MORE_DOCUMENT_PAGE = 100

/** What one documents search is for: the applied criteria (no text query) and the scope. */
export interface DocumentQuery {
  criteria: Criteria
  /** Browse only this collection's documents; not part of the shareable URL. */
  userCollectionId: string | null
}

/**
 * The documents of one search, as loaded so far, in the server's stable order (publication
 * year, oldest first, then id; the undated last). A new search gets a new `id`; loading more
 * keeps it.
 *
 * `totalCount` is the exact number of matching documents: the population a chart of the same
 * criteria describes (#528), not the loaded page. Only the first `retrievalLimit` of them can
 * be paged through; `bounded` when more match.
 */
export interface DocumentResults {
  readonly id: number
  readonly query: DocumentQuery
  readonly items: readonly Document[]
  /** Offset of the next page; null when the matching (or the reachable) documents are all loaded. */
  readonly nextOffset: number | null
  readonly totalCount: number
  readonly retrievalLimit: number
  readonly bounded: boolean
  /** Time of the first page, in seconds. */
  readonly timeSpent: number
}

export const hasMoreDocuments = (results: DocumentResults): boolean => results.nextOffset !== null

/**
 * Runs documents searches (`POST /api/search/documents`), loads their later pages and holds
 * the current results; the same guards as `usePassageSearch`: a new search aborts the previous
 * one and its Load more, and an answer that still arrives for them is dropped.
 */
export function useDocumentSearch () {
  const api = useApi().default
  const results = shallowRef<DocumentResults | null>(null)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref<string | null>(null)
  const loadMoreError = ref<string | null>(null)
  const guard = createContextGuard()
  let abort: AbortController | null = null
  let lastId = 0

  function start (): { isCurrent: () => boolean, signal: AbortSignal } {
    abort?.abort()
    const controller = new AbortController()
    abort = controller
    return { isCurrent: guard.capture(), signal: controller.signal }
  }

  const page = (query: DocumentQuery, offset: number, limit: number, signal: AbortSignal) =>
    api.searchDocumentsApiSearchDocumentsPost({
      documentSearchRequest: {
        criteria: toSearchCriteria({ ...query.criteria, textQuery: null }),
        limit,
        offset,
        userCollectionId: query.userCollectionId
      }
    }, { signal })

  /** Resolves to the new results, or null when it failed or a later search replaced it. */
  async function search (query: DocumentQuery): Promise<DocumentResults | null> {
    guard.enter()
    const { isCurrent, signal } = start()
    results.value = null
    error.value = null
    loadMoreError.value = null
    loading.value = true
    loadingMore.value = false
    try {
      const found = await page(query, 0, FIRST_DOCUMENT_PAGE, signal)
      if (!isCurrent()) return null
      results.value = {
        id: ++lastId,
        query,
        items: found.items,
        nextOffset: found.nextOffset,
        totalCount: found.totalCount,
        retrievalLimit: found.retrievalLimit,
        bounded: found.bounded,
        timeSpent: found.timeSpent
      }
      return results.value
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return null
      console.error('Documents search failed', e)
      const message = await apiErrorMessage(e, 'The documents could not be loaded. Please try again.')
      if (isCurrent()) error.value = message
      return null
    } finally {
      if (isCurrent()) {
        loading.value = false
        abort = null
      }
    }
  }

  /**
   * Loads the next page of the current search; nothing without more or while loading. The
   * corpus may change between pages: a document already shown is not shown twice.
   */
  async function loadMore (): Promise<void> {
    const current = results.value
    if (!current || current.nextOffset === null || loading.value || loadingMore.value) return
    const offset = current.nextOffset
    const { isCurrent, signal } = start()
    loadingMore.value = true
    loadMoreError.value = null
    try {
      // The last pages stop at the reachable documents (offset + limit <= retrievalLimit).
      const limit = Math.min(MORE_DOCUMENT_PAGE, current.retrievalLimit - offset)
      const next = await page(current.query, offset, limit, signal)
      if (!isCurrent() || results.value?.id !== current.id) return
      const seen = new Set(current.items.map(item => item.id))
      results.value = {
        ...current,
        items: [...current.items, ...next.items.filter(item => !seen.has(item.id))],
        nextOffset: next.nextOffset,
        totalCount: next.totalCount,
        bounded: next.bounded
      }
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Loading more documents failed', e)
      const message = await apiErrorMessage(e, 'More documents could not be loaded. Please try again.')
      if (isCurrent()) loadMoreError.value = message
    } finally {
      if (isCurrent()) {
        loadingMore.value = false
        abort = null
      }
    }
  }

  /** Stops a running search and forgets the results. */
  function cancel () {
    abort?.abort()
    abort = null
    guard.enter()
    results.value = null
    error.value = null
    loadMoreError.value = null
    loading.value = false
    loadingMore.value = false
  }

  return { results, loading, loadingMore, error, loadMoreError, search, loadMore, cancel }
}

/** The stable order of the documents, as the results header names it. */
export const DOCUMENT_ORDER_LABEL = 'Sorted by publication year, oldest first; documents without a year last.'

/**
 * What the loaded documents cover: the exact number of matching documents, how many are
 * shown, and when more match than can be listed, that narrowing the filters reaches them.
 */
export function documentCoverage (results: DocumentResults): string {
  const shown = results.items.length
  const total = results.totalCount
  const noun = total === 1 ? 'document' : 'documents'
  const fmt = (n: number) => n.toLocaleString('en')
  if (results.bounded) {
    return `${fmt(total)} matching ${noun} (${fmt(shown)} shown); only the first ${fmt(results.retrievalLimit)} ` +
      'can be listed. Narrow the filters to reach the others.'
  }
  return shown === total ? `All ${fmt(total)} matching ${noun}.` : `${fmt(total)} matching ${noun} (${fmt(shown)} shown).`
}
