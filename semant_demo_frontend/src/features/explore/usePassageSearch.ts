import { ref, shallowRef } from 'vue'
import { SearchType, type PassageSearchResponse, type SearchResultChunk } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { toSearchCriteria, type Criteria } from './criteria'

/** Passages per page (#605): the first page and each Load more. */
export const PASSAGE_PAGE_SIZE = 20

/** What one passage search is for: the applied criteria and the retrieval options. */
export interface PassageQuery {
  criteria: Criteria
  vector: string | null
  /** Search only this collection's passages; not part of the shareable URL. */
  userCollectionId: string | null
}

/**
 * The passages of one search, as loaded so far. A new search gets a new `id`; loading more
 * keeps it (the same search, more of its results). `last` is the newest page's answer, so
 * its `nextOffset`, `bounded`, `totalCount` and `retrievalLimit` describe the population.
 */
export interface PassageResults {
  readonly id: number
  readonly query: PassageQuery
  readonly items: readonly SearchResultChunk[]
  readonly last: PassageSearchResponse
  /** Time of the first page, in seconds. */
  readonly timeSpent: number
}

/**
 * Runs passage searches (`POST /api/search/passages`) and holds the current results.
 * A new search aborts the previous one and its Load more; an answer that still arrives for
 * them is dropped and changes neither the results nor the loading and error states. While a
 * search runs, no results are shown, so earlier ones are never presented as its answer.
 */
export function usePassageSearch () {
  const api = useApi().default
  const results = shallowRef<PassageResults | null>(null)
  const loading = ref(false)
  const loadingMore = ref(false)
  /** Why the last search failed; null while none did. */
  const error = ref<string | null>(null)
  /** Why the last Load more failed; the results loaded before stay. */
  const loadMoreError = ref<string | null>(null)
  const guard = createContextGuard()
  let abort: AbortController | null = null
  let lastId = 0

  const request = (query: PassageQuery, offset: number, signal: AbortSignal) => api.searchPassagesApiSearchPassagesPost({
    passageSearchRequest: {
      criteria: toSearchCriteria(query.criteria),
      offset,
      limit: PASSAGE_PAGE_SIZE,
      type: SearchType.hybrid,
      vector: query.vector,
      userCollectionId: query.userCollectionId
    }
  }, { signal })

  function start (): { isCurrent: () => boolean, signal: AbortSignal } {
    abort?.abort()
    const controller = new AbortController()
    abort = controller
    return { isCurrent: guard.capture(), signal: controller.signal }
  }

  /** Resolves to the new results, or null when it failed or a later search replaced it. */
  async function search (query: PassageQuery): Promise<PassageResults | null> {
    guard.enter()
    const { isCurrent, signal } = start()
    results.value = null
    error.value = null
    loadMoreError.value = null
    loading.value = true
    loadingMore.value = false
    try {
      const page = await request(query, 0, signal)
      if (!isCurrent()) return null
      results.value = { id: ++lastId, query, items: page.items, last: page, timeSpent: page.timeSpent }
      return results.value
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return null
      console.error('Passage search failed', e)
      const message = await apiErrorMessage(e, 'The search failed. Please try again.')
      if (isCurrent()) error.value = message
      return null
    } finally {
      if (isCurrent()) {
        loading.value = false
        abort = null
      }
    }
  }

  /** Loads the next page of the current search; nothing without one or while loading. */
  async function loadMore (): Promise<void> {
    const current = results.value
    const offset = current?.last.nextOffset
    if (!current || offset == null || loading.value || loadingMore.value) return
    const { isCurrent, signal } = start()
    loadingMore.value = true
    loadMoreError.value = null
    try {
      const page = await request(current.query, offset, signal)
      if (!isCurrent() || results.value?.id !== current.id) return
      // A passage ranked again on a later page (equal scores) is shown once.
      const seen = new Set(current.items.map(item => item.id))
      results.value = { ...current, items: [...current.items, ...page.items.filter(item => !seen.has(item.id))], last: page }
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Loading more passages failed', e)
      const message = await apiErrorMessage(e, 'More passages could not be loaded. Please try again.')
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

/**
 * What the loaded passages cover, for the results header: how many are shown, and whether
 * they are all matching passages or only the best ones up to the retrieval limit.
 */
export function passageCoverage (results: PassageResults): string {
  const shown = results.items.length
  const { bounded, totalCount, retrievalLimit } = results.last
  const limit = retrievalLimit.toLocaleString('en')
  if (bounded === false) {
    const total = (totalCount ?? shown).toLocaleString('en')
    return shown === totalCount || totalCount === null
      ? `All ${total} matching ${total === '1' ? 'passage' : 'passages'}.`
      : `${shown.toLocaleString('en')} of ${total} matching passages.`
  }
  if (bounded === true) {
    return `The best ${limit} passages by relevance; more may match. Refine the query or filters to reach others.`
  }
  return `The ${shown.toLocaleString('en')} best passages by relevance so far (at most ${limit} per search).`
}
