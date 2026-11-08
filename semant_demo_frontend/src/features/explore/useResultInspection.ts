import { ref, shallowRef } from 'vue'
import type { DocumentHit, RankedDocument, SearchResultChunk } from 'src/generated/api'
import { apiErrorMessage, createContextGuard, isAbortError, useApi } from 'src/shared/api'
import { toSearchCriteria, type Criteria } from './criteria'

/** Inspected results of the first page, and of each Load more (the server reads at most 100). */
export const FIRST_INSPECTED_PAGE = 20
export const MORE_INSPECTED_PAGE = 100

/** The inspected subset of one search's ranking (#620): ids in ranking order. */
export interface InspectedSubset {
  /** The search and the inspected category: another of either is another subset. */
  key: string
  criteria: Criteria
  userCollectionId: string | null
  /** Documents: the ranking entries of the subset (read by entry); Passages: their ids. */
  documents: readonly RankedDocument[] | null
  passageIds: readonly string[] | null
}

const subsetSize = (subset: InspectedSubset) => (subset.documents ?? subset.passageIds ?? []).length

/**
 * Reads the inspected results page by page with the read endpoints of Results
 * (`POST /api/search/documents/read`, `POST /api/search/passages/read`), which check the
 * search's collection and criteria again: never a search, so the subset cannot widen. A new
 * subset aborts the reads of the previous one and drops their late answers.
 */
export function useResultInspection () {
  const api = useApi().default
  const subset = shallowRef<InspectedSubset | null>(null)
  const documents = shallowRef<readonly DocumentHit[]>([])
  const passages = shallowRef<readonly SearchResultChunk[]>([])
  /** How many leading subset entries were read (those gone by then are missing). */
  const readCount = ref(0)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref<string | null>(null)
  const loadMoreError = ref<string | null>(null)
  const guard = createContextGuard()
  let abort: AbortController | null = null

  function start () {
    abort?.abort()
    const controller = new AbortController()
    abort = controller
    return { isCurrent: guard.capture(), signal: controller.signal }
  }

  async function read (current: InspectedSubset, from: number, count: number, signal: AbortSignal) {
    const criteria = toSearchCriteria(current.criteria)
    if (current.documents) {
      const ranked = current.documents.slice(from, from + count)
      const page = await api.readDocumentsApiSearchDocumentsReadPost({
        documentReadRequest: { ranked: [...ranked], criteria, userCollectionId: current.userCollectionId }
      }, { signal })
      return { documents: page.items, passages: [], read: ranked.length }
    }
    const ids = (current.passageIds ?? []).slice(from, from + count)
    const page = await api.readPassagesApiSearchPassagesReadPost({
      passageReadRequest: { ids: [...ids], criteria, userCollectionId: current.userCollectionId }
    }, { signal })
    return { documents: [], passages: page.items, read: ids.length }
  }

  /** Shows `requested`, unless it is already shown (or loading) without an error. */
  async function open (requested: InspectedSubset, { force = false } = {}) {
    if (!force && subset.value?.key === requested.key && !error.value) return
    guard.enter()
    const { isCurrent, signal } = start()
    subset.value = requested
    documents.value = []
    passages.value = []
    readCount.value = 0
    error.value = null
    loadMoreError.value = null
    loadingMore.value = false
    loading.value = subsetSize(requested) > 0
    if (!loading.value) return
    try {
      const page = await read(requested, 0, FIRST_INSPECTED_PAGE, signal)
      if (!isCurrent()) return
      documents.value = page.documents
      passages.value = page.passages
      readCount.value = page.read
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Reading the inspected results failed', e)
      const message = await apiErrorMessage(e, 'The inspected results could not be loaded. Please try again.')
      if (isCurrent()) error.value = message
    } finally {
      if (isCurrent()) {
        loading.value = false
        abort = null
      }
    }
  }

  const hasMore = () => !!subset.value && readCount.value < subsetSize(subset.value)

  async function loadMore () {
    const current = subset.value
    if (!current || !hasMore() || loading.value || loadingMore.value) return
    const { isCurrent, signal } = start()
    loadingMore.value = true
    loadMoreError.value = null
    try {
      const page = await read(current, readCount.value, MORE_INSPECTED_PAGE, signal)
      if (!isCurrent() || subset.value?.key !== current.key) return
      const seenDocuments = new Set(documents.value.map(item => item.document.id))
      const seenPassages = new Set(passages.value.map(item => item.id))
      documents.value = [...documents.value, ...page.documents.filter(item => !seenDocuments.has(item.document.id))]
      passages.value = [...passages.value, ...page.passages.filter(item => !seenPassages.has(item.id))]
      readCount.value += page.read
    } catch (e) {
      if (!isCurrent() || isAbortError(e)) return
      console.error('Loading more inspected results failed', e)
      const message = await apiErrorMessage(e, 'More inspected results could not be loaded. Please try again.')
      if (isCurrent()) loadMoreError.value = message
    } finally {
      if (isCurrent()) {
        loadingMore.value = false
        abort = null
      }
    }
  }

  const retry = () => (subset.value ? open(subset.value, { force: true }) : Promise.resolve())

  function clear () {
    abort?.abort()
    abort = null
    guard.enter()
    subset.value = null
    documents.value = []
    passages.value = []
    readCount.value = 0
    loading.value = false
    loadingMore.value = false
    error.value = null
    loadMoreError.value = null
  }

  return { subset, documents, passages, readCount, loading, loadingMore, error, loadMoreError, hasMore, open, loadMore, retry, clear }
}
