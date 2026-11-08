import { ref, shallowRef } from 'vue'
import { SearchType, type SearchResultChunk } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { toSearchCriteria, type Criteria } from './criteria'

/** Passages of the first page of a search (#605). */
export const FIRST_PASSAGE_PAGE = 20
/** Passages each Load more adds (#611); the server reads at most 100 at once. */
export const MORE_PASSAGE_PAGE = 100

/** What one passage search is for: the applied criteria and the retrieval options. */
export interface PassageQuery {
  criteria: Criteria
  vector: string | null
  /** Search only this collection's passages; not part of the shareable URL. */
  userCollectionId: string | null
}

/**
 * The passages of one search, as loaded so far. A new search gets a new `id`; loading more
 * keeps it (the same search, more of its results).
 *
 * The search ranks once (#611): `rankedIds` is its whole bounded ranking, best first, and
 * Load more reads the next of them by id instead of ranking again. It is the population the
 * coverage describes and that visualizations of the same search can use (#528); it lives only
 * in this state, never in the shareable URL, and a new search replaces it.
 */
export interface PassageResults {
  readonly id: number
  readonly query: PassageQuery
  readonly rankedIds: readonly string[]
  /** The passages of the first `readCount` ranked ids; those gone by the time they were read are missing. */
  readonly items: readonly SearchResultChunk[]
  readonly readCount: number
  /** Coverage of the ranking: at most `retrievalLimit`; `bounded` when the limit cut it, else `totalCount` matches. */
  readonly retrievalLimit: number
  readonly bounded: boolean
  readonly totalCount: number | null
  /** Time of the search (ranking and first page), in seconds. */
  readonly timeSpent: number
}

/** Whether Load more has ranked passages left to read. */
export const hasMorePassages = (results: PassageResults): boolean => results.readCount < results.rankedIds.length

/**
 * Runs passage searches (`POST /api/search/passages`), reads their later pages
 * (`POST /api/search/passages/read`) and holds the current results.
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
      const found = await api.searchPassagesApiSearchPassagesPost({
        passageSearchRequest: {
          criteria: toSearchCriteria(query.criteria),
          limit: FIRST_PASSAGE_PAGE,
          type: SearchType.hybrid,
          vector: query.vector,
          userCollectionId: query.userCollectionId
        }
      }, { signal })
      if (!isCurrent()) return null
      results.value = {
        id: ++lastId,
        query,
        rankedIds: found.rankedIds,
        items: found.items,
        readCount: found.readCount,
        retrievalLimit: found.retrievalLimit,
        bounded: found.bounded,
        totalCount: found.totalCount ?? null,
        timeSpent: found.timeSpent
      }
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

  /**
   * Reads the next ranked ids of the current search; nothing without more or while loading.
   * The server applies the search's collection and criteria again, so it may leave some out.
   */
  async function loadMore (): Promise<void> {
    const current = results.value
    if (!current || !hasMorePassages(current) || loading.value || loadingMore.value) return
    const ids = current.rankedIds.slice(current.readCount, current.readCount + MORE_PASSAGE_PAGE)
    const { isCurrent, signal } = start()
    loadingMore.value = true
    loadMoreError.value = null
    try {
      const page = await api.readPassagesApiSearchPassagesReadPost({
        passageReadRequest: {
          ids,
          criteria: toSearchCriteria(current.query.criteria),
          userCollectionId: current.query.userCollectionId
        }
      }, { signal })
      if (!isCurrent() || results.value?.id !== current.id) return
      const seen = new Set(current.items.map(item => item.id))
      results.value = {
        ...current,
        items: [...current.items, ...page.items.filter(item => !seen.has(item.id))],
        readCount: current.readCount + ids.length
      }
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
 * What the loaded passages cover, for the results header: every matching passage or only the
 * best ones up to the retrieval limit (known from the ranking), and how many are shown.
 */
export function passageCoverage (results: PassageResults): string {
  const shown = results.items.length.toLocaleString('en')
  const { bounded, totalCount, retrievalLimit } = results
  if (bounded) {
    return `The best ${retrievalLimit.toLocaleString('en')} passages by relevance (${shown} shown); more may match. ` +
      'Refine the query or filters to reach others.'
  }
  const total = totalCount ?? results.items.length
  const noun = total === 1 ? 'passage' : 'passages'
  return shown === total.toLocaleString('en')
    ? `All ${shown} matching ${noun}.`
    : `${total.toLocaleString('en')} matching ${noun} (${shown} shown).`
}
