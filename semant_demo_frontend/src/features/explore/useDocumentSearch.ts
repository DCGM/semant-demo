import { ref, shallowRef } from 'vue'
import { SearchType, type DocumentHit, type DocumentRetrieval, type RankedDocument } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { toSearchCriteria, type Criteria } from './criteria'

/** Documents of the first page (#606). */
export const FIRST_DOCUMENT_PAGE = 20
/** Documents each Load more adds; the server returns at most 100 at once. */
export const MORE_DOCUMENT_PAGE = 100

/** What one documents search is for: the applied criteria and the scope. */
export interface DocumentQuery {
  criteria: Criteria
  /** Search vector of a text query's chunk ranking; null: the server's default. */
  vector?: string | null
  /** Only this collection's documents; not part of the shareable URL. */
  userCollectionId: string | null
}

/**
 * The documents of one search, as loaded so far. A new search gets a new `id`; loading more
 * keeps it.
 *
 * Without a text query (#606) they are paged by offset in the server's stable order
 * (publication year, oldest first, then id; the undated last), and `totalCount` is the exact
 * number of matching documents: the population a chart of the same criteria describes (#528).
 * Only the first `retrievalLimit` can be paged through; `bounded` when more match.
 *
 * With a text query (#607) the search ranks once: `ranked` is its whole bounded ranking of
 * distinct documents (metadata matches first, then by best chunk), and Load more reads the next
 * entries by id. `totalCount` is known only when no retrieval limit cut the ranking (`bounded`);
 * `eligibleCount` is the exact number of documents the filters admit. The ranking lives only in
 * this state, never in the URL.
 */
export interface DocumentResults {
  readonly id: number
  readonly query: DocumentQuery
  readonly items: readonly DocumentHit[]
  /** Offset of the next page without a text query; null when all (reachable) documents are loaded. */
  readonly nextOffset: number | null
  /** A text query's ranking, best first; null without one. */
  readonly ranked: readonly RankedDocument[] | null
  /** How many leading `ranked` entries are loaded. */
  readonly readCount: number
  readonly totalCount: number | null
  readonly eligibleCount: number
  readonly retrievalLimit: number
  readonly bounded: boolean
  readonly retrieval: DocumentRetrieval | null
  /** Time of the first page, in seconds. */
  readonly timeSpent: number
}

export const hasMoreDocuments = (results: DocumentResults): boolean =>
  results.ranked ? results.readCount < results.ranked.length : results.nextOffset !== null

/**
 * Runs documents searches (`POST /api/search/documents`), loads their later pages (by offset,
 * or for a text query by ranking entries, `POST /api/search/documents/read`) and holds the
 * current results; the same guards as `usePassageSearch`: a new search aborts the previous one
 * and its Load more, and an answer that still arrives for them is dropped.
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
        criteria: toSearchCriteria(query.criteria),
        limit,
        offset,
        ...(query.criteria.textQuery ? { type: SearchType.hybrid, vector: query.vector ?? null } : {}),
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
        nextOffset: found.nextOffset ?? null,
        ranked: found.ranked ?? null,
        readCount: found.readCount ?? 0,
        totalCount: found.totalCount ?? null,
        eligibleCount: found.eligibleCount,
        retrievalLimit: found.retrievalLimit,
        bounded: found.bounded,
        retrieval: found.retrieval ?? null,
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

  /** The next page of `current` and the results with it. */
  async function next (current: DocumentResults, signal: AbortSignal): Promise<Pick<DocumentResults, 'items' | 'nextOffset' | 'readCount' | 'totalCount' | 'bounded'>> {
    if (current.ranked) {
      // A text query's ranking: the next entries, read under the search's criteria again.
      const entries = current.ranked.slice(current.readCount, current.readCount + MORE_DOCUMENT_PAGE)
      const read = await api.readDocumentsApiSearchDocumentsReadPost({
        documentReadRequest: {
          ranked: [...entries],
          criteria: toSearchCriteria(current.query.criteria),
          userCollectionId: current.query.userCollectionId
        }
      }, { signal })
      return { ...current, items: read.items, readCount: current.readCount + entries.length }
    }
    const offset = current.nextOffset ?? 0
    // The last pages stop at the reachable documents (offset + limit <= retrievalLimit).
    const limit = Math.min(MORE_DOCUMENT_PAGE, current.retrievalLimit - offset)
    const found = await page(current.query, offset, limit, signal)
    return { ...current, items: found.items, nextOffset: found.nextOffset ?? null, totalCount: found.totalCount ?? null, bounded: found.bounded }
  }

  /**
   * Loads the next page of the current search; nothing without more or while loading. A
   * document already shown is not shown twice (the corpus may change between pages).
   */
  async function loadMore (): Promise<void> {
    const current = results.value
    if (!current || !hasMoreDocuments(current) || loading.value || loadingMore.value) return
    const { isCurrent, signal } = start()
    loadingMore.value = true
    loadMoreError.value = null
    try {
      const loaded = await next(current, signal)
      if (!isCurrent() || results.value?.id !== current.id) return
      const seen = new Set(current.items.map(item => item.document.id))
      results.value = {
        ...current,
        ...loaded,
        items: [...current.items, ...loaded.items.filter(item => !seen.has(item.document.id))]
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

/** The order of the documents, as the results header names it. */
export function documentOrderLabel (results: DocumentResults): string {
  return results.ranked
    ? 'Matches in the title, author or publisher first, then by the best-matching passage.'
    : 'Sorted by publication year, oldest first; documents without a year last.'
}

const fmt = (n: number) => n.toLocaleString('en')
const documents = (n: number) => (n === 1 ? 'document' : 'documents')

/**
 * What the loaded documents cover: the number of matching documents when it is known, how many
 * are shown, and when a limit leaves some out, how to reach them.
 */
export function documentCoverage (results: DocumentResults): string {
  const shown = results.items.length
  if (results.ranked) {
    const ranked = results.ranked.length
    if (results.bounded) {
      return `The best ${fmt(ranked)} ${documents(ranked)} by relevance (${fmt(shown)} shown); more of the ` +
        `${fmt(results.eligibleCount)} ${documents(results.eligibleCount)} these filters admit may match. ` +
        'Refine the query or filters to reach others.'
    }
    return shown === ranked ? `All ${fmt(ranked)} matching ${documents(ranked)}.` : `${fmt(ranked)} matching ${documents(ranked)} (${fmt(shown)} shown).`
  }
  const total = results.totalCount ?? 0
  if (results.bounded) {
    return `${fmt(total)} matching ${documents(total)} (${fmt(shown)} shown); only the first ${fmt(results.retrievalLimit)} ` +
      'can be listed. Narrow the filters to reach the others.'
  }
  return shown === total ? `All ${fmt(total)} matching ${documents(total)}.` : `${fmt(total)} matching ${documents(total)} (${fmt(shown)} shown).`
}
